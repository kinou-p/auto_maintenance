"""
Auto Maintenance - API Système pour la gestion globale des containers DDEV.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from sqlalchemy import select

from backend.utils.command import run_command, run_ddev_command
from backend.core.config import settings
from backend.models.database import Project, ProjectStatus, async_session
from backend.api.projects import _delete_project_background
from backend.core.websocket import ws_manager

router = APIRouter(tags=["system"])


async def get_dir_size_fast(path: Path, max_depth: int = 2, current_depth: int = 0) -> int:
    """Calcule la taille d'un répertoire avec une profondeur limitée pour la rapidité."""
    if current_depth > max_depth or not path.exists():
        return 0
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file(follow_symlinks=False):
                total += entry.stat().st_size
            elif entry.is_dir(follow_symlinks=False) and current_depth < max_depth:
                total += await get_dir_size_fast(Path(entry.path), max_depth, current_depth + 1)
    except Exception:
        pass
    return total


async def _sync_project_status_by_name(name: str, new_status: ProjectStatus) -> None:
    """Met à jour le statut du projet en BDD si un projet correspondant existe."""
    async with async_session() as session:
        result = await session.execute(
            select(Project).where(Project.name == name)
        )
        project = result.scalar_one_or_none()
        if project and project.status != ProjectStatus.DELETING:
            project.status = new_status
            await session.commit()


@router.get("/system/containers")
async def list_containers() -> List[Dict[str, Any]]:
    """Liste tous les projets DDEV du système et fait le lien avec la BDD."""
    result = await run_command("ddev list -j", timeout=30)
    if not result.success:
        raise HTTPException(status_code=500, detail=f"Échec de la liste DDEV : {result.stderr}")
    
    # Récupérer les projets BDD pour le mapping project_id
    project_map: dict[str, int] = {}
    async with async_session() as session:
        db_projects = (await session.execute(select(Project))).scalars().all()
        for p in db_projects:
            project_map[p.name] = p.id

    try:
        data = json.loads(result.stdout)
        raw_list = data.get("raw", [])
        
        containers = []
        for item in raw_list:
            approot = Path(item.get("approot", ""))
            name = item.get("name", "")
            size_bytes = 0
            if approot.exists():
                size_bytes = await get_dir_size_fast(approot)

            containers.append({
                "name": name,
                "project_id": project_map.get(name),
                "status": item.get("status"),
                "php_version": item.get("php_version"),
                "db_type": item.get("db_type"),
                "db_version": item.get("db_version"),
                "url": item.get("httpsurl") or item.get("httpurl") or item.get("primary_url"),
                "approot": str(approot),
                "storage_bytes": size_bytes,
                "type": item.get("type"),
                "router": item.get("router"),
            })
        return containers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de parsing des données DDEV : {str(e)}")


@router.post("/system/containers/{name}/start")
async def start_container(name: str):
    """Démarre un container DDEV spécifique et synchronise le projet BDD."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev start", container["approot"], timeout=180)
    if result.success:
        await _sync_project_status_by_name(name, ProjectStatus.READY)
        return {"status": "success", "message": f"Projet {name} démarré"}
    raise HTTPException(status_code=500, detail=result.stderr)


@router.post("/system/containers/{name}/stop")
async def stop_container(name: str):
    """Arrête un container DDEV spécifique et synchronise le projet BDD."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev stop", container["approot"], timeout=60)
    if result.success:
        await _sync_project_status_by_name(name, ProjectStatus.STOPPED)
        return {"status": "success", "message": f"Projet {name} arrêté"}
    raise HTTPException(status_code=500, detail=result.stderr)


@router.post("/system/containers/{name}/pause")
async def pause_container(name: str):
    """Met en pause un container DDEV spécifique et synchronise le projet BDD."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev pause", container["approot"], timeout=60)
    if result.success:
        await _sync_project_status_by_name(name, ProjectStatus.PAUSED)
        return {"status": "success", "message": f"Projet {name} mis en pause"}
    raise HTTPException(status_code=500, detail=result.stderr)


@router.post("/system/containers/{name}/restart")
async def restart_container(name: str):
    """Redémarre un container DDEV spécifique et synchronise le projet BDD."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev restart", container["approot"], timeout=180)
    if result.success:
        await _sync_project_status_by_name(name, ProjectStatus.READY)
        return {"status": "success", "message": f"Projet {name} redémarré"}
    raise HTTPException(status_code=500, detail=result.stderr)


@router.delete("/system/containers/{name}")
async def delete_container(name: str, background_tasks: BackgroundTasks):
    """Supprime un container DDEV et nettoie le projet en BDD s'il existe."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    # Vérifier si un projet correspondant existe en BDD
    async with async_session() as session:
        result = await session.execute(
            select(Project).where(Project.name == name)
        )
        project = result.scalar_one_or_none()
        if project:
            project.status = ProjectStatus.DELETING
            await session.commit()
            background_tasks.add_task(_delete_project_background, project.id, project.name, project.domain, True)
            return {"status": "success", "message": f"Nettoyage complet et suppression du projet '{name}' lancés en arrière-plan"}

    # Si pas de projet en BDD, supprimer simplement le container DDEV
    result = await run_ddev_command("ddev delete -Oy", container["approot"], timeout=120)
    if result.success:
        return {"status": "success", "message": f"Projet DDEV {name} supprimé"}
    raise HTTPException(status_code=500, detail=result.stderr)


@router.post("/system/ddev-reset")
async def reset_ddev_global():
    """Effectue un poweroff global DDEV (arrête tous les conteneurs DDEV)."""
    result = await run_command("ddev poweroff", timeout=60)
    if result.success:
        # Passer tous les projets en statut STOPPED
        async with async_session() as session:
            db_projects = (await session.execute(select(Project))).scalars().all()
            for p in db_projects:
                if p.status not in (ProjectStatus.CREATED, ProjectStatus.DELETING, ProjectStatus.ERROR):
                    p.status = ProjectStatus.STOPPED
            await session.commit()

        await ws_manager.broadcast({"type": "queue_updated"})
        return {"status": "success", "message": "Environnement DDEV réinitialisé avec succès (power-off global)."}
    raise HTTPException(status_code=500, detail=f"Échec du reset DDEV : {result.stderr}")
