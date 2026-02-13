"""
Auto Maintenance - Routes API Projets.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy import select

from backend.core.config import settings
from backend.core.websocket import ws_manager
from backend.managers.ddev_manager import DDEVManager
from backend.managers.hosts_manager import HostsManager
from backend.models.database import Project, ProjectStatus, async_session
from backend.models.schemas import ProjectCreate, ProjectList, ProjectResponse, StatusResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    name: str = Form(...),
    domain: Optional[str] = Form(None),
    wpress_file: Optional[UploadFile] = File(None),
) -> ProjectResponse:
    """
    Crée un nouveau projet de maintenance WordPress.

    - **name**: Nom du projet (alphanumérique, tirets, underscores)
    - **domain**: Domaine local souhaité (ex: monsite.ddev.site)
    - **wpress_file**: Fichier .wpress (optionnel)
    """
    # Validation du nom
    import re
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        raise HTTPException(400, "Nom de projet invalide (alphanumérique, - et _ uniquement)")

    # Domaine par défaut
    if not domain:
        domain = f"{name}.ddev.site"

    # Vérifier que le projet n'existe pas déjà
    async with async_session() as session:
        existing = await session.execute(
            select(Project).where(Project.name == name)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Le projet '{name}' existe déjà.")

    # Sauvegarder le fichier .wpress si fourni
    wpress_path: Optional[str] = None
    if wpress_file and wpress_file.filename:
        if not wpress_file.filename.endswith(".wpress"):
            raise HTTPException(400, "Le fichier doit être au format .wpress")

        upload_dir = settings.uploads_dir / name
        upload_dir.mkdir(parents=True, exist_ok=True)
        wpress_dest = upload_dir / wpress_file.filename

        with open(wpress_dest, "wb") as f:
            content = await wpress_file.read()
            f.write(content)

        wpress_path = str(wpress_dest)

    # Créer le projet en DB
    async with async_session() as session:
        project = Project(
            name=name,
            domain=domain,
            status=ProjectStatus.CREATED,
            wpress_file=wpress_path,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        return ProjectResponse.model_validate(project)


@router.post("/batch", response_model=dict, status_code=201)
async def create_projects_batch(
    wpress_files: list[UploadFile] = File(...),
) -> dict:
    """
    Crée plusieurs projets en batch à partir de fichiers .wpress.
    
    Chaque fichier sera traité séquentiellement :
    - Le nom du projet est déduit du nom du fichier
    - Le domaine est auto-généré (nom.ddev.site)
    
    Returns:
        Statut avec liste des projets créés et erreurs éventuelles.
    """
    if not wpress_files:
        raise HTTPException(400, "Aucun fichier fourni")
    
    created_projects: list[ProjectResponse] = []
    errors: list[dict] = []
    
    for wpress_file in wpress_files:
        try:
            # Validation du fichier
            if not wpress_file.filename or not wpress_file.filename.endswith(".wpress"):
                errors.append({
                    "file": wpress_file.filename or "unknown",
                    "error": "Le fichier doit être au format .wpress"
                })
                continue
            
            # Générer le nom du projet depuis le nom du fichier
            import re
            name = wpress_file.filename.replace('.wpress', '')
            name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).lower()
            
            # Vérifier si le projet existe déjà
            async with async_session() as session:
                existing = await session.execute(
                    select(Project).where(Project.name == name)
                )
                if existing.scalar_one_or_none():
                    errors.append({
                        "file": wpress_file.filename,
                        "error": f"Le projet '{name}' existe déjà"
                    })
                    continue
            
            # Domaine auto-généré
            domain = f"{name}.ddev.site"
            
            # Sauvegarder le fichier .wpress
            upload_dir = settings.uploads_dir / name
            upload_dir.mkdir(parents=True, exist_ok=True)
            wpress_dest = upload_dir / wpress_file.filename
            
            # Lire et sauvegarder le contenu
            with open(wpress_dest, "wb") as f:
                content = await wpress_file.read()
                f.write(content)
            
            wpress_path = str(wpress_dest)
            
            # Créer le projet en DB
            async with async_session() as session:
                project = Project(
                    name=name,
                    domain=domain,
                    status=ProjectStatus.CREATED,
                    wpress_file=wpress_path,
                )
                session.add(project)
                await session.commit()
                await session.refresh(project)
                
                created_projects.append(ProjectResponse.model_validate(project))
        
        except Exception as e:
            errors.append({
                "file": wpress_file.filename if wpress_file.filename else "unknown",
                "error": str(e)
            })
    
    return {
        "status": "success" if created_projects else "error",
        "message": f"{len(created_projects)} projet(s) créé(s), {len(errors)} erreur(s)",
        "created": [p.model_dump() for p in created_projects],
        "errors": errors,
    }


@router.get("/", response_model=ProjectList)
async def list_projects() -> ProjectList:
    """Liste tous les projets."""
    async with async_session() as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()))
        projects = result.scalars().all()

        return ProjectList(
            projects=[ProjectResponse.model_validate(p) for p in projects],
            total=len(projects),
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int) -> ProjectResponse:
    """Récupère les détails d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")
        return ProjectResponse.model_validate(project)


