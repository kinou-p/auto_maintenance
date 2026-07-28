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

from datetime import datetime, timezone
from backend.core.config import settings
from backend.core.websocket import ws_manager
from backend.managers.ddev_manager import DDEVManager
from backend.managers.hosts_manager import HostsManager
from backend.managers.workflow_orchestrator import get_active_workflow
from backend.models.database import Project, ProjectStatus, Workflow, WorkflowStatus, async_session
from backend.models.schemas import ProjectCreate, ProjectList, ProjectResponse, StatusResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/projects", tags=["projects"])

def _resolve_upload_path_safely(relative_path: str) -> Path:
    """Résout un chemin utilisateur dans uploads_dir en bloquant les traversals."""
    uploads_root = settings.uploads_dir.resolve()
    candidate = (uploads_root / relative_path).resolve()
    if uploads_root != candidate and uploads_root not in candidate.parents:
        raise HTTPException(400, "Chemin de fichier invalide")
    return candidate


async def _save_upload_with_limit(upload: UploadFile, dest: Path) -> int:
    """Écrit un upload sur disque en respectant max_upload_size_mb. Retourne la taille."""
    max_bytes = settings.max_upload_size_bytes
    chunk_size = 1024 * 1024  # 1 Mo
    written = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await upload.read(chunk_size)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"Fichier trop volumineux (max {settings.max_upload_size_mb} Mo)",
                    )
                f.write(chunk)
    finally:
        await upload.close()
    return written


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    name: str = Form(...),
    domain: Optional[str] = Form(None),
    wpress_file: Optional[UploadFile] = File(None),
    local_file_path: Optional[str] = Form(None),
) -> ProjectResponse:
    """
    Crée un nouveau projet de maintenance WordPress.

    - **name**: Nom du projet (alphanumérique, tirets, underscores)
    - **domain**: Domaine local souhaité (ex: monsite.ddev.site)
    - **wpress_file**: Fichier .wpress (upload)
    - **local_file_path**: Chemin relatif vers un fichier .wpress existant dans uploads/ (library)
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
    
    if local_file_path:
        # Utilisation d'un fichier existant
        source_path = _resolve_upload_path_safely(local_file_path)
        if not source_path.exists() or not source_path.is_file():
             raise HTTPException(400, f"Fichier local introuvable : {local_file_path}")
        if not source_path.name.endswith(".wpress"):
             raise HTTPException(400, "Le fichier local doit être un .wpress")
             
        wpress_path = str(source_path)

    elif wpress_file and wpress_file.filename:
        if not wpress_file.filename.endswith(".wpress"):
            raise HTTPException(400, "Le fichier doit être au format .wpress")

        # Sauvegarder directement dans data/uploads/
        # On évite le sous-dossier par projet pour créer une "librairie" commune
        upload_dir = settings.uploads_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_filename = Path(wpress_file.filename).name
        if not safe_filename.endswith(".wpress"):
            raise HTTPException(400, "Nom de fichier upload invalide")
        wpress_dest = upload_dir / safe_filename
        await _save_upload_with_limit(wpress_file, wpress_dest)
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


@router.get("/files", response_model=list[dict])
async def list_wpress_files() -> list[dict]:
    """
    Liste les fichiers .wpress disponibles dans le dossier uploads.
    """
    files = []
    uploads_dir = settings.uploads_dir
    
    if not uploads_dir.exists():
        return []

    # Parcourir récursivement (ou juste les sous-dossiers de niveau 1)
    for path in uploads_dir.rglob("*.wpress"):
        if path.is_file():
            # Chemin relatif pour l'affichage et la sélection
            rel_path = path.relative_to(uploads_dir)
            files.append({
                "path": str(rel_path),
                "name": path.name,
                "size": path.stat().st_size,
                "created": path.stat().st_ctime,
            })
            
    # Trier par date de création (plus récent en premier)
    files.sort(key=lambda x: x["created"], reverse=True)
    return files
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
            
            # Sauvegarder le fichier .wpress directement dans data/uploads/
            upload_dir = settings.uploads_dir
            upload_dir.mkdir(parents=True, exist_ok=True)
            safe_filename = Path(wpress_file.filename).name
            if not safe_filename.endswith(".wpress"):
                errors.append({
                    "file": wpress_file.filename,
                    "error": "Nom de fichier upload invalide"
                })
                continue
            wpress_dest = upload_dir / safe_filename
            try:
                await _save_upload_with_limit(wpress_file, wpress_dest)
            except HTTPException as exc:
                errors.append({
                    "file": wpress_file.filename,
                    "error": str(exc.detail),
                })
                continue
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


class BatchLibraryRequest(BaseModel):
    files: list[str]

@router.post("/batch-library", response_model=dict, status_code=201)
async def create_projects_from_library(
    payload: BatchLibraryRequest,
) -> dict:
    """
    Crée plusieurs projets en batch à partir de fichiers .wpress existants dans la librairie.
    """
    if not payload.files:
        raise HTTPException(400, "Aucun fichier fourni")

    created_projects: list[ProjectResponse] = []
    errors: list[dict] = []

    for filename in payload.files:
        try:
            try:
                source_path = _resolve_upload_path_safely(filename)
            except HTTPException as exc:
                errors.append({
                    "file": filename,
                    "error": str(exc.detail),
                })
                continue
            
            if not source_path.exists() or not source_path.is_file():
                errors.append({
                    "file": filename,
                    "error": "Fichier introuvable"
                })
                continue
                
            if not source_path.name.endswith(".wpress"):
                errors.append({
                    "file": filename,
                    "error": "Le fichier doit être au format .wpress"
                })
                continue

            # Générer le nom
            import re
            name = source_path.name.replace('.wpress', '')
            name = re.sub(r'[^a-zA-Z0-9_-]', '-', name).lower()

            # Vérifier existence projet
            async with async_session() as session:
                existing = await session.execute(
                    select(Project).where(Project.name == name)
                )
                if existing.scalar_one_or_none():
                    errors.append({
                        "file": filename,
                        "error": f"Le projet '{name}' existe déjà"
                    })
                    continue

            domain = f"{name}.ddev.site"
            wpress_path = str(source_path)

            # Créer
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
                "file": filename,
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
        for subdir in ["screenshots", "reports"]:
            data_dir = settings.data_dir / subdir / project_name
            if data_dir.exists():
                shutil.rmtree(data_dir, ignore_errors=True)

        # Suppression sélective dans uploads (garder les .wpress)
        uploads_dir = settings.uploads_dir / project_name
        if uploads_dir.exists():
            # Supprimer tout sauf les .wpress
            for item in uploads_dir.iterdir():
                if item.is_file() and item.suffix == ".wpress":
                    continue
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
            
            # Si le dossier est vide (pas de .wpress), le supprimer
            if not any(uploads_dir.iterdir()):
                uploads_dir.rmdir()

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


class BatchDeleteRequest(BaseModel):
    project_ids: list[int] = Field(..., min_length=1)
    cleanup_ddev: bool = True


@router.post("/batch-delete", response_model=dict, status_code=200)
async def delete_projects_batch(
    payload: BatchDeleteRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Supprime plusieurs projets en batch.
    """
    if not payload.project_ids:
        raise HTTPException(400, "Aucun ID de projet fourni")

    count = 0
    async with async_session() as session:
        result = await session.execute(
            select(Project).where(Project.id.in_(payload.project_ids))
        )
        projects = result.scalars().all()

        for project in projects:
            if project.status == ProjectStatus.DELETING:
                continue

            project.status = ProjectStatus.DELETING
            background_tasks.add_task(
                _delete_project_background,
                project.id,
                project.name,
                project.domain,
                payload.cleanup_ddev,
            )
            count += 1

        await session.commit()

    return {
        "status": "success",
        "message": f"Suppression lancée pour {count} projet(s).",
        "count": count,
    }


