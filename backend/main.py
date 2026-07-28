"""
Auto Maintenance - Point d'entrée FastAPI.

Application principale avec :
- Routes REST pour projets, workflows, mises à jour et VRT
- WebSocket pour logs temps réel
- Middleware CORS pour le frontend React
- Montage des fichiers statiques (screenshots, rapports)
"""

from __future__ import annotations

import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.projects import router as projects_router
from backend.api.updates_vrt import router as updates_vrt_router
from backend.api.workflows import router as workflows_router
from backend.api.system import router as system_router
from backend.core.config import settings
from backend.core.websocket import ws_manager
from backend.models.database import init_db


# ── Logging ───────────────────────────────────────────────────────
def setup_logging() -> None:
    """Configure le logging applicatif."""
    log_format = (
        '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
        if settings.log_format == "json"
        else "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ── Lifecycle ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gère le cycle de vie de l'application."""
    setup_logging()
    logger = logging.getLogger("auto_maintenance")
    logger.info("Initialisation de l'application...")

    # Créer les répertoires nécessaires
    for directory in [
        settings.data_dir,
        settings.screenshots_dir,
        settings.reports_dir,
        settings.uploads_dir,
        settings.ddev_projects_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    # Initialiser la base de données
    await init_db()
    logger.info("Base de données initialisée.")

    # Relancer la file d'attente (reprise des workflows PENDING)
    from backend.managers.queue_manager import queue_manager
    import asyncio
    asyncio.create_task(queue_manager.process_queue())
    logger.info("File d'attente des workflows démarrée.")

    logger.info(f"Application démarrée sur {settings.app_host}:{settings.app_port}")
    yield

    logger.info("Arrêt de l'application.")


# ── Application FastAPI ───────────────────────────────────────────
app = FastAPI(
    title="Auto Maintenance - WordPress Maintenance Automation",
    description=(
        "Application locale pour automatiser la maintenance de sites WordPress.\n\n"
        "Fonctionnalités :\n"
        "- Création de projets DDEV\n"
        "- Installation et import WordPress (.wpress)\n"
        "- Mises à jour WordPress (core, plugins, thèmes)\n"
        "- Visual Regression Testing (screenshots avant/après)\n"
        "- Logs temps réel via WebSocket"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routeurs API ──────────────────────────────────────────────────
app.include_router(projects_router, prefix="/api")
app.include_router(workflows_router, prefix="/api")
app.include_router(updates_vrt_router, prefix="/api")
app.include_router(system_router, prefix="/api")

# ── Fichiers statiques ───────────────────────────────────────────
# Monter le dossier data pour servir screenshots et rapports
app.mount(
    "/static/data",
    StaticFiles(directory=str(settings.data_dir)),
    name="data",
)


# ── WebSocket ─────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_global(websocket: WebSocket) -> None:
    """WebSocket pour recevoir tous les logs en temps réel."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Garder la connexion ouverte
            data = await websocket.receive_text()
            # On peut recevoir des commandes du client ici
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/{project_id}")
async def websocket_project(websocket: WebSocket, project_id: int) -> None:
    """WebSocket pour recevoir les logs d'un projet spécifique."""
    await ws_manager.connect(websocket, project_id)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, project_id)


# ── Health check ──────────────────────────────────────────────────
@app.get("/api/health")
async def health_check() -> dict:
    """Vérifie que l'API est opérationnelle."""
    from backend.utils.command import run_command

    ddev_installed = False
    docker_running = False

    ddev_result = await run_command("ddev --version", timeout=5)
    ddev_installed = ddev_result.success or "ddev" in ddev_result.stdout.lower() or shutil.which("ddev") is not None

    docker_result = await run_command("docker info", timeout=5)
    docker_running = docker_result.success

    return {
        "status": "healthy",
        "version": "1.0.0",
        "checks": {
            "ddev_installed": ddev_installed,
            "docker_running": docker_running,
        },
    }


# ── Setup sudoers (endpoint one-time) ────────────────────────────
@app.post("/api/setup/sudoers")
async def setup_sudoers() -> dict:
    """Configure les permissions sudoers pour /etc/hosts (one-time)."""
    from backend.managers.hosts_manager import HostsManager

    success = await HostsManager.setup_sudoers()
    if success:
        return {"status": "success", "message": "Permissions sudoers configurées."}
    return {"status": "error", "message": "Échec de la configuration sudoers."}


@app.post("/api/system/ddev-reset")
async def global_ddev_reset() -> dict:
    """Arrête tous les projets DDEV et les services partagés (power-off)."""
    from backend.utils.command import run_command
    
    # ddev power-off arrête tous les projets et le routeur
    result = await run_command("ddev power-off", timeout=60)
    
    if result.success:
        return {"status": "success", "message": "DDEV a été réinitialisé (power-off)."}
    
    return {"status": "error", "message": f"Échec de la réinitialisation : {result.stderr}"}