async def _delete_project_background(project_id: int, project_name: str, domain: str, cleanup_ddev: bool = True) -> None:
    """
    Supprime un projet en arrière-plan avec notifications WebSocket.
    """
    try:
        await ws_manager.broadcast({
            "type": "project_deletion",
            "project_id": project_id,
            "status": "started",
            "message": f"Début de la suppression du projet '{project_name}'..."
        })

        # Supprimer le projet DDEV
        if cleanup_ddev:
            await ws_manager.broadcast({
                "type": "project_deletion",
                "project_id": project_id,
                "status": "progress",
                "message": "Suppression de l'environnement DDEV..."
            })
            ddev = DDEVManager(project_name)
            if await ddev.project_exists():
                await ddev.destroy(remove_files=True)

        # Supprimer l'entrée DNS
        await ws_manager.broadcast({
            "type": "project_deletion",
            "project_id": project_id,
            "status": "progress",
            "message": "Suppression de l'entrée DNS..."
        })
        hosts = HostsManager()
        await hosts.remove_entry(domain)

        # Supprimer les données locales
        await ws_manager.broadcast({
            "type": "project_deletion",
            "project_id": project_id,
            "status": "progress",
            "message": "Suppression des données locales..."
        })
        for subdir in ["screenshots", "reports", "uploads"]:
            data_dir = settings.data_dir / subdir / project_name
            if data_dir.exists():
                shutil.rmtree(data_dir, ignore_errors=True)

        # Supprimer de la DB
        async with async_session() as session:
            project = await session.get(Project, project_id)
            if project:
                await session.delete(project)
                await session.commit()

        await ws_manager.broadcast({
            "type": "project_deletion",
            "project_id": project_id,
            "status": "completed",
            "message": f"Projet '{project_name}' supprimé avec succès."
        })

    except Exception as e:
        # En cas d'erreur, marquer le projet comme ERROR au lieu de le supprimer
        async with async_session() as session:
            project = await session.get(Project, project_id)
            if project:
                project.status = ProjectStatus.ERROR
                await session.commit()

        await ws_manager.broadcast({
            "type": "project_deletion",
            "project_id": project_id,
            "status": "failed",
            "message": f"Erreur lors de la suppression : {str(e)}"
        })


@router.delete("/{project_id}", response_model=StatusResponse)
async def delete_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    cleanup_ddev: bool = True
) -> StatusResponse:
    """
    Supprime un projet et ses ressources en arrière-plan.

    - **cleanup_ddev**: Supprimer aussi le projet DDEV (default: true)
    """
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        if project.status == ProjectStatus.DELETING:
            raise HTTPException(409, f"Le projet '{project.name}' est déjà en cours de suppression.")

        project_name = project.name
        domain = project.domain

        # Marquer le projet comme en cours de suppression
        project.status = ProjectStatus.DELETING
        await session.commit()

    # Lancer la suppression en arrière-plan
    background_tasks.add_task(_delete_project_background, project_id, project_name, domain, cleanup_ddev)

    return StatusResponse(
        status="success",
        message=f"Suppression du projet '{project_name}' lancée en arrière-plan."
    )


@router.post("/{project_id}/stop", response_model=StatusResponse)
async def stop_project(project_id: int) -> StatusResponse:
    """Arrête les conteneurs DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        ddev = DDEVManager(project.name)
        result = await ddev.stop()

        if result.success:
            project.status = ProjectStatus.STOPPED
            await session.commit()
            return StatusResponse(status="success", message="Projet arrêté.")

        raise HTTPException(500, f"Impossible d'arrêter le projet : {result.stderr}")


@router.post("/{project_id}/start", response_model=StatusResponse)
async def start_project(project_id: int) -> StatusResponse:
    """Démarre les conteneurs DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        ddev = DDEVManager(project.name)
        result = await ddev.start()

        if result.success:
            project.status = ProjectStatus.READY
            await session.commit()
            return StatusResponse(status="success", message="Projet démarré.")

        raise HTTPException(500, f"Impossible de démarrer le projet : {result.stderr}")


@router.get("/{project_id}/status")
async def get_project_status(project_id: int) -> dict:
    """Récupère le statut détaillé d'un projet (infos DDEV incluses)."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        ddev = DDEVManager(project.name)
        ddev_status = await ddev.get_status()

        return {
            "project": ProjectResponse.model_validate(project).model_dump(),
            "ddev": ddev_status,
        }
