"""
Base class partagée pour les sous-managers WordPress.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from backend.core.websocket import WorkflowLogger
from backend.managers.ddev_manager import DDEVManager


class WPBaseManager:
    """Classe de base fournissant les accès communs à DDEV, au logger et au dossier projet."""

    def __init__(
        self,
        project_name: str,
        ddev: DDEVManager,
        logger: Optional[WorkflowLogger] = None,
    ) -> None:
        self.project_name = project_name
        self.ddev = ddev
        self.project_dir = ddev.project_dir
        self.logger = logger

    async def _log(self, level: str, message: str, step: str = "wp_install") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)
