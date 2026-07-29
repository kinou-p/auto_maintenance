"""
Auto Maintenance - DDEV Manager.

Gère le cycle de vie des projets DDEV :
création, démarrage, arrêt, suppression, et statut.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.utils.command import CommandResult, run_command, run_ddev_command


class DDEVManager:
    """Orchestre les opérations DDEV pour un projet WordPress."""

    def __init__(self, project_name: str, logger: Optional[WorkflowLogger] = None) -> None:
        self.project_name = project_name
        self.project_dir = settings.effective_ddev_projects_dir / project_name
        self.logger = logger

    async def _log(self, level: str, message: str, step: str = "ddev_create") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)

    # ── Vérifications ─────────────────────────────────────────────

    async def check_ddev_installed(self) -> bool:
        """Vérifie que DDEV est installé et accessible."""
        result = await run_command("ddev --version", timeout=10)
        if result.success or "ddev" in result.stdout.lower() or shutil.which("ddev") is not None:
            return True
        if "permission denied" in (result.stderr or "").lower():
            await self._log(
                "error",
                "DDEV est installé mais Docker n'est pas accessible. "
                "Vérifiez que votre utilisateur est dans le groupe 'docker' : "
                "sudo usermod -aG docker $USER (puis re-login).",
            )
        return False

    async def check_docker_running(self) -> bool:
        """Vérifie que Docker est en cours d'exécution (avec retries si Docker est en cours de démarrage)."""
        import asyncio
        for attempt in range(5):
            result = await run_command("docker info", timeout=10)
            if result.success:
                return True
            if attempt < 4:
                await self._log("info", f"En attente de la stabilisation du daemon Docker ({attempt + 1}/5)...")
                await asyncio.sleep(4)
        return False

    async def project_exists(self) -> bool:
        """Vérifie si le projet DDEV existe déjà."""
        config_path = self.project_dir / ".ddev" / "config.yaml"
        return config_path.exists()

    # ── Cycle de vie ──────────────────────────────────────────────

    async def create_project(self, domain: Optional[str] = None) -> CommandResult:
        """
        Crée un nouveau projet DDEV configuré pour WordPress.

        Args:
            domain: Domaine personnalisé (ex: monsite.ddev.site).

        Returns:
            CommandResult du ddev config.
        """
        await self._log("info", f"Création du projet DDEV '{self.project_name}'...")

        # Vérifier les prérequis
        if not await self.check_ddev_installed():
            await self._log("error", "DDEV n'est pas installé ou inaccessible.")
            return CommandResult(
                returncode=1, stdout="", stderr="DDEV non installé", command="ddev version"
            )

        if not await self.check_docker_running():
            await self._log("error", "Docker n'est pas en cours d'exécution.")
            return CommandResult(
                returncode=1, stdout="", stderr="Docker non démarré", command="docker info"
            )

        # Créer le répertoire du projet
        self.project_dir.mkdir(parents=True, exist_ok=True)
        await self._log("info", f"Répertoire créé : {self.project_dir}")

        # Configurer DDEV
        fqdn = domain or f"{self.project_name}.ddev.site"
        # Ajouter le domaine original ET le domaine .ddev.site comme FQDNs
        # pour que les assets référençant l'ancien domaine soient servis localement
        ddev_fqdn = f"{self.project_name}.ddev.site"
        fqdns = set([fqdn, ddev_fqdn])
        fqdns_str = ",".join(fqdns)
        config_cmd = (
            f"ddev config"
            f" --project-type=wordpress"
            f" --project-name={self.project_name}"
            f" --php-version={settings.ddev_php_version}"
            f" --webserver-type={settings.ddev_webserver_type}"
            f" --database=mariadb:{settings.ddev_mariadb_version}"
            f" --additional-fqdns={fqdns_str}"
            f" --performance-mode=none"
            f" --docroot=."
            f" --upload-dirs=wp-content/uploads"
        )

        result = await run_ddev_command(config_cmd, str(self.project_dir))

        if result.success:
            await self._log("success", f"Projet DDEV configuré avec succès (domaine: {fqdn})")
            # Écrire une config supplémentaire pour augmenter les limites PHP et MariaDB
            await self._write_php_config()
            await self._write_mysql_config()
        else:
            await self._log("error", f"Échec de la configuration DDEV : {result.stderr}")

        return result

    async def _write_php_config(self) -> None:
        """Écrit une configuration PHP personnalisée pour les gros imports."""
        php_ini_dir = self.project_dir / ".ddev" / "php"
        php_ini_dir.mkdir(parents=True, exist_ok=True)
        php_ini = php_ini_dir / "custom.ini"
        php_ini.write_text(
            "[PHP]\n"
            "upload_max_filesize = 2G\n"
            "post_max_size = 2G\n"
            "memory_limit = 2048M\n"
            "max_execution_time = 0\n"
            "max_input_time = 0\n"
            "max_input_vars = 10000\n"
        )
        await self._log("info", "Configuration PHP personnalisée appliquée (upload 2G, memory 2G)")

    async def _write_mysql_config(self) -> None:
        """Écrit une configuration MariaDB ultra-rapide (désactivation fsync synchrone lors de la restauration)."""
        mysql_dir = self.project_dir / ".ddev" / "mysql"
        mysql_dir.mkdir(parents=True, exist_ok=True)
        mysql_cnf = mysql_dir / "speed.cnf"
        mysql_cnf.write_text(
            "[mysqld]\n"
            "innodb_flush_log_at_trx_commit = 2\n"
            "innodb_doublewrite = 0\n"
            "max_allowed_packet = 1G\n"
            "innodb_buffer_pool_size = 512M\n"
            "sync_binlog = 0\n"
            "innodb_io_capacity = 2000\n"
        )
        await self._log("info", "Configuration MariaDB optimisée (fast transaction log applied)")

    async def start(self, retries: int = 3) -> CommandResult:
        """Démarre les conteneurs DDEV du projet avec retries automatique et nettoyage réseau pour gérer les conflits Docker/ddev-router temporaires."""
        import asyncio
        await self._log("info", "Démarrage des conteneurs DDEV...")

        last_result: Optional[CommandResult] = None

        for attempt in range(1, retries + 1):
            result = await run_ddev_command("ddev start", str(self.project_dir), timeout=180)
            last_result = result

            if result.success:
                await self._log("success", "Conteneurs DDEV démarrés avec succès.")
                return result

            err_lower = (result.stderr or "").lower() + (result.stdout or "").lower()
            is_subnet_error = (
                "all predefined address pools have been fully subnetted" in err_lower
                or "failed to create network" in err_lower
            )
            is_transient_docker_error = is_subnet_error or any(
                kw in err_lower
                for kw in [
                    "already in progress",
                    "failed to start ddev-router",
                    "conflict",
                    "is already in use",
                    "driver failed programming external connectivity",
                ]
            )

            if is_transient_docker_error and attempt < retries:
                if is_subnet_error:
                    await self._log(
                        "warning",
                        f"Pool d'adresses IP Docker saturé ({attempt}/{retries}). Nettoyage automatique des réseaux Docker inutilisés (docker network prune)...",
                    )
                    await run_command("docker network prune -f", timeout=30)
                else:
                    await self._log(
                        "warning",
                        f"Conflit Docker/ddev-router temporaire ({attempt}/{retries}). Nouvelle tentative dans 4s...",
                    )
                await asyncio.sleep(4)
            else:
                break

        await self._log("error", f"Échec du démarrage DDEV : {last_result.stderr if last_result else 'Erreur inconnue'}")
        return last_result if last_result else CommandResult(returncode=1, stdout="", stderr="Échec ddev start", command="ddev start")

    async def stop(self) -> CommandResult:
        """Arrête les conteneurs DDEV du projet."""
        await self._log("info", "Arrêt des conteneurs DDEV...")
        result = await run_ddev_command("ddev stop", str(self.project_dir), timeout=60)

        if result.success:
            await self._log("success", "Conteneurs DDEV arrêtés.")
        else:
            await self._log("warning", f"Problème à l'arrêt DDEV : {result.stderr}")

        return result

    async def pause(self) -> CommandResult:
        """Met en pause les conteneurs DDEV du projet."""
        await self._log("info", "Mise en pause des conteneurs DDEV...")
        result = await run_ddev_command("ddev pause", str(self.project_dir), timeout=60)

        if result.success:
            await self._log("success", "Conteneurs DDEV mis en pause.")
        else:
            await self._log("warning", f"Problème à la mise en pause DDEV : {result.stderr}")

        return result

    async def destroy(self, remove_files: bool = False) -> CommandResult:
        """
        Supprime le projet DDEV.

        Args:
            remove_files: Si True, supprime aussi les fichiers du projet.
        """
        await self._log("warning", f"Suppression du projet DDEV '{self.project_name}'...")

        cmd = "ddev delete -Oy"
        result = await run_ddev_command(cmd, str(self.project_dir), timeout=60)

        if result.success and remove_files and self.project_dir.exists():
            shutil.rmtree(self.project_dir, ignore_errors=True)
            await self._log("info", "Fichiers du projet supprimés.")

        if result.success:
            await self._log("success", "Projet DDEV supprimé.")
            await run_command("docker network prune -f", timeout=15)
        else:
            await self._log("error", f"Échec de la suppression : {result.stderr}")

        return result

    async def restart(self) -> CommandResult:
        """Redémarre les conteneurs DDEV."""
        await self._log("info", "Redémarrage DDEV...")
        result = await run_ddev_command("ddev restart", str(self.project_dir), timeout=180)

        if result.success:
            await self._log("success", "DDEV redémarré.")
        else:
            await self._log("error", f"Échec du redémarrage : {result.stderr}")

        return result

    async def recreate(self, domain: Optional[str] = None) -> CommandResult:
        """
        Supprime et recrée complètement le projet DDEV.
        Attention : cette opération préserve les fichiers (car destroy n'est pas appelé avec remove_files=True).
        """
        await self._log("warning", f"Recréation complète du projet DDEV '{self.project_name}'...")
        
        # 1. Stop
        await self.stop()
        
        # 2. Delete (containers/configs)
        await self.destroy(remove_files=False)
        
        # 3. Config
        config_result = await self.create_project(domain)
        if not config_result.success:
            return config_result
            
        # 4. Start
        return await self.start()

    # ── MariaDB Snapshots ─────────────────────────────────────────

    async def create_snapshot(self, snapshot_name: str = "pre_updates") -> CommandResult:
        """
        Crée un snapshot MariaDB ultra-rapide (< 1 seconde).

        Args:
            snapshot_name: Nom du snapshot.
        """
        await self._log("info", f"📸 Création du snapshot MariaDB '{snapshot_name}'...")
        cmd = f"ddev snapshot --name={snapshot_name}"
        result = await run_ddev_command(cmd, str(self.project_dir), timeout=60)

        if result.success:
            await self._log("success", f"Snapshot MariaDB '{snapshot_name}' créé avec succès.")
        else:
            await self._log("warning", f"Impossible de créer le snapshot MariaDB : {result.stderr}")

        return result

    async def restore_snapshot(self, snapshot_name: str = "pre_updates") -> CommandResult:
        """
        Restaure un snapshot MariaDB en environ 1 seconde.

        Args:
            snapshot_name: Nom du snapshot à restaurer.
        """
        await self._log("info", f"🔄 Restauration instantanée du snapshot MariaDB '{snapshot_name}'...")
        cmd = f"ddev snapshot restore {snapshot_name}"
        result = await run_ddev_command(cmd, str(self.project_dir), timeout=90)

        if result.success:
            await self._log("success", f"Snapshot MariaDB '{snapshot_name}' restauré en ~1s.")
        else:
            await self._log("error", f"Échec de la restauration du snapshot : {result.stderr}")

        return result

    async def get_status(self) -> dict:
        """Récupère le statut du projet DDEV."""
        if not await self.project_exists():
            return {"running": False, "status": "not_created", "data": None, "urls": []}

        result = await run_ddev_command(
            "ddev describe -j", str(self.project_dir), timeout=15
        )
        if result.success:
            import json
            try:
                data = json.loads(result.stdout)
                raw = data.get("raw", {})
                status_str = raw.get("status", "stopped")
                is_running = status_str in ("running", "OK")
                return {
                    "running": is_running,
                    "status": status_str,
                    "data": data,
                    "urls": raw.get("urls", []),
                }
            except json.JSONDecodeError:
                pass
        return {"running": False, "status": "stopped", "data": None, "urls": []}

    async def get_url(self) -> str:
        """Retourne l'URL principale du projet DDEV."""
        status = await self.get_status()
        urls = status.get("urls", [])
        # Préférer https
        for url in urls:
            if url.startswith("https://"):
                return url
        return urls[0] if urls else f"https://{self.project_name}.ddev.site"

    async def exec_in_container(self, command: str, timeout: int = 60) -> CommandResult:
        """Exécute une commande dans le conteneur web DDEV."""
        return await run_ddev_command(
            f"ddev exec {command}", str(self.project_dir), timeout=timeout
        )

    async def copy_to_container(self, local_path: str, container_path: str) -> CommandResult:
        """Copie un fichier local dans le répertoire du projet DDEV (monté sur /var/www/html)."""
        import os
        await self._log("info", f"Copie de {local_path} vers le conteneur...")

        src = Path(local_path)
        if not src.exists():
            err_msg = f"Fichier local introuvable : {local_path}"
            await self._log("error", err_msg)
            return CommandResult(returncode=1, stdout="", stderr=err_msg, command="copy_file")

        try:
            rel_path = container_path
            if rel_path.startswith("/var/www/html/"):
                rel_path = rel_path[len("/var/www/html/"):]
            elif rel_path.startswith("/tmp/"):
                rel_path = rel_path[len("/tmp/"):]

            rel_path = rel_path.lstrip("/").replace("/", os.sep)
            dest = self.project_dir / rel_path

            if container_path.endswith("/") or container_path.endswith("\\"):
                dest = dest / src.name

            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

            await self._log("success", f"Fichier copié dans le conteneur ({src.name})")
            return CommandResult(returncode=0, stdout=f"Copie réussie vers {dest}", stderr="", command="copy_file")
        except Exception as e:
            err_msg = f"Échec de la copie : {e}"
            await self._log("error", err_msg)
            return CommandResult(returncode=1, stdout="", stderr=err_msg, command="copy_file")
