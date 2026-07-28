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

from backend.models.database import Workflow, WorkflowStatus, async_session
from backend.managers.workflow_orchestrator import WorkflowOrchestrator, get_active_workflow
from backend.core.websocket import ws_manager

logger = logging.getLogger("auto_maintenance.queue")


class WorkflowQueueManager:
    """
    Gère l'exécution séquentielle des workflows.
    
    Pattern Singleton pour s'assurer qu'il n'y a qu'une seule file de traitement.
    """
    
    _instance: Optional[WorkflowQueueManager] = None
    
    def __new__(cls) -> WorkflowQueueManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._lock = asyncio.Lock()
            self._is_processing = False
            self._initialized = True

    async def add_to_queue(self, workflow_id: int) -> None:
        """
        Signale qu'un nouveau workflow est disponible.
        Déclenche le traitement si aucun workflow n'est en cours.
        """
        logger.info(f"Nouveau workflow ajouté à la file : {workflow_id}")
        
        # On ne lance le traitement que s'il n'est pas déjà en cours
        # (le traitement boucle tant qu'il y a des items via process_queue)
        if not self._is_processing:
            asyncio.create_task(self.process_queue())

    async def process_queue(self) -> None:
        """
        Traite la file d'attente des workflows PENDING.
        S'assure qu'un seul workflow tourne à la fois.
        """
        # Eviter les exécutions concurrentes de process_queue
        if self._is_processing:
            return

        async with self._lock:
            self._is_processing = True
            
            try:
                while True:
                    async with async_session() as session:
                        # 1. Vérifier si un workflow est déjà en cours d'exécution
                        running_res = await session.execute(
                            select(Workflow).where(Workflow.status == WorkflowStatus.RUNNING)
                        )
                        running_list = running_res.scalars().all()
                        active_running_found = False

                        for wf_item in running_list:
                            if get_active_workflow(wf_item.id) is None:
                                logger.warning(
                                    f"Workflow {wf_item.id} détecté en statut RUNNING sans orchestration active (Zombie). "
                                    "Marquage comme FAILED et continuation de la file."
                                )
                                wf_item.status = WorkflowStatus.FAILED
                                wf_item.error_message = "Arrêt inattendu (Zombie détecté)"
                                wf_item.completed_at = datetime.now(timezone.utc)
                                await session.commit()
                            else:
                                active_running_found = True

                        if active_running_found:

                                
                                await ws_manager.broadcast({
                                    "type": "workflow_status",
                                    "workflow_id": existing_running.id,
                                    "project_id": existing_running.project_id,
                                    "status": "failed",
                                    "completed": False,
                                })

                        # 2. Récupérer le plus vieux workflow PENDING
                        result = await session.execute(
                            select(Workflow)
                            .where(Workflow.status == WorkflowStatus.PENDING)
                            .order_by(Workflow.created_at.asc())
                            .limit(1)
                        )
                        next_workflow = result.scalar_one_or_none()
                        
                        if not next_workflow:
                            logger.info("Plus de workflows en attente.")
                            break

                        workflow_id = next_workflow.id
                        project_id = next_workflow.project_id
                        options = next_workflow.options or {}
                        steps = options.get("steps")
                        selected_updates = options.get("selected_updates")
                        
                        logger.info(f"Démarrage du workflow {workflow_id} pour le projet {project_id}")

                    # 3. Exécuter le workflow
                    try:
                        orchestrator = WorkflowOrchestrator(
                            project_id=project_id,
                            workflow_id=workflow_id,
                            steps=steps,
                            selected_updates=selected_updates,
                            options=options,
                        )

                        
                        # Exécution (bloquante pour la boucle while, mais async)
                        await orchestrator.run()
                        
                    except Exception as e:
                        logger.error(f"Erreur lors de l'exécution du workflow {workflow_id}: {e}")
                        # On s'assure qu'il est marqué failed pour ne pas bloquer la boucle
                        async with async_session() as session:
                            w = await session.get(Workflow, workflow_id)
                            if w and w.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
                                w.status = WorkflowStatus.FAILED
                                w.error_message = f"Erreur système: {str(e)}"
                                await session.commit()

                    # Petite pause pour laisser respirer
                    await asyncio.sleep(1)

            finally:
                self._is_processing = False

# Instance globale
queue_manager = WorkflowQueueManager()
