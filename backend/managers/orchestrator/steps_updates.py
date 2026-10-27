"""
Auto Maintenance - Étapes de Mises à jour (Listing, Application, Rollback).
"""

from __future__ import annotations

from typing import Optional

from backend.core.websocket import ws_manager
from backend.managers.backup_manager import BackupManager
from backend.managers.orchestrator.exceptions import StepError
from backend.models.database import Project, ProjectStatus, Workflow, async_session


class WorkflowUpdatesStepsMixin:
    """Mixin pour les étapes de listing et d'application des mises à jour avec rollback."""

    async def _step_updates_list(self) -> None:
        """Étape 7 : Liste des mises à jour disponibles."""
        assert self._wp is not None
        updates = await self._wp.list_updates()

        tot = updates.get("total_available", 0)
        core_up = updates.get("core")
        core_str = f"Core ({core_up.current_version} -> {core_up.new_version})" if core_up else "Core (à jour)"
        plugins_cnt = len(updates.get("plugins", []))
        themes_cnt = len(updates.get("themes", []))

        await self.logger.info(
            f"📦 {tot} mise(s) à jour détectée(s) : {core_str}, {plugins_cnt} plugin(s), {themes_cnt} thème(s).",
            step="updates_list",
        )

        # Envoyer la liste via WebSocket pour affichage dans le dashboard
        await ws_manager.send_to_project(self.project_id, {
            "type": "updates_available",
            "data": {
                "core": updates["core"].model_dump() if updates["core"] else None,
                "plugins": [p.model_dump() for p in updates["plugins"]],
                "themes": [t.model_dump() for t in updates["themes"]],
                "total_available": updates["total_available"],
            },
        })

        # Stocker pour l'étape suivante si pas de sélection manuelle
        self._available_updates = updates

    async def _step_updates_apply(self) -> None:
        """Étape 8 : Application des mises à jour avec Snapshot MariaDB instantané et backup complet des fichiers."""
        assert self._wp is not None
        assert self._ddev is not None

        # Si des mises à jour ont été sélectionnées
        update_core = self.selected_updates.get("update_core", True)
        plugin_names = self.selected_updates.get("plugin_names")
        theme_names = self.selected_updates.get("theme_names")

        # Si aucune sélection, tout mettre à jour
        if plugin_names is None and hasattr(self, "_available_updates"):
            plugin_names = [p.name for p in self._available_updates.get("plugins", [])]
        if theme_names is None and hasattr(self, "_available_updates"):
            theme_names = [t.name for t in self._available_updates.get("themes", [])]

        # Sauvegarde préventive complète (DB + Fichiers) via BackupManager
        snapshot_name = f"pre_updates_wf_{self.workflow_id}"
        p_name = self.project_name or (self._wp.project_name if self._wp else "")
        backup_mgr = BackupManager(
            project_name=p_name,
            project_dir=self._wp.project_dir,
            ddev=self._ddev,
            logger=self.logger,
            workflow_id=self.workflow_id,
        )
        backup_res = await backup_mgr.create_backup(snapshot_name, backup_core=update_core)
        if not backup_res.success:
            raise StepError(f"Échec critique de la sauvegarde préventive avant mises à jour : {backup_res.error}")

        await self.logger.info(
            f"⚙️ Application des mises à jour en cours... (Core: {update_core}, Plugins: {len(plugin_names or [])}, Thèmes: {len(theme_names or [])})",
            step="updates_apply",
        )

        async def _do_rollback(reason: str):
            await self.logger.error(
                f"⚠️ Déclenchement du rollback complet (MariaDB + Fichiers) : {reason}",
                step="updates_apply",
            )
            rest_res = await backup_mgr.restore_backup(backup_res)
            if not rest_res.success:
                await self.logger.error(
                    f"Échec critique lors du rollback : {rest_res.error}",
                    step="updates_apply",
                )
            else:
                await self.logger.success("Rollback complet (base + fichiers) validé avec succès.", step="updates_apply")

        try:
            results = await self._wp.apply_updates(
                update_core=update_core,
                plugin_names=plugin_names or [],
                theme_names=theme_names or [],
            )
        except Exception as e:
            await _do_rollback(f"Exception durant la mise à jour : {e}")
            raise

        total_success = sum(1 for r in results if r.success)
        total_failed = sum(1 for r in results if not r.success)

        # Si toutes les mises à jour ont échoué, rollback automatique
        if results and total_success == 0:
            await _do_rollback("100% des mises à jour ont échoué.")
            raise StepError("Toutes les mises à jour ont échoué. Rollback complet effectué.")

        await self.logger.info(
            f"✅ Application terminée : {total_success}/{len(results)} mise(s) à jour réussie(s) ({total_failed} échec(s)).",
            step="updates_apply",
        )

        # Nettoyer l'archive de backup temporaire après succès
        await backup_mgr.cleanup_backup(backup_res)

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.MAINTENANCE_IN_PROGRESS
                await session.commit()

        # Envoyer les résultats via WebSocket
        await ws_manager.send_to_project(self.project_id, {
            "type": "updates_results",
            "data": [r.model_dump() for r in results],
        })

        # Sauvegarder les stats dans le workflow
        async with async_session() as session:
            workflow = await session.get(Workflow, self.workflow_id)
            if workflow:
                workflow.updates_stats = {
                    "total": len(results),
                    "success": total_success,
                    "failed": total_failed,
                    "img_optim_saved_bytes": 0,
                }
                await session.commit()
