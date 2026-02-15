"""
Auto Maintenance - Workflow Orchestrator.

Orchestre l'enchaînement des étapes de maintenance WordPress :
création DDEV → install WP → import → screenshots → updates → VRT.

Supporte l'annulation en cours d'exécution et le nettoyage automatique
en cas d'échec.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger, ws_manager
from backend.managers.ddev_manager import DDEVManager
from backend.managers.hosts_manager import HostsManager
from backend.managers.screenshot_manager import ScreenshotManager
from backend.managers.vrt_manager import VRTManager
from backend.managers.wordpress_manager import WordPressManager
from backend.models.database import (
    Project,
    ProjectStatus,
    VRTReport,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    async_session,
)


# Registry des workflows en cours (pour annulation)
_active_workflows: dict[int, "WorkflowOrchestrator"] = {}


def get_active_workflow(workflow_id: int) -> Optional["WorkflowOrchestrator"]:
    return _active_workflows.get(workflow_id)


class WorkflowOrchestrator:
    """
    Orchestre un workflow complet de maintenance WordPress.

    Workflow complet :
    1. Création du projet DDEV
    2. Configuration DNS (/etc/hosts)
    3. Installation WordPress
    4. Installation du plugin AIO WP Migration
    5. Import du fichier .wpress
    6. Screenshots avant maintenance
    7. Liste des mises à jour
    8. Application des mises à jour
    9. Screenshots après maintenance
    10. Comparaison visuelle (VRT)
    11. Génération du rapport
    """

    # Mapping étape → poids estimé pour la barre de progression
    STEP_WEIGHTS: dict[str, float] = {
        WorkflowStep.DDEV_CREATE: 10,
        WorkflowStep.DNS_SETUP: 2,
        WorkflowStep.WP_INSTALL: 15,
        WorkflowStep.PLUGIN_INSTALL: 5,
        WorkflowStep.WPRESS_IMPORT: 25,
        WorkflowStep.SCREENSHOTS_BEFORE: 10,
        WorkflowStep.UPDATES_LIST: 3,
        WorkflowStep.UPDATES_APPLY: 15,
        WorkflowStep.SCREENSHOTS_AFTER: 10,
        WorkflowStep.VRT_COMPARE: 5,
    }

    def __init__(
        self,
        project_id: int,
        workflow_id: int,
        steps: Optional[list[str]] = None,
        selected_updates: Optional[dict] = None,
    ) -> None:
        self.project_id = project_id
        self.workflow_id = workflow_id
        self.steps = steps or [s.value for s in WorkflowStep]
        self.selected_updates = selected_updates or {}
        self._cancelled = False
        self._current_step: Optional[str] = None
        self.logger = WorkflowLogger(project_id, workflow_id)

        # Managers (initialisés au lancement)
        self._ddev: Optional[DDEVManager] = None
        self._wp: Optional[WordPressManager] = None
        self._hosts: Optional[HostsManager] = None
        self._screenshots: Optional[ScreenshotManager] = None
        self._vrt: Optional[VRTManager] = None

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        """Demande l'annulation du workflow."""
        self._cancelled = True

    async def _check_cancelled(self) -> None:
        """Vérifie si le workflow a été annulé."""
        if self._cancelled:
            raise WorkflowCancelled("Workflow annulé par l'utilisateur.")

    # ── Exécution principale ──────────────────────────────────────

    async def run(self) -> dict:
        """
        Exécute le workflow complet.

        Returns:
            Dict avec le résultat du workflow.
        """
        start_time = time.time()
        _active_workflows[self.workflow_id] = self

        try:
            # Charger les infos du projet
            async with async_session() as session:
                project = await session.get(Project, self.project_id)
                if not project:
                    raise ValueError(f"Projet {self.project_id} introuvable")

                # Mettre à jour le statut du workflow
                workflow = await session.get(Workflow, self.workflow_id)
                if workflow:
                    workflow.status = WorkflowStatus.RUNNING
                    workflow.started_at = datetime.now(timezone.utc)
                    await session.commit()

            # Notifier le frontend du démarrage
            await ws_manager.broadcast({
                "type": "workflow_status",
                "workflow_id": self.workflow_id,
                "project_id": self.project_id,
                "status": "running",
                "completed": False,
            })

            # Initialiser les managers
            self._ddev = DDEVManager(project.name, self.logger)
            self._wp = WordPressManager(project.name, self._ddev, self.logger)
            self._hosts = HostsManager(self.logger)
            self._screenshots = ScreenshotManager(project.name, self.logger)
            self._vrt = VRTManager(project.name, self.logger)

            domain = project.domain
            wpress_file = project.wpress_file

            await self.logger.info("Démarrage du workflow de maintenance", step="workflow")

            # Exécuter chaque étape dans l'ordre
            step_handlers: dict[str, Any] = {
                WorkflowStep.DDEV_CREATE: lambda: self._step_ddev_create(domain),
                WorkflowStep.DNS_SETUP: lambda: self._step_dns_setup(domain),
                WorkflowStep.WP_INSTALL: lambda: self._step_wp_install(domain),
                WorkflowStep.PLUGIN_INSTALL: lambda: self._step_plugin_install(),
                WorkflowStep.WPRESS_IMPORT: lambda: self._step_wpress_import(wpress_file),
                WorkflowStep.SCREENSHOTS_BEFORE: lambda: self._step_screenshots("before"),
                WorkflowStep.UPDATES_LIST: lambda: self._step_updates_list(),
                WorkflowStep.UPDATES_APPLY: lambda: self._step_updates_apply(),
                WorkflowStep.SCREENSHOTS_AFTER: lambda: self._step_screenshots("after"),
                WorkflowStep.VRT_COMPARE: lambda: self._step_vrt_compare(),
            }

            completed_steps: list[str] = []
            failed_steps: list[str] = []

            for step_name in self.steps:
                await self._check_cancelled()
                self._current_step = step_name

                handler = step_handlers.get(step_name)
                if not handler:
                    await self.logger.warning(f"Étape inconnue ignorée : {step_name}")
                    continue

                # Calculer la progression globale
                total_weight = sum(self.STEP_WEIGHTS.get(s, 1) for s in self.steps)
                done_weight = sum(
                    self.STEP_WEIGHTS.get(s, 1) for s in completed_steps
                )
                progress = (done_weight / total_weight) * 100 if total_weight else 0

                await self.logger.progress(step_name, progress, f"Étape : {step_name}")

                # Mettre à jour la DB
                async with async_session() as session:
                    workflow = await session.get(Workflow, self.workflow_id)
                    if workflow:
                        workflow.current_step = step_name
                        workflow.steps_completed = completed_steps
                        await session.commit()

                try:
                    await handler()
                    completed_steps.append(step_name)
                    await self.logger.success(f"Étape '{step_name}' terminée.", step=step_name)

                    # Notifier le frontend de la complétion de l'étape
                    await ws_manager.send_to_project(self.project_id, {
                        "type": "step_completed",
                        "workflow_id": self.workflow_id,
                        "project_id": self.project_id,
                        "step": step_name,
                        "status": "completed",
                        "steps_completed": list(completed_steps),
                        "steps_failed": list(failed_steps),
                    })
                except WorkflowCancelled:
                    raise
                except Exception as e:
                    failed_steps.append(step_name)
                    await self.logger.error(
                        f"Étape '{step_name}' échouée : {e}", step=step_name
                    )

                    # Notifier le frontend de l'échec de l'étape
                    await ws_manager.send_to_project(self.project_id, {
                        "type": "step_completed",
                        "workflow_id": self.workflow_id,
                        "project_id": self.project_id,
                        "step": step_name,
                        "status": "failed",
                        "steps_completed": list(completed_steps),
                        "steps_failed": list(failed_steps),
                    })
                    # Continuer avec les étapes suivantes si possible
                    # Sauf pour les étapes critiques
                    critical_steps = {
                        WorkflowStep.DDEV_CREATE,
                        WorkflowStep.WP_INSTALL,
                        WorkflowStep.WPRESS_IMPORT,
                    }
                    if step_name in critical_steps:
                        await self.logger.error(
                            f"Étape critique échouée. Arrêt du workflow.", step=step_name
                        )
                        break

            # Finaliser
            elapsed = time.time() - start_time
            status = (
                WorkflowStatus.COMPLETED if not failed_steps
                else WorkflowStatus.FAILED
            )

            async with async_session() as session:
                workflow = await session.get(Workflow, self.workflow_id)
                if workflow:
                    workflow.status = status
                    workflow.steps_completed = completed_steps
                    workflow.steps_failed = failed_steps
                    workflow.completed_at = datetime.now(timezone.utc)
                    workflow.logs = self.logger.get_logs()
                    await session.commit()

                project = await session.get(Project, self.project_id)
                if project:
                    project.status = (
                        ProjectStatus.MAINTENANCE_DONE if not failed_steps
                        else ProjectStatus.ERROR
                    )
                    await session.commit()

            await self.logger.progress("workflow", 100, "Workflow terminé")
            await self.logger.info(
                f"Workflow terminé en {elapsed:.1f}s "
                f"({len(completed_steps)} réussie(s), {len(failed_steps)} échouée(s))",
                step="workflow",
            )

            # Notifier le frontend du changement de statut
            await ws_manager.broadcast({
                "type": "workflow_status",
                "workflow_id": self.workflow_id,
                "project_id": self.project_id,
                "status": status.value,
                "completed": not failed_steps,
            })

            return {
                "status": status.value,
                "elapsed_seconds": round(elapsed, 1),
                "completed_steps": completed_steps,
                "failed_steps": failed_steps,
            }

        except WorkflowCancelled:
            elapsed = time.time() - start_time
            await self.logger.warning("Workflow annulé.", step="workflow")

            # Notifier le frontend de l'annulation
            await ws_manager.broadcast({
                "type": "workflow_status",
                "workflow_id": self.workflow_id,
                "project_id": self.project_id,
                "status": "cancelled",
                "completed": False,
            })

            async with async_session() as session:
                workflow = await session.get(Workflow, self.workflow_id)
                if workflow:
                    workflow.status = WorkflowStatus.CANCELLED
                    workflow.completed_at = datetime.now(timezone.utc)
                    workflow.logs = self.logger.get_logs()
                    await session.commit()

            return {
                "status": "cancelled",
                "elapsed_seconds": round(elapsed, 1),
            }

        except Exception as e:
            await self.logger.error(f"Erreur fatale du workflow : {e}", step="workflow")

            async with async_session() as session:
                workflow = await session.get(Workflow, self.workflow_id)
                if workflow:
                    workflow.status = WorkflowStatus.FAILED
                    workflow.error_message = str(e)
                    workflow.completed_at = datetime.now(timezone.utc)
                    workflow.logs = self.logger.get_logs()
                    await session.commit()

            raise

        finally:
            # Libérer le navigateur Playwright
            if self._screenshots:
                await self._screenshots.cleanup()
            _active_workflows.pop(self.workflow_id, None)

    # ── Étapes individuelles ──────────────────────────────────────

    async def _step_ddev_create(self, domain: str) -> None:
        """Étape 1 : Création du projet DDEV."""
        assert self._ddev is not None
        result = await self._ddev.create_project(domain)
        if not result.success:
            raise StepError(f"Impossible de créer le projet DDEV : {result.stderr}")

        result = await self._ddev.start()
        if not result.success:
            raise StepError(f"Impossible de démarrer DDEV : {result.stderr}")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.INITIALIZING
                project.ddev_dir = str(self._ddev.project_dir)
                await session.commit()

    async def _step_dns_setup(self, domain: str) -> None:
        """Étape 2 : Configuration DNS locale."""
        assert self._hosts is not None
        success = await self._hosts.add_entry(domain)
        if not success:
            await self.logger.warning(
                "Impossible de modifier /etc/hosts. "
                "Utilisez DDEV qui gère le DNS automatiquement.",
                step="dns_setup",
            )
            # Non-bloquant : DDEV gère le DNS via dnsmasq

    async def _step_wp_install(self, domain: str) -> None:
        """Étape 3 : Installation WordPress."""
        assert self._wp is not None
        success = await self._wp.full_install(domain)
        if not success:
            raise StepError("Échec de l'installation WordPress.")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.WORDPRESS_INSTALLED
                await session.commit()

    async def _step_plugin_install(self) -> None:
        """Étape 4 : Installation du plugin AIO WP Migration."""
        assert self._wp is not None
        result = await self._wp.install_aio_plugin()
        if not result.success:
            await self.logger.warning(
                "Plugin AIO non installé. L'import .wpress pourrait échouer.",
                step="plugin_install",
            )

    async def _step_wpress_import(self, wpress_file: Optional[str]) -> None:
        """Étape 5 : Import du fichier .wpress."""
        if not wpress_file:
            await self.logger.info(
                "Pas de fichier .wpress à importer. Saut de l'étape.",
                step="wpress_import",
            )
            return

        assert self._wp is not None
        success = await self._wp.import_wpress(wpress_file)
        if not success:
            raise StepError("Échec de l'import .wpress.")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.READY
                await session.commit()

    async def _step_screenshots(self, phase: str) -> None:
        """Étape 6/9 : Capture des screenshots."""
        assert self._wp is not None
        assert self._screenshots is not None

        # Vérifier que le site est accessible avant de capturer
        site_url = await self._wp.ddev.get_url()
        import httpx
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                response = await client.get(site_url)
                if response.status_code != 200:
                    await self.logger.warning(
                        f"Le site répond avec le code {response.status_code}. "
                        f"Les screenshots pourraient être incorrects.",
                        step=f"screenshots_{phase}",
                    )
                else:
                    # Vérifier la présence de CSS dans le HTML
                    body = response.text
                    has_css = '<link' in body and ('stylesheet' in body or '.css' in body)
                    if not has_css:
                        await self.logger.warning(
                            "Aucune feuille de style CSS détectée dans le HTML. "
                            "Les screenshots risquent de montrer du HTML brut.",
                            step=f"screenshots_{phase}",
                        )
        except Exception as e:
            await self.logger.warning(
                f"Impossible de vérifier l'accessibilité du site : {e}",
                step=f"screenshots_{phase}",
            )

        pages = await self._wp.get_page_info()
        if not pages:
            await self.logger.warning(
                f"Aucune page trouvée pour les screenshots ({phase}).",
                step=f"screenshots_{phase}",
            )
            return

        await self._screenshots.capture_screenshots(pages, phase)

    async def _step_updates_list(self) -> None:
        """Étape 7 : Liste des mises à jour disponibles."""
        assert self._wp is not None
        updates = await self._wp.list_updates()

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
        """Étape 8 : Application des mises à jour."""
        assert self._wp is not None

        # Si des mises à jour ont été sélectionnées
        update_core = self.selected_updates.get("update_core", True)
        plugin_names = self.selected_updates.get("plugin_names")
        theme_names = self.selected_updates.get("theme_names")

        # Si aucune sélection, tout mettre à jour
        if plugin_names is None and hasattr(self, "_available_updates"):
            plugin_names = [p.name for p in self._available_updates.get("plugins", [])]
        if theme_names is None and hasattr(self, "_available_updates"):
            theme_names = [t.name for t in self._available_updates.get("themes", [])]

        results = await self._wp.apply_updates(
            update_core=update_core,
            plugin_names=plugin_names or [],
            theme_names=theme_names or [],
        )

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
                total_success = sum(1 for r in results if r.success)
                total_failed = sum(1 for r in results if not r.success)
                workflow.updates_stats = {
                    "total": len(results),
                    "success": total_success,
                    "failed": total_failed,
                    "img_optim_saved_bytes": 0,  # Placeholder pour future feature
                }
                await session.commit()

    async def _step_vrt_compare(self) -> None:
        """Étape 10 : Comparaison visuelle avant/après."""
        assert self._vrt is not None
        report = await self._vrt.compare_all()

        # Sauvegarder les résultats VRT en DB
        async with async_session() as session:
            for item in report.get("items", []):
                vrt_report = VRTReport(
                    project_id=self.project_id,
                    workflow_id=self.workflow_id,
                    page_url=item.get("page_url", ""),
                    page_name=item.get("page_name", ""),
                    device=item.get("device", "unknown"),
                    before_screenshot=item.get("before_path"),
                    after_screenshot=item.get("after_path"),
                    diff_image=item.get("diff_image"),
                    diff_percentage=item.get("diff_percentage"),
                    ssim_score=item.get("ssim_score"),
                    passed=1 if item.get("passed") else 0,
                )
                session.add(vrt_report)
            await session.commit()

        # Envoyer le rapport via WebSocket
        await ws_manager.send_to_project(self.project_id, {
            "type": "vrt_report",
            "data": report,
        })

    # ── Nettoyage ─────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Nettoie les ressources en cas d'échec (rollback)."""
        try:
            if self._ddev:
                await self._ddev.stop()
            if self._hosts:
                async with async_session() as session:
                    project = await session.get(Project, self.project_id)
                    if project:
                        await self._hosts.remove_entry(project.domain)
        except Exception:
            pass


class StepError(Exception):
    """Erreur lors d'une étape du workflow."""
    pass


class WorkflowCancelled(Exception):
    """Le workflow a été annulé par l'utilisateur."""
    pass
