"""
Auto Maintenance - DDEV Manager.

Gère le cycle de vie des projets DDEV :
création, démarrage, arrêt, suppression, et statut.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.utils.command import CommandResult, run_command, run_ddev_command


class DDEVManager:
    """Orchestre les opérations DDEV pour un projet WordPress."""

    def __init__(self, project_name: str, logger: Optional[WorkflowLogger] = None) -> None:
        self.project_name = project_name
        self.project_dir = settings.ddev_projects_dir / project_name
        self.logger = logger

    async def _log(self, level: str, message: str, step: str = "ddev_create") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)

    # ── Vérifications ─────────────────────────────────────────────

    async def check_ddev_installed(self) -> bool:
        """Vérifie que DDEV est installé et accessible."""
        result = await run_command("ddev version", timeout=10)
        if not result.success and "permission denied" in (result.stderr or "").lower():
            await self._log(
                "error",
                "DDEV est installé mais Docker n'est pas accessible. "
                "Vérifiez que votre utilisateur est dans le groupe 'docker' : "
                "sudo usermod -aG docker $USER (puis re-login).",
            )
        return result.success

    async def check_docker_running(self) -> bool:
        """Vérifie que Docker est en cours d'exécution."""
        result = await run_command("docker info", timeout=10)
        return result.success

    async def project_exists(self) -> bool:
        """Vérifie si le projet DDEV existe déjà."""
        config_path = self.project_dir / ".ddev" / "config.yaml"
        return config_path.exists()

    # ── Cycle de vie ──────────────────────────────────────────────

    async def create_project(self, domain: Optional[str] = None) -> CommandResult:
        """
        Crée un nouveau projet DDEV configuré pour WordPress.

        Args:
            domain: Domaine personnalisé (ex: monsite.ddev.site).

        Returns:
            CommandResult du ddev config.
        """
        await self._log("info", f"Création du projet DDEV '{self.project_name}'...")

        # Vérifier les prérequis
        if not await self.check_ddev_installed():
            await self._log("error", "DDEV n'est pas installé ou inaccessible.")
            return CommandResult(
                returncode=1, stdout="", stderr="DDEV non installé", command="ddev version"
            )

        if not await self.check_docker_running():
            await self._log("error", "Docker n'est pas en cours d'exécution.")
            return CommandResult(
                returncode=1, stdout="", stderr="Docker non démarré", command="docker info"
            )

        # Créer le répertoire du projet
        self.project_dir.mkdir(parents=True, exist_ok=True)
        await self._log("info", f"Répertoire créé : {self.project_dir}")

        # Configurer DDEV
        fqdn = domain or f"{self.project_name}.ddev.site"
        # Ajouter le domaine original ET le domaine .ddev.site comme FQDNs
        # pour que les assets référençant l'ancien domaine soient servis localement
        ddev_fqdn = f"{self.project_name}.ddev.site"
        fqdns = set([fqdn, ddev_fqdn])
        fqdns_str = ",".join(fqdns)
        config_cmd = (
            f"ddev config"
            f" --project-type=wordpress"
            f" --project-name={self.project_name}"
            f" --php-version={settings.ddev_php_version}"
            f" --webserver-type={settings.ddev_webserver_type}"
            f" --database=mariadb:{settings.ddev_mariadb_version}"
            f" --additional-fqdns={fqdns_str}"
            f" --docroot=."
            f" --upload-dirs=wp-content/uploads"
        )

        result = await run_ddev_command(config_cmd, str(self.project_dir))

        if result.success:
            await self._log("success", f"Projet DDEV configuré avec succès (domaine: {fqdn})")
            # Écrire une config supplémentaire pour augmenter les limites PHP
            await self._write_php_config()
        else:
            await self._log("error", f"Échec de la configuration DDEV : {result.stderr}")

        return result

    async def _write_php_config(self) -> None:
        """Écrit une configuration PHP personnalisée pour les gros imports."""
        php_ini_dir = self.project_dir / ".ddev" / "php"
        php_ini_dir.mkdir(parents=True, exist_ok=True)
        php_ini = php_ini_dir / "custom.ini"
        php_ini.write_text(
            "[PHP]\n"
            "upload_max_filesize = 2G\n"
            "post_max_size = 2G\n"
            "memory_limit = 512M\n"
            "max_execution_time = 600\n"
            "max_input_time = 600\n"
            "max_input_vars = 5000\n"
        )
        await self._log("info", "Configuration PHP personnalisée appliquée (upload 2G, memory 512M)")

    async def start(self) -> CommandResult:
        """Démarre les conteneurs DDEV du projet."""
        await self._log("info", f"Démarrage des conteneurs DDEV...")
        result = await run_ddev_command("ddev start", str(self.project_dir), timeout=180)

        if result.success:
            await self._log("success", "Conteneurs DDEV démarrés avec succès.")
        else:
            await self._log("error", f"Échec du démarrage DDEV : {result.stderr}")

        return result

    async def stop(self) -> CommandResult:
        """Arrête les conteneurs DDEV du projet."""
        await self._log("info", "Arrêt des conteneurs DDEV...")
        result = await run_ddev_command("ddev stop", str(self.project_dir), timeout=60)

        if result.success:
            await self._log("success", "Conteneurs DDEV arrêtés.")
        else:
            await self._log("warning", f"Problème à l'arrêt DDEV : {result.stderr}")

        return result

    async def destroy(self, remove_files: bool = False) -> CommandResult:
        """
        Supprime le projet DDEV.

        Args:
            remove_files: Si True, supprime aussi les fichiers du projet.
        """
        await self._log("warning", f"Suppression du projet DDEV '{self.project_name}'...")

        cmd = "ddev delete -Oy"
        result = await run_ddev_command(cmd, str(self.project_dir), timeout=60)

        if result.success and remove_files and self.project_dir.exists():
            shutil.rmtree(self.project_dir, ignore_errors=True)
            await self._log("info", "Fichiers du projet supprimés.")

        if result.success:
            await self._log("success", "Projet DDEV supprimé.")
        else:
            await self._log("error", f"Échec de la suppression : {result.stderr}")

        return result

    async def restart(self) -> CommandResult:
        """Redémarre les conteneurs DDEV."""
        await self._log("info", "Redémarrage DDEV...")
        result = await run_ddev_command("ddev restart", str(self.project_dir), timeout=180)

        if result.success:
            await self._log("success", "DDEV redémarré.")
        else:
            await self._log("error", f"Échec du redémarrage : {result.stderr}")

        return result

    async def get_status(self) -> dict:
        """Récupère le statut du projet DDEV."""
        result = await run_ddev_command(
            "ddev describe -j", str(self.project_dir), timeout=15
        )
        if result.success:
            import json
            try:
                data = json.loads(result.stdout)
                return {
                    "running": True,
                    "data": data,
                    "urls": data.get("raw", {}).get("urls", []),
                }
            except json.JSONDecodeError:
                pass
        return {"running": False, "data": None, "urls": []}

    async def get_url(self) -> str:
        """Retourne l'URL principale du projet DDEV."""
        status = await self.get_status()
        urls = status.get("urls", [])
        # Préférer https
        for url in urls:
            if url.startswith("https://"):
                return url
        return urls[0] if urls else f"https://{self.project_name}.ddev.site"

    async def exec_in_container(self, command: str, timeout: int = 60) -> CommandResult:
        """Exécute une commande dans le conteneur web DDEV."""
        return await run_ddev_command(
            f"ddev exec {command}", str(self.project_dir), timeout=timeout
        )

    async def copy_to_container(self, local_path: str, container_path: str) -> CommandResult:
        """Copie un fichier local dans le conteneur DDEV."""
        await self._log("info", f"Copie de {local_path} vers le conteneur...")
        # Utiliser docker cp via ddev
        result = await run_command(
            f"docker cp {local_path} ddev-{self.project_name}-web:{container_path}",
            timeout=300
        )
        if result.success:
            await self._log("success", f"Fichier copié dans le conteneur ({container_path})")
        else:
            await self._log("error", f"Échec de la copie : {result.stderr}")
        return result
