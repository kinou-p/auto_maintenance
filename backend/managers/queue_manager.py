"""
Auto Maintenance - Workflow Queue Manager.

Gère la file d'attente des workflows pour s'assurer qu'ils s'exécutent
séquentiellement (un par un).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
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
            self._active_tasks: set[asyncio.Task] = set()
            self._is_processing = False
            self._initialized = True

    async def add_to_queue(self, workflow_id: int) -> None:
        """Signale un nouveau workflow et déclenche le processeur de file."""
        logger.info(f"Nouveau workflow ajouté à la file : {workflow_id}")
        await ws_manager.broadcast({"type": "queue_updated"})
        asyncio.create_task(self.process_queue())

    async def process_queue(self) -> None:
        """
        Dépile et lance les workflows PENDING en parallèle
        dans la limite de settings.max_concurrent_workflows.
        """
        while True:
            # 1. Vérifier si on a un slot libre dans le sémaphore
            if len(self._active_tasks) >= settings.max_concurrent_workflows:
                # Tous les slots sont occupés
                break

            async with async_session() as session:
                # Nettoyer les workflows zombies
                running_res = await session.execute(
                    select(Workflow).where(Workflow.status == WorkflowStatus.RUNNING)
                )
                running_list = running_res.scalars().all()
                for wf_item in running_list:
                    if get_active_workflow(wf_item.id) is None:
                        logger.warning(
                            f"Workflow {wf_item.id} détecté Zombie (statut RUNNING sans tâche active). Marquage FAILED."
                        )
                        wf_item.status = WorkflowStatus.FAILED
                        wf_item.error_message = "Arrêt inattendu (Zombie détecté)"
                        wf_item.completed_at = datetime.now(timezone.utc)
                        await session.commit()

                # Récupérer le plus ancien workflow PENDING
                result = await session.execute(
                    select(Workflow)
                    .where(Workflow.status == WorkflowStatus.PENDING)
                    .order_by(Workflow.created_at.asc())
                    .limit(1)
                )
                next_workflow = result.scalar_one_or_none()

                if not next_workflow:
                    logger.info("Plus de workflows PENDING en attente dans la file.")
                    break

                workflow_id = next_workflow.id
                project_id = next_workflow.project_id
                options = next_workflow.options or {}
                steps = options.get("steps")
                selected_updates = options.get("selected_updates")

            # Lancer le workflow dans une tâche asynchrone concurrente
            task = asyncio.create_task(
                self._execute_workflow_task(workflow_id, project_id, steps, selected_updates, options)
            )
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
            await ws_manager.broadcast({"type": "queue_updated"})
            await asyncio.sleep(0.5)

    async def _execute_workflow_task(
        self,
        workflow_id: int,
        project_id: int,
        steps: Optional[list[str]],
        selected_updates: Optional[dict],
        options: Optional[dict],
    ) -> None:
        async with self._semaphore:
            logger.info(f"🚀 Début d'exécution concurrente du workflow {workflow_id} (Projet {project_id})")
            await ws_manager.broadcast({"type": "queue_updated"})
            try:
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
                        await session.commit()
            finally:
                await ws_manager.broadcast({"type": "queue_updated"})
                # Déclencher le dépilage du workflow suivant
                asyncio.create_task(self.process_queue())


# Instance globale
queue_manager = WorkflowQueueManager()