@router.post("/{project_id}/stop", response_model=StatusResponse)
async def stop_project(project_id: int) -> StatusResponse:
    """Arrête les conteneurs DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        # 1. Vérifier et annuler les workflows en cours
        running_workflow_result = await session.execute(
            select(Workflow).where(
                Workflow.project_id == project_id,
                Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]),
            )
        )
        workflow = running_workflow_result.scalar_one_or_none()
        
        if workflow:
            # Si un orchestrateur est actif en mémoire
            orchestrator = get_active_workflow(workflow.id)
            if orchestrator:
                orchestrator.cancel()
                # On laisse l'orchestrateur gérer la mise à jour DB et le nettoyage
                
            # Si le workflow est juste en attente (PENDING), on l'annule directement
            elif workflow.status == WorkflowStatus.PENDING:
                workflow.status = WorkflowStatus.CANCELLED
                workflow.completed_at = datetime.now(timezone.utc)
                await session.commit()

        # 2. Arrêter le projet DDEV
        ddev = DDEVManager(project.name)
        result = await ddev.stop()

        if result.success:
            project.status = ProjectStatus.STOPPED
            await session.commit()
            return StatusResponse(status="success", message="Projet arrêté.")

        raise HTTPException(500, f"Impossible d'arrêter le projet : {result.stderr}")


@router.post("/{project_id}/pause", response_model=StatusResponse)
async def pause_project(project_id: int) -> StatusResponse:
    """Met en pause les conteneurs DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        ddev = DDEVManager(project.name)
        result = await ddev.pause()

        if result.success:
            project.status = ProjectStatus.PAUSED
            await session.commit()
            return StatusResponse(status="success", message="Projet mis en pause.")

        raise HTTPException(500, f"Impossible de mettre le projet en pause : {result.stderr}")


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


