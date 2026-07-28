"""
Auto Maintenance - Gestionnaire de logs temps réel via WebSocket.

Fournit un système de logging structuré JSON qui diffuse les messages
aux clients WebSocket connectés en temps réel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket


class ConnectionManager:
    """Gère les connexions WebSocket actives par projet."""

    def __init__(self) -> None:
        # project_id -> set de WebSocket
        self._connections: dict[int, set[WebSocket]] = {}
        # Connexions globales (reçoivent tous les messages)
        self._global_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, project_id: Optional[int] = None) -> None:
        """Accepte et enregistre une connexion WebSocket."""
        await websocket.accept()
        async with self._lock:
            if project_id is not None:
                if project_id not in self._connections:
                    self._connections[project_id] = set()
                self._connections[project_id].add(websocket)
            else:
                self._global_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket, project_id: Optional[int] = None) -> None:
        """Retire une connexion WebSocket."""
        async with self._lock:
            if project_id is not None and project_id in self._connections:
                self._connections[project_id].discard(websocket)
                if not self._connections[project_id]:
                    del self._connections[project_id]
            else:
                self._global_connections.discard(websocket)

    async def send_to_project(self, project_id: int, message: dict[str, Any]) -> None:
        """Envoie un message JSON à tous les clients d'un projet."""
        data = json.dumps(message, ensure_ascii=False, default=str)
        dead: list[WebSocket] = []

        # Clients du projet
        for ws in self._connections.get(project_id, set()):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)

        # Clients globaux
        for ws in self._global_connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)

        # Nettoyage des connexions mortes
        for ws in dead:
            await self.disconnect(ws, project_id)
            await self.disconnect(ws, None)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Envoie un message à toutes les connexions."""
        data = json.dumps(message, ensure_ascii=False, default=str)
        all_ws: set[WebSocket] = set(self._global_connections)
        for conns in self._connections.values():
            all_ws.update(conns)

        dead: list[WebSocket] = []
        for ws in all_ws:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._global_connections.discard(ws)
            for conns in self._connections.values():
                conns.discard(ws)


# Singleton global
ws_manager = ConnectionManager()


class WorkflowLogger:
    """
    Logger structuré pour un workflow.

    Chaque message est :
    - Loggé via le module logging standard
    - Diffusé en temps réel via WebSocket
    - Stocké en mémoire pour insertion DB ultérieure
    """

    def __init__(self, project_id: int, workflow_id: int) -> None:
        self.project_id = project_id
        self.workflow_id = workflow_id
        self._logs: list[dict[str, Any]] = []
        self._logger = logging.getLogger(f"workflow.{project_id}.{workflow_id}")
        self.on_log: Optional[Any] = None


    def _build_message(
        self,
        level: str,
        message: str,
        step: Optional[str] = None,
        details: Optional[dict] = None,
        progress: Optional[float] = None,
    ) -> dict[str, Any]:
        return {
            "type": "log",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "step": step,
            "message": message,
            "details": details,
            "progress": progress,
            "project_id": self.project_id,
            "workflow_id": self.workflow_id,
        }

    async def _emit(
        self,
        level: str,
        message: str,
        step: Optional[str] = None,
        details: Optional[dict] = None,
        progress: Optional[float] = None,
    ) -> None:
        msg = self._build_message(level, message, step, details, progress)
        self._logs.append(msg)

        # Log standard
        log_fn = getattr(self._logger, level if level != "success" else "info")
        log_fn(message, extra={"step": step, "details": details})

        # WebSocket
        await ws_manager.send_to_project(self.project_id, msg)

        # Callback console / CLI direct
        if self.on_log:
            try:
                self.on_log(msg)
            except Exception:
                pass


    async def info(self, message: str, step: Optional[str] = None, **kwargs: Any) -> None:
        await self._emit("info", message, step, kwargs.get("details"), kwargs.get("progress"))

    async def success(self, message: str, step: Optional[str] = None, **kwargs: Any) -> None:
        await self._emit("success", message, step, kwargs.get("details"), kwargs.get("progress"))

    async def warning(self, message: str, step: Optional[str] = None, **kwargs: Any) -> None:
        await self._emit("warning", message, step, kwargs.get("details"), kwargs.get("progress"))

    async def error(self, message: str, step: Optional[str] = None, **kwargs: Any) -> None:
        await self._emit("error", message, step, kwargs.get("details"), kwargs.get("progress"))

    async def debug(self, message: str, step: Optional[str] = None, **kwargs: Any) -> None:
        await self._emit("debug", message, step, kwargs.get("details"), kwargs.get("progress"))

    async def progress(self, step: str, progress: float, message: str = "") -> None:
        """Envoie une mise à jour de progression."""
        msg = {
            "type": "progress",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": self.project_id,
            "workflow_id": self.workflow_id,
            "step": step,
            "progress": progress,
            "message": message,
        }
        await ws_manager.send_to_project(self.project_id, msg)

    def get_logs(self) -> list[dict[str, Any]]:
        """Retourne tous les logs collectés."""
        return list(self._logs)
