"""
Auto Maintenance - Machine d'États et Moteur d'Orchestration.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

from backend.core.websocket import WorkflowLogger, ws_manager
from backend.managers.ddev_manager import DDEVManager
from backend.managers.docker_env_manager import DockerEnvManager
from backend.managers.hosts_manager import HostsManager
from backend.managers.orchestrator.exceptions import StepError, WorkflowCancelled
from backend.managers.orchestrator.steps_setup import WorkflowSetupStepsMixin
from backend.managers.orchestrator.steps_updates import WorkflowUpdatesStepsMixin
from backend.managers.orchestrator.steps_visual import WorkflowVisualStepsMixin
from backend.managers.screenshot_manager import ScreenshotManager
from backend.managers.vrt_manager import VRTManager
from backend.managers.wordpress_manager import WordPressManager
from backend.models.database import (
    Project,
    ProjectStatus,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    async_session,
)


# Registry des workflows en cours (pour annulation)
_active_workflows: dict[int, "WorkflowOrchestrator"] = {}


def get_active_workflow(workflow_id: int) -> Optional["WorkflowOrchestrator"]:
    """Retourne l'instance d'orchestrateur active pour un workflow_id donné."""
    return _active_workflows.get(workflow_id)


class WorkflowOrchestrator(
    WorkflowSetupStepsMixin,
    WorkflowUpdatesStepsMixin,
    WorkflowVisualStepsMixin,
):
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

    IMPORT_ONLY_STEPS: list[str] = [
        WorkflowStep.DDEV_CREATE.value if hasattr(WorkflowStep.DDEV_CREATE, "value") else str(WorkflowStep.DDEV_CREATE),
        WorkflowStep.DNS_SETUP.value if hasattr(WorkflowStep.DNS_SETUP, "value") else str(WorkflowStep.DNS_SETUP),
        WorkflowStep.WP_INSTALL.value if hasattr(WorkflowStep.WP_INSTALL, "value") else str(WorkflowStep.WP_INSTALL),
        WorkflowStep.PLUGIN_INSTALL.value if hasattr(WorkflowStep.PLUGIN_INSTALL, "value") else str(WorkflowStep.PLUGIN_INSTALL),
        WorkflowStep.WPRESS_IMPORT.value if hasattr(WorkflowStep.WPRESS_IMPORT, "value") else str(WorkflowStep.WPRESS_IMPORT),
    ]

    def __init__(
        self,
        project_id: int,
        workflow_id: int,
        steps: Optional[list[str]] = None,
        selected_updates: Optional[dict] = None,
        options: Optional[dict] = None,
    ) -> None:
        self.project_id = project_id
        self.workflow_id = workflow_id
        self.selected_updates = selected_updates or {}
        self.options = options or self.selected_updates

        import_only_active = (
            self.options.get("import_only")
            or self.options.get("no_maintenance")
            or self.options.get("setup_only")
            or self.selected_updates.get("import_only")
            or self.selected_updates.get("no_maintenance")
            or self.selected_updates.get("setup_only")
        )

        if steps:
            self.steps = [s.value if hasattr(s, "value") else str(s) for s in steps]
        elif import_only_active:
            self.steps = list(self.IMPORT_ONLY_STEPS)
        else:
            self.steps = [s.value if hasattr(s, "value") else str(s) for s in WorkflowStep]

        self._cancelled = False
        self._current_step: Optional[str] = None
        self._project_name: Optional[str] = None
        self.logger = WorkflowLogger(project_id, workflow_id)

        # Managers (initialisés au lancement)
        self._ddev: Optional[DDEVManager] = None
        self._docker: Optional[DockerEnvManager] = None
        self._wp: Optional[WordPressManager] = None
        self._hosts: Optional[HostsManager] = None
        self._screenshots: Optional[ScreenshotManager] = None
        self._vrt: Optional[VRTManager] = None

    @property
    def project_name(self) -> str:
        """Nom du projet associé à ce workflow."""
        if self._project_name:
            return self._project_name
        if self._wp and hasattr(self._wp, "project_name"):
            return self._wp.project_name
        return ""

    @project_name.setter
    def project_name(self, value: Optional[str]) -> None:
        self._project_name = value

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

                self.project_name = project.name

                # Le claim atomique de la queue passe déjà PENDING→RUNNING.
                # On s'assure seulement que le statut est cohérent.
                workflow = await session.get(Workflow, self.workflow_id)
                if workflow:
                    if workflow.status == WorkflowStatus.CANCELLED:
                        raise WorkflowCancelled("Workflow annulé avant démarrage.")
                    if workflow.status != WorkflowStatus.RUNNING:
                        workflow.status = WorkflowStatus.RUNNING
                        workflow.started_at = datetime.now(timezone.utc)
                        await session.commit()
                    elif workflow.started_at is None:
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
            self._docker = DockerEnvManager(project.name, self.logger)
            self._wp = WordPressManager(project.name, self._ddev, self.logger)
            self._hosts = HostsManager(self.logger)
            self._screenshots = ScreenshotManager(project.name, self.logger, workflow_id=self.workflow_id)
            self._vrt = VRTManager(project.name, self.logger, workflow_id=self.workflow_id)

            domain = project.domain
            wpress_file = project.wpress_file

            await self.logger.info("Démarrage du workflow de maintenance", step="workflow")

            # Exécuter chaque étape dans l'ordre
            step_handlers: dict[str, Any] = {
                WorkflowStep.DDEV_CREATE.value if hasattr(WorkflowStep.DDEV_CREATE, "value") else str(WorkflowStep.DDEV_CREATE): lambda: self._step_ddev_create(domain),
                WorkflowStep.DNS_SETUP.value if hasattr(WorkflowStep.DNS_SETUP, "value") else str(WorkflowStep.DNS_SETUP): lambda: self._step_dns_setup(domain),
                WorkflowStep.WP_INSTALL.value if hasattr(WorkflowStep.WP_INSTALL, "value") else str(WorkflowStep.WP_INSTALL): lambda: self._step_wp_install(domain),
                WorkflowStep.PLUGIN_INSTALL.value if hasattr(WorkflowStep.PLUGIN_INSTALL, "value") else str(WorkflowStep.PLUGIN_INSTALL): lambda: self._step_plugin_install(),
                WorkflowStep.WPRESS_IMPORT.value if hasattr(WorkflowStep.WPRESS_IMPORT, "value") else str(WorkflowStep.WPRESS_IMPORT): lambda: self._step_wpress_import(wpress_file),
                WorkflowStep.SCREENSHOTS_BEFORE.value if hasattr(WorkflowStep.SCREENSHOTS_BEFORE, "value") else str(WorkflowStep.SCREENSHOTS_BEFORE): lambda: self._step_screenshots("before"),
                WorkflowStep.UPDATES_LIST.value if hasattr(WorkflowStep.UPDATES_LIST, "value") else str(WorkflowStep.UPDATES_LIST): lambda: self._step_updates_list(),
                WorkflowStep.UPDATES_APPLY.value if hasattr(WorkflowStep.UPDATES_APPLY, "value") else str(WorkflowStep.UPDATES_APPLY): lambda: self._step_updates_apply(),
                WorkflowStep.SCREENSHOTS_AFTER.value if hasattr(WorkflowStep.SCREENSHOTS_AFTER, "value") else str(WorkflowStep.SCREENSHOTS_AFTER): lambda: self._step_screenshots("after"),
                WorkflowStep.VRT_COMPARE.value if hasattr(WorkflowStep.VRT_COMPARE, "value") else str(WorkflowStep.VRT_COMPARE): lambda: self._step_vrt_compare(),
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
                        WorkflowStep.DDEV_CREATE.value,
                        WorkflowStep.WP_INSTALL.value,
                        WorkflowStep.WPRESS_IMPORT.value,
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
                    is_import_only = (
                        self.options.get("import_only")
                        or self.options.get("no_maintenance")
                        or self.options.get("setup_only")
                        or self.selected_updates.get("import_only")
                        or self.selected_updates.get("no_maintenance")
                        or self.selected_updates.get("setup_only")
                    )
                    if failed_steps:
                        project.status = ProjectStatus.ERROR
                    elif is_import_only:
                        project.status = ProjectStatus.READY
                    else:
                        project.status = ProjectStatus.MAINTENANCE_DONE
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
            # Arrêter les conteneurs DDEV du projet pour libérer immédiatement la RAM (MariaDB, web, etc.)
            if self._ddev:
                try:
                    await self._ddev.stop()
                except Exception:
                    pass
            _active_workflows.pop(self.workflow_id, None)

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
