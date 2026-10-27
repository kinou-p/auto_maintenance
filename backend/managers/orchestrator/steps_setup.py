"""
Auto Maintenance - Étapes de Setup et Provisioning (DDEV, DNS, WP, Import).
"""

from __future__ import annotations

from typing import Optional

from backend.managers.orchestrator.exceptions import StepError
from backend.models.database import Project, ProjectStatus, async_session


class WorkflowSetupStepsMixin:
    """Mixin pour les étapes d'infrastructure et d'installation de WordPress."""

    async def _step_ddev_create(self, domain: str) -> None:
        """Étape 1 : Création du projet DDEV."""
        assert self._ddev is not None
        result = await self._ddev.create_project(domain)
        if not result.success:
            raise StepError(f"Impossible de créer le projet DDEV : {result.stderr}")

        result = await self._ddev.start()
        if not result.success:
            raise StepError(f"Impossible de démarrer DDEV : {result.stderr}")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.INITIALIZING
                project.ddev_dir = str(self._ddev.project_dir)
                await session.commit()

    async def _step_dns_setup(self, domain: str) -> None:
        """Étape 2 : Configuration DNS locale."""
        assert self._hosts is not None
        success = await self._hosts.add_entry(domain)
        if not success:
            await self.logger.warning(
                "Impossible de modifier /etc/hosts. "
                "Utilisez DDEV qui gère le DNS automatiquement.",
                step="dns_setup",
            )
            # Non-bloquant : DDEV gère le DNS via dnsmasq

    async def _step_wp_install(self, domain: str) -> None:
        """Étape 3 : Installation WordPress."""
        assert self._wp is not None
        success = await self._wp.full_install(domain)
        if not success:
            raise StepError("Échec de l'installation WordPress.")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.WORDPRESS_INSTALLED
                await session.commit()

    async def _step_plugin_install(self) -> None:
        """Étape 4 : Installation du plugin AIO WP Migration."""
        assert self._wp is not None
        result = await self._wp.install_aio_plugin()
        if not result.success:
            await self.logger.warning(
                "Plugin AIO non installé. L'import .wpress pourrait échouer.",
                step="plugin_install",
            )

    async def _step_wpress_import(self, wpress_file: Optional[str]) -> None:
        """Étape 5 : Import du fichier .wpress."""
        if not wpress_file:
            await self.logger.info(
                "Pas de fichier .wpress à importer. Saut de l'étape.",
                step="wpress_import",
            )
            return

        assert self._wp is not None
        success = await self._wp.import_wpress(wpress_file)
        if not success:
            raise StepError("Échec de l'import .wpress.")

        async with async_session() as session:
            project = await session.get(Project, self.project_id)
            if project:
                project.status = ProjectStatus.READY
                await session.commit()
