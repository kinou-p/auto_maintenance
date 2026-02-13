"""
Auto Maintenance - Routes API Workflows.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.managers.workflow_orchestrator import (
    WorkflowOrchestrator,
    get_active_workflow,
)
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

    Le workflow s'exécute en arrière-plan et envoie les logs
    en temps réel via WebSocket.
    """
    # Vérifier que le projet existe
    async with async_session() as session:
        project = await session.get(Project, request.project_id)
        if not project:
            raise HTTPException(404, f"Projet {request.project_id} introuvable.")

        # Vérifier qu'il n'y a pas de workflow en cours
        running = await session.execute(
            select(Workflow).where(
                Workflow.project_id == request.project_id,
                Workflow.status == WorkflowStatus.RUNNING,
            )
        )
        if running.scalar_one_or_none():
            raise HTTPException(409, "Un workflow est déjà en cours pour ce projet.")

        # Créer le workflow en DB
        workflow = Workflow(
            project_id=request.project_id,
            status=WorkflowStatus.PENDING,
        )
        session.add(workflow)
        await session.commit()
        await session.refresh(workflow)

        workflow_id = workflow.id

    # Préparer les mises à jour sélectionnées
    selected_updates = {}
    if request.selected_updates:
        selected_updates = {
            "update_core": True,
            "plugin_names": request.selected_updates,
            "theme_names": [],
        }

    # Lancer le workflow en arrière-plan
    orchestrator = WorkflowOrchestrator(
        project_id=request.project_id,
        workflow_id=workflow_id,
        steps=request.steps,
        selected_updates=selected_updates,
    )

    asyncio.create_task(orchestrator.run())

    # Retourner immédiatement
    async with async_session() as session:
        workflow = await session.get(Workflow, workflow_id)
        return WorkflowResponse.model_validate(workflow)


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
    """Récupère le workflow actif (RUNNING) d'un projet s'il existe."""
    async with async_session() as session:
        result = await session.execute(
            select(Workflow).where(
                Workflow.project_id == project_id,
                Workflow.status == WorkflowStatus.RUNNING,
            )
        )
        workflow = result.scalar_one_or_none()
        if workflow:
            return WorkflowResponse.model_validate(workflow)
        return None


@router.post("/{workflow_id}/cancel", response_model=StatusResponse)
async def cancel_workflow(workflow_id: int) -> StatusResponse:
    """Annule un workflow en cours d'exécution."""
    orchestrator = get_active_workflow(workflow_id)
    if not orchestrator:
        raise HTTPException(404, "Aucun workflow actif avec cet ID.")

    orchestrator.cancel()
    return StatusResponse(status="success", message="Demande d'annulation envoyée.")


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
