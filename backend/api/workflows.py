"""
Auto Maintenance - Routes API Workflows.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.core.config import settings
from backend.core.websocket import ws_manager
from backend.managers.workflow_orchestrator import (
    WorkflowOrchestrator,
    get_active_workflow,
)
from backend.managers.queue_manager import queue_manager
from backend.models.database import (
    Project,
    Workflow,
    WorkflowStatus,
    async_session,
)
from backend.models.schemas import (
    StatusResponse,
    WorkflowResponse,
    WorkflowStart,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/", response_model=WorkflowResponse, status_code=201)
async def start_workflow(request: WorkflowStart) -> WorkflowResponse:
    """
    Démarre un nouveau workflow de maintenance.
    
    Le workflow est ajouté à la file d'attente et s'exécutera
    dès que les ressources seront disponibles.
    """
    # Vérifier que le projet existe
    async with async_session() as session:
        project = await session.get(Project, request.project_id)
        if not project:
            raise HTTPException(404, f"Projet {request.project_id} introuvable.")

        # Vérifier qu'il n'y a pas de workflow en cours ou en attente pour ce projet précis
        # (Optionnel : on pourrait autoriser plusieurs en file, mais simplifions)
        running = await session.execute(
            select(Workflow).where(
                Workflow.project_id == request.project_id,
                Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]),
            )
        )
        if running.scalar_one_or_none():
            raise HTTPException(409, "Un workflow est déjà en cours ou en attente pour ce projet.")

        options = {}
        if request.steps:
            options["steps"] = request.steps
        if request.selected_updates:
            options["selected_updates"] = request.selected_updates
        if request.import_only:
            options["import_only"] = True

        # Créer le workflow en DB
        workflow = Workflow(
            project_id=request.project_id,
            status=WorkflowStatus.PENDING,
            options=options,
        )
        session.add(workflow)
        await session.commit()
        await session.refresh(workflow)

        workflow_id = workflow.id

    # Ajouter à la file d'attente
    await queue_manager.add_to_queue(workflow_id)

    # Notifier tous les clients de la mise à jour de la file
    await ws_manager.broadcast({
        "type": "queue_updated",
        "workflow_id": workflow_id,
        "project_id": request.project_id,
        "status": "pending",
        "message": "Nouveau workflow ajouté à la file.",
    })

    # Retourner immédiatement
    async with async_session() as session:
        workflow = await session.get(Workflow, workflow_id)
        return WorkflowResponse.model_validate(workflow)



@router.post("/batch", response_model=list[WorkflowResponse], status_code=201)
async def start_workflows_batch(project_ids: list[int]) -> list[WorkflowResponse]:
    """
    Démarre des workflows pour plusieurs projets (batch).
    """
    created_workflows = []
    
    async with async_session() as session:
        for pid in project_ids:
            # Vérifier existence projet et absence de workflow en cours
            project = await session.get(Project, pid)
            if not project:
                continue
                
            running = await session.execute(
                select(Workflow).where(
                    Workflow.project_id == pid,
                    Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]),
                )
            )
            if running.scalar_one_or_none():
                continue
            
            # Créer le workflow
            workflow = Workflow(
                project_id=pid,
                status=WorkflowStatus.PENDING,
            )
            session.add(workflow)
            await session.flush() # Pour avoir l'ID
            await session.refresh(workflow)
            
            created_workflows.append(WorkflowResponse.model_validate(workflow))
            
            # Ajouter à la queue (ceci ne bloque pas)
            await queue_manager.add_to_queue(workflow.id)
        
        await session.commit()
        
    return created_workflows


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int) -> WorkflowResponse:
    """Récupère le statut d'un workflow."""
    async with async_session() as session:
        workflow = await session.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(404, f"Workflow {workflow_id} introuvable.")
        return WorkflowResponse.model_validate(workflow)


@router.get("/project/{project_id}", response_model=list[WorkflowResponse])
async def list_project_workflows(project_id: int) -> list[WorkflowResponse]:
    """Liste tous les workflows d'un projet."""
    async with async_session() as session:
        result = await session.execute(
            select(Workflow)
            .where(Workflow.project_id == project_id)
            .order_by(Workflow.created_at.desc())
        )
        workflows = result.scalars().all()
        return [WorkflowResponse.model_validate(w) for w in workflows]


@router.get("/project/{project_id}/active", response_model=Optional[WorkflowResponse])
async def get_active_workflow_for_project(project_id: int) -> Optional[WorkflowResponse]:
    """Récupère le workflow actif (RUNNING ou PENDING) d'un projet s'il existe."""
    async with async_session() as session:
        result = await session.execute(
            select(Workflow)
            .where(
                Workflow.project_id == project_id,
                Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]),
            )
            .order_by(Workflow.id.desc())
        )
        workflow = result.scalars().first()
        if workflow:
            return WorkflowResponse.model_validate(workflow)
        return None



@router.post("/{workflow_id}/cancel", response_model=StatusResponse)
async def cancel_workflow(workflow_id: int) -> StatusResponse:
    """Annule un workflow en cours d'exécution ou en attente."""
    # 1. Vérifier si c'est celui qui tourne
    orchestrator = get_active_workflow(workflow_id)
    if orchestrator:
        orchestrator.cancel()
        return StatusResponse(status="success", message="Demande d'annulation envoyée pour le workflow en cours.")

    # 2. Sinon, vérifier s'il est en attente dans la DB et le marquer CANCELLED
    async with async_session() as session:
        workflow = await session.get(Workflow, workflow_id)
        if workflow and workflow.status == WorkflowStatus.PENDING:
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.now(timezone.utc)
            await session.commit()
            return StatusResponse(status="success", message="Workflow en attente annulé.")
            
    raise HTTPException(404, "Aucun workflow actif ou en attente avec cet ID.")


@router.get("/{workflow_id}/logs")
async def get_workflow_logs(workflow_id: int) -> dict:
    """Récupère les logs d'un workflow (depuis la DB)."""
    async with async_session() as session:
        workflow = await session.get(Workflow, workflow_id)
        if not workflow:
            raise HTTPException(404, f"Workflow {workflow_id} introuvable.")

        return {
            "workflow_id": workflow_id,
            "status": workflow.status.value if workflow.status else "unknown",
            "logs": workflow.logs or [],
        }


@router.get("/queue")
async def get_workflow_queue() -> dict:
    """Récupère la liste complète des workflows en cours (RUNNING) et en attente (PENDING)."""
    async with async_session() as session:
        result = await session.execute(
            select(Workflow, Project.name, Project.domain)
            .join(Project, Workflow.project_id == Project.id)
            .where(Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]))
            .order_by(Workflow.created_at.asc())
        )
        rows = result.all()

        items = []
        pending_counter = 0
        for wf, project_name, domain in rows:
            is_running = wf.status == WorkflowStatus.RUNNING
            position = 0
            if not is_running:
                pending_counter += 1
                position = pending_counter

            items.append({
                "id": wf.id,
                "project_id": wf.project_id,
                "project_name": project_name,
                "domain": domain,
                "status": wf.status.value if hasattr(wf.status, "value") else str(wf.status),
                "current_step": wf.current_step,
                "position": position,
                "created_at": wf.created_at.isoformat() if wf.created_at else None,
                "started_at": wf.started_at.isoformat() if wf.started_at else None,
            })

        return {
            "queue": items,
            "total_active": len([i for i in items if i["status"] == "running"]),
            "total_pending": pending_counter,
        }