@router.post("/{project_id}/restart", response_model=StatusResponse)
async def restart_project(project_id: int) -> StatusResponse:
    """Redémarre les conteneurs DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        # Marquer comme initialisation pendant le restart
        project.status = ProjectStatus.INITIALIZING
        await session.commit()

        ddev = DDEVManager(project.name)
        result = await ddev.restart()

        if result.success:
            project.status = ProjectStatus.READY
            await session.commit()
            return StatusResponse(status="success", message="Projet redémarré.")

        # En cas d'erreur, remettre en ERROR
        project.status = ProjectStatus.ERROR
        await session.commit()
        raise HTTPException(500, f"Impossible de redémarrer le projet : {result.stderr}")


@router.get("/{project_id}/status")
async def get_project_status(project_id: int) -> dict:
    """Récupère le statut détaillé d'un projet (infos DDEV incluses) et synchronise le statut BDD."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        ddev = DDEVManager(project.name)
        ddev_status = await ddev.get_status()

        # Réconciliation automatique du statut BDD avec l'état réel DDEV
        transient_statuses = {
            ProjectStatus.INITIALIZING,
            ProjectStatus.IMPORTING,
            ProjectStatus.MAINTENANCE_IN_PROGRESS,
            ProjectStatus.DELETING,
        }
        if project.status not in transient_statuses:
            status_str = ddev_status.get("status", "")
            if status_str == "paused" and project.status != ProjectStatus.PAUSED:
                project.status = ProjectStatus.PAUSED
                await session.commit()
            elif status_str == "stopped" and project.status not in (ProjectStatus.STOPPED, ProjectStatus.CREATED, ProjectStatus.ERROR):
                project.status = ProjectStatus.STOPPED
                await session.commit()
            elif status_str == "running" and project.status in (ProjectStatus.STOPPED, ProjectStatus.PAUSED):
                project.status = ProjectStatus.READY
                await session.commit()

        return {
            "project": ProjectResponse.model_validate(project).model_dump(),
            "ddev": ddev_status,
        }


@router.post("/{project_id}/recreate", response_model=StatusResponse)
async def recreate_project(project_id: int) -> StatusResponse:
    """Recrée complètement l'environnement DDEV d'un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        # Marquer comme initialisation
        project.status = ProjectStatus.INITIALIZING
        await session.commit()

        ddev = DDEVManager(project.name)
        result = await ddev.recreate(project.domain)

        if result.success:
            project.status = ProjectStatus.READY
            await session.commit()
            return StatusResponse(status="success", message="Projet recréé avec succès.")

        # En cas d'erreur
        project.status = ProjectStatus.ERROR
        await session.commit()
        raise HTTPException(500, f"Impossible de recréer le projet : {result.stderr}")


@router.post("/{project_id}/reset", response_model=StatusResponse)
async def reset_project(project_id: int) -> StatusResponse:
    """
    Réinitialise un projet :
    - Arrête et détruit son conteneur DDEV (s'il existe)
    - Supprime ses screenshots, rapports et logs de workflows
    - Remet son statut BDD à 'created' (gardant le projet et son fichier .wpress intacts)
    """
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

        project_name = project.name

        # 1. Annuler les workflows actifs
        running_workflow_result = await session.execute(
            select(Workflow).where(
                Workflow.project_id == project_id,
                Workflow.status.in_([WorkflowStatus.RUNNING, WorkflowStatus.PENDING]),
            )
        )
        for wf in running_workflow_result.scalars().all():
            orchestrator = get_active_workflow(wf.id)
            if orchestrator:
                orchestrator.cancel()
            wf.status = WorkflowStatus.CANCELLED
            wf.completed_at = datetime.now(timezone.utc)

        # 2. Détruire le conteneur DDEV
        ddev = DDEVManager(project_name)
        if await ddev.project_exists():
            await ddev.destroy(remove_files=True)

        # 3. Nettoyer les screenshots et rapports
        for subdir in ["screenshots", "reports"]:
            data_dir = settings.data_dir / subdir / project_name
            if data_dir.exists():
                shutil.rmtree(data_dir, ignore_errors=True)

        # 4. Remettre le statut à CREATED
        project.status = ProjectStatus.CREATED
        await session.commit()

    await ws_manager.broadcast({"type": "queue_updated"})
    return StatusResponse(status="success", message=f"Projet '{project_name}' réinitialisé au statut initial (CREATED).")
