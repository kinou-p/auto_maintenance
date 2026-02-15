"""
Auto Maintenance - API Système pour la gestion globale des containers DDEV.
"""

from fastapi import APIRouter, HTTPException
import os
import json
from pathlib import Path
from typing import List, Dict, Any
from backend.utils.command import run_command, run_ddev_command
from backend.core.config import settings

router = APIRouter(tags=["system"])

async def get_dir_size(path: Path) -> int:
    """Calcule la taille d'un répertoire en octets."""
    total = 0
    try:
        if not path.exists():
            return 0
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += await get_dir_size(Path(entry.path))
    except Exception:
        pass
    return total

@router.get("/system/containers")
async def list_containers() -> List[Dict[str, Any]]:
    """Liste tous les projets DDEV du système."""
    result = await run_command("ddev list -j", timeout=30)
    if not result.success:
        raise HTTPException(status_code=500, detail=f"Échec de la liste DDEV : {result.stderr}")
    
    try:
        data = json.loads(result.stdout)
        raw_list = data.get("raw", [])
        
        containers = []
        for item in raw_list:
            approot = Path(item.get("approot", ""))
            # Taille du dossier (approximative pour le stockage)
            size_bytes = 0
            if approot.exists():
                # On ne calcule que la taille du dossier racine pour aller vite
                # Pour être précis il faudrait ddev describe mais c'est lent
                size_bytes = await get_dir_size(approot)

            containers.append({
                "name": item.get("name"),
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
    """Démarre un container DDEV spécifique."""
    # On a besoin de connaître l'approot pour lancer la commande dans le bon dossier
    # On le récupère via ddev list
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev start", container["approot"], timeout=180)
    if result.success:
        return {"status": "success", "message": f"Projet {name} démarré"}
    raise HTTPException(status_code=500, detail=result.stderr)

@router.post("/system/containers/{name}/stop")
async def stop_container(name: str):
    """Arrête un container DDEV spécifique."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev stop", container["approot"], timeout=60)
    if result.success:
        return {"status": "success", "message": f"Projet {name} arrêté"}
    raise HTTPException(status_code=500, detail=result.stderr)

@router.post("/system/containers/{name}/restart")
async def restart_container(name: str):
    """Redémarre un container DDEV spécifique."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    result = await run_ddev_command("ddev restart", container["approot"], timeout=180)
    if result.success:
        return {"status": "success", "message": f"Projet {name} redémarré"}
    raise HTTPException(status_code=500, detail=result.stderr)

@router.delete("/system/containers/{name}")
async def delete_container(name: str):
    """Supprime un container DDEV (ddev delete)."""
    containers = await list_containers()
    container = next((c for c in containers if c["name"] == name), None)
    if not container:
        raise HTTPException(status_code=404, detail="Container non trouvé")
    
    # ddev delete -Oy : supprimer sans snapshot et confirmer automatiquement
    result = await run_ddev_command("ddev delete -Oy", container["approot"], timeout=120)
    if result.success:
        return {"status": "success", "message": f"Projet {name} supprimé"}
    raise HTTPException(status_code=500, detail=result.stderr)
