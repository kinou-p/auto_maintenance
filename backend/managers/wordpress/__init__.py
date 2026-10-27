"""
Package modulaire pour la gestion WordPress via WP-CLI et DDEV.
"""

from __future__ import annotations

from typing import Optional

from backend.core.websocket import WorkflowLogger
from backend.managers.ddev_manager import DDEVManager
from backend.managers.wordpress.wp_base import WPBaseManager
from backend.managers.wordpress.wp_importer import WPImporterMixin
from backend.managers.wordpress.wp_installer import WPInstallerMixin
from backend.managers.wordpress.wp_pages import WPPagesMixin
from backend.managers.wordpress.wp_updates import WPUpdatesMixin


class WordPressManager(
    WPInstallerMixin,
    WPImporterMixin,
    WPUpdatesMixin,
    WPPagesMixin,
    WPBaseManager,
):
    """
    Gestionnaire centralisé des opérations WordPress (installation, import .wpress,
    mises à jour, pages et WP-CLI) découpé en mixins modulaires.
    """

    def __init__(
        self,
        project_name: str,
        ddev: DDEVManager,
        logger: Optional[WorkflowLogger] = None,
    ) -> None:
        super().__init__(project_name=project_name, ddev=ddev, logger=logger)


__all__ = ["WordPressManager"]
