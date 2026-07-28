"""
Auto Maintenance - Workflow Queue Manager.

Gère la file d'attente des workflows pour s'assurer qu'ils s'exécutent
dans la limite de concurrence configurée, avec claim atomique PENDING→RUNNING.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from backend.core.config import settings
from backend.models.database import Workflow, WorkflowStatus, async_session
from backend.managers.workflow_orchestrator import WorkflowOrchestrator, get_active_workflow
from backend.core.websocket import ws_manager

logger = logging.getLogger("auto_maintenance.queue")


class WorkflowQueueManager:
    """
    Gère l'exécution concurrente et parallèle des workflows.
    Supporte la configuration du nombre max de projets simultanés (settings.max_concurrent_workflows).
    """

    _instance: Optional[WorkflowQueueManager] = None

    def __new__(cls) -> WorkflowQueueManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_workflows)
            self._active_tasks: dict[int, asyncio.Task] = {}
            self._claim_lock = asyncio.Lock()
            self._process_lock = asyncio.Lock()
            self._initialized = True

    async def add_to_queue(self, workflow_id: int) -> None:
        """Signale un nouveau workflow et déclenche le processeur de file."""
        logger.info(f"Nouveau workflow ajouté à la file : {workflow_id}")
        await ws_manager.broadcast({"type": "queue_updated"})
        asyncio.create_task(self.process_queue())

    async def _cleanup_zombies(self) -> None:
        """Marque FAILED les workflows RUNNING sans tâche active en mémoire."""
        async with async_session() as session:
            running_res = await session.execute(
                select(Workflow).where(Workflow.status == WorkflowStatus.RUNNING)
            )
            running_list = running_res.scalars().all()
            changed = False
            for wf_item in running_list:
                has_task = wf_item.id in self._active_tasks and not self._active_tasks[wf_item.id].done()
                if get_active_workflow(wf_item.id) is None and not has_task:
                    logger.warning(
                        f"Workflow {wf_item.id} détecté Zombie (statut RUNNING sans tâche active). Marquage FAILED."
                    )
                    wf_item.status = WorkflowStatus.FAILED
                    wf_item.error_message = "Arrêt inattendu (Zombie détecté)"
                    wf_item.completed_at = datetime.now(timezone.utc)
                    changed = True
            if changed:
                await session.commit()
                await ws_manager.broadcast({"type": "queue_updated"})

    async def _claim_next_workflow(self) -> Optional[tuple[int, int, Optional[list], Optional[dict], dict]]:
        """
        Claim atomique du plus ancien workflow PENDING.
        Passe PENDING → RUNNING en une seule transaction pour éviter les doubles exécutions.
        """
        async with self._claim_lock:
            async with async_session() as session:
                # Claim atomique via UPDATE conditionnel (compatible SQLite).
                # Le lock asyncio _claim_lock sérialise les claims dans le process.
                result = await session.execute(
                    select(Workflow)
                    .where(Workflow.status == WorkflowStatus.PENDING)
                    .order_by(Workflow.created_at.asc())
                    .limit(1)
                )
                next_workflow = result.scalar_one_or_none()
                if not next_workflow:
                    return None

                claim = await session.execute(
                    update(Workflow)
                    .where(
                        Workflow.id == next_workflow.id,
                        Workflow.status == WorkflowStatus.PENDING,
                    )
                    .values(
                        status=WorkflowStatus.RUNNING,
                        started_at=datetime.now(timezone.utc),
                    )
                )
                if claim.rowcount != 1:
                    await session.rollback()
                    return None

                workflow_id = next_workflow.id
                project_id = next_workflow.project_id
                options = dict(next_workflow.options or {})
                steps = options.get("steps")
                selected_updates = options.get("selected_updates")
                await session.commit()

                return workflow_id, project_id, steps, selected_updates, options

    async def process_queue(self) -> None:
        """
        Dépile et lance les workflows PENDING en parallèle
        dans la limite de settings.max_concurrent_workflows.
        """
        if self._process_lock.locked():
            return

        async with self._process_lock:
            await self._cleanup_zombies()

            while True:
                # Nettoyer les tâches terminées
                done_ids = [wid for wid, t in self._active_tasks.items() if t.done()]
                for wid in done_ids:
                    self._active_tasks.pop(wid, None)

                if len(self._active_tasks) >= settings.max_concurrent_workflows:
                    break

                claimed = await self._claim_next_workflow()
                if not claimed:
                    logger.info("Plus de workflows PENDING en attente dans la file.")
                    break

                workflow_id, project_id, steps, selected_updates, options = claimed
                task = asyncio.create_task(
                    self._execute_workflow_task(
                        workflow_id, project_id, steps, selected_updates, options
                    )
                )
                self._active_tasks[workflow_id] = task
                task.add_done_callback(lambda t, wid=workflow_id: self._active_tasks.pop(wid, None))
                await ws_manager.broadcast({"type": "queue_updated"})

    async def _execute_workflow_task(
        self,
        workflow_id: int,
        project_id: int,
        steps: Optional[list[str]],
        selected_updates: Optional[dict],
        options: Optional[dict],
    ) -> None:
        async with self._semaphore:
            logger.info(
                f"Début d'exécution concurrente du workflow {workflow_id} (Projet {project_id})"
            )
            await ws_manager.broadcast({"type": "queue_updated"})
            try:
                # Vérifier annulation pendant l'attente du sémaphore
                async with async_session() as session:
                    w = await session.get(Workflow, workflow_id)
                    if not w or w.status == WorkflowStatus.CANCELLED:
                        logger.info(f"Workflow {workflow_id} annulé avant exécution.")
                        return

                orchestrator = WorkflowOrchestrator(
                    project_id=project_id,
                    workflow_id=workflow_id,
                    steps=steps,
                    selected_updates=selected_updates,
                    options=options,
                )
                await orchestrator.run()
            except Exception as e:
                logger.error(f"Erreur lors de l'exécution du workflow {workflow_id}: {e}")
                async with async_session() as session:
                    w = await session.get(Workflow, workflow_id)
                    if w and w.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
                        w.status = WorkflowStatus.FAILED
                        w.error_message = f"Erreur système: {str(e)}"
                        w.completed_at = datetime.now(timezone.utc)
                        await session.commit()
            finally:
                await ws_manager.broadcast({"type": "queue_updated"})
                asyncio.create_task(self.process_queue())


# Instance globale
queue_manager = WorkflowQueueManager()
