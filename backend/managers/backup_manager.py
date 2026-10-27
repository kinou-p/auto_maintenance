"""
Auto Maintenance - Backup & Restore Manager.

Gère de façon unifiée et sécurisée :
- La création et restauration des snapshots MariaDB instantanés via DDEV.
- L'archivage et la restauration complète des fichiers WordPress (plugins, thèmes, et core :
  wp-admin, wp-includes, fichiers PHP racine hors wp-config.php).
- Le nettoyage strict des répertoires avant restauration afin d'éviter tout fichier orphelin résiduel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import shutil
import tarfile
from typing import Optional

from backend.core.websocket import WorkflowLogger
from backend.managers.ddev_manager import DDEVManager


@dataclass
class BackupResult:
    """Résultat d'une opération de sauvegarde préventive."""
    success: bool
    snapshot_name: str
    tar_path: Optional[Path] = None
    archived_folders: list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RestoreResult:
    """Résultat d'une opération de restauration après incident ou régression."""
    success: bool
    db_restored: bool = False
    files_restored: bool = False
    error: Optional[str] = None


class BackupManager:
    """Gère la sauvegarde et la restauration cohérente base de données + fichiers WordPress."""

    def __init__(
        self,
        project_name: str,
        project_dir: Path,
        ddev: DDEVManager,
        logger: Optional[WorkflowLogger] = None,
        workflow_id: Optional[int] = None,
    ) -> None:
        self.project_name = project_name
        self.project_dir = Path(project_dir)
        self.ddev = ddev
        self.logger = logger
        self.workflow_id = workflow_id

    async def _log(self, level: str, message: str, step: str = "backup_restore") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)

    async def create_backup(
        self,
        snapshot_name: str,
        backup_core: bool = True,
    ) -> BackupResult:
        """
        Crée une sauvegarde intégrale (Snapshot MariaDB + Archive Fichiers).

        Args:
            snapshot_name: Nom du snapshot MariaDB DDEV.
            backup_core: Si True, sauvegarde également wp-admin, wp-includes et les .php racines.

        Returns:
            BackupResult détaillant le statut et le chemin de l'archive.
        """
        await self._log("info", f"📦 Création de la sauvegarde préventive (DB: {snapshot_name})...", step="updates_apply")

        # 1. Snapshot MariaDB
        snap_res = await self.ddev.create_snapshot(snapshot_name)
        if not snap_res.success:
            err_msg = f"Échec critique de création du snapshot MariaDB '{snapshot_name}' : {snap_res.stderr or snap_res.stdout}"
            await self._log("error", err_msg, step="updates_apply")
            return BackupResult(
                success=False,
                snapshot_name=snapshot_name,
                error=err_msg,
            )

        # 2. Archive fichiers WordPress
        backup_dir = self.project_dir / ".ddev" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        wf_suffix = f"_wf_{self.workflow_id}" if self.workflow_id is not None else ""
        tar_path = backup_dir / f"{snapshot_name}{wf_suffix}_files.tar.gz"

        archived_folders: list[str] = []

        def _archive_files() -> list[str]:
            folders_to_purge_on_restore = []
            with tarfile.open(tar_path, "w:gz") as tar:
                # wp-content/plugins et wp-content/themes
                wp_content = self.project_dir / "wp-content"
                if wp_content.exists():
                    for folder in ["plugins", "themes"]:
                        folder_path = wp_content / folder
                        if folder_path.exists():
                            rel_name = f"wp-content/{folder}"
                            tar.add(folder_path, arcname=rel_name)
                            folders_to_purge_on_restore.append(rel_name)

                # Core WordPress si demandé
                if backup_core:
                    for core_dir in ["wp-admin", "wp-includes"]:
                        core_path = self.project_dir / core_dir
                        if core_path.exists():
                            tar.add(core_path, arcname=core_dir)
                            folders_to_purge_on_restore.append(core_dir)

                    # Fichiers PHP à la racine (sauf wp-config.php)
                    for php_file in self.project_dir.glob("*.php"):
                        if php_file.name == "wp-config.php":
                            continue
                        tar.add(php_file, arcname=php_file.name)

            return folders_to_purge_on_restore

        try:
            archived_folders = await asyncio.to_thread(_archive_files)
            await self._log(
                "success",
                f"✅ Sauvegarde complète (DB '{snapshot_name}' + {len(archived_folders)} répertoires de fichiers) créée avec succès.",
                step="updates_apply",
            )
            return BackupResult(
                success=True,
                snapshot_name=snapshot_name,
                tar_path=tar_path,
                archived_folders=archived_folders,
            )
        except Exception as e:
            err_msg = f"Échec de l'archivage préventif des fichiers WordPress : {e}"
            await self._log("error", err_msg, step="updates_apply")
            if tar_path.exists():
                try:
                    tar_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return BackupResult(
                success=False,
                snapshot_name=snapshot_name,
                error=err_msg,
            )

    async def restore_backup(self, backup: BackupResult) -> RestoreResult:
        """
        Restaure la base de données MariaDB et les fichiers WordPress.
        Nettoie au préalable les dossiers archivés pour supprimer tout fichier orphelin créé par la mise à jour.
        """
        await self._log(
            "warning",
            f"⚠️ Restauration complète en cours (DB: {backup.snapshot_name})...",
            step="updates_apply",
        )

        # 1. Restauration MariaDB
        rest_db = await self.ddev.restore_snapshot(backup.snapshot_name)
        db_ok = rest_db.success
        if not db_ok:
            await self._log("error", f"Échec de restauration du snapshot MariaDB : {rest_db.stderr}", step="updates_apply")
        else:
            await self._log("success", f"Base de données MariaDB restaurée depuis '{backup.snapshot_name}'.", step="updates_apply")

        # 2. Restauration des fichiers WordPress
        files_ok = True
        if backup.tar_path and backup.tar_path.exists():
            def _extract_clean() -> None:
                # Vider d'abord les répertoires existants qui étaient archivés pour éviter les fichiers résiduels
                for rel_folder in backup.archived_folders:
                    target_folder = self.project_dir / rel_folder
                    if target_folder.exists() and target_folder.is_dir():
                        shutil.rmtree(target_folder)
                        target_folder.mkdir(parents=True, exist_ok=True)

                # Extraire l'archive complète
                with tarfile.open(backup.tar_path, "r:gz") as tar:
                    tar.extractall(path=self.project_dir)

            try:
                await asyncio.to_thread(_extract_clean)
                await self._log("success", "Fichiers WordPress intégralement restaurés depuis l'archive de sauvegarde.", step="updates_apply")
            except Exception as e:
                files_ok = False
                await self._log("error", f"Échec critique de restauration des fichiers WordPress : {e}", step="updates_apply")

        overall_success = db_ok and files_ok
        error_msg = None
        if not overall_success:
            parts = []
            if not db_ok:
                parts.append(f"DB: {rest_db.stderr or 'erreur inconnue'}")
            if not files_ok:
                parts.append("Fichiers: échec de décompression ou restauration")
            error_msg = " ; ".join(parts)

        return RestoreResult(
            success=overall_success,
            db_restored=db_ok,
            files_restored=files_ok,
            error=error_msg,
        )

    async def cleanup_backup(self, backup: Optional[BackupResult]) -> None:
        """Supprime l'archive temporaire de backup des fichiers."""
        if backup and backup.tar_path and backup.tar_path.exists():
            try:
                backup.tar_path.unlink(missing_ok=True)
            except Exception:
                pass
