"""
Sous-manager pour l'installation, le téléchargement et la configuration de WordPress.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
import httpx

from backend.core.config import settings
from backend.managers.wordpress.wp_base import WPBaseManager
from backend.utils.command import CommandResult, run_wp_cli


class WPInstallerMixin(WPBaseManager):
    """Mixin pour le téléchargement, la création de config et l'installation de WordPress."""

    async def download_wordpress(self) -> CommandResult:
        """Télécharge et extrait WordPress (version FR) de manière 100% cross-platform (Python)."""
        import tarfile

        locale = settings.wp_locale
        cache_dir = settings.wp_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        lang_prefix = locale.split("_")[0] if locale != "en_US" else ""
        tarball_name = f"latest-{locale}.tar.gz" if locale != "en_US" else "latest.tar.gz"
        cached_tarball = cache_dir / tarball_name

        # Vérifier si le cache est valide (< N jours)
        use_cache = False
        if cached_tarball.exists():
            age_days = (time.time() - cached_tarball.stat().st_mtime) / 86400
            if age_days < settings.wp_cache_max_age_days:
                use_cache = True
                await self._log(
                    "info",
                    f"Cache WordPress trouvé ({age_days:.1f} jour(s)), téléchargement ignoré.",
                )
            else:
                await self._log("info", f"Cache WordPress expiré ({age_days:.0f}j), re-téléchargement...")

        if not use_cache:
            base_url = f"https://{lang_prefix}.wordpress.org" if lang_prefix else "https://wordpress.org"
            url = f"{base_url}/{tarball_name}"
            await self._log("info", f"Téléchargement de WordPress ({locale}) depuis {base_url}...")

            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    cached_tarball.write_bytes(response.content)
                await self._log("success", "WordPress téléchargé et mis en cache.")
            except Exception as e:
                err_msg = f"Échec du téléchargement WordPress : {str(e)}"
                await self._log("error", err_msg)
                return CommandResult(returncode=1, stdout="", stderr=err_msg, command=f"download {url}")

        # Nettoyer d'anciens dossiers coeur (wp-includes, wp-admin) pour éviter les incohérences de version PHP
        for sub in ["wp-includes", "wp-admin"]:
            target_sub = self.project_dir / sub
            if target_sub.exists():
                try:
                    shutil.rmtree(target_sub, ignore_errors=True)
                except Exception:
                    pass
        for root_php in self.project_dir.glob("wp-*.php"):
            if root_php.name != "wp-config.php":
                try:
                    root_php.unlink(missing_ok=True)
                except Exception:
                    pass

        # Extraire dans le répertoire du projet avec tarfile (cross-platform)
        await self._log("info", "Extraction de WordPress dans le projet...")
        try:
            with tarfile.open(cached_tarball, "r:gz") as tar:
                members = []
                for member in tar.getmembers():
                    parts = Path(member.name).parts
                    if len(parts) > 1:
                        member.name = str(Path(*parts[1:]))
                        members.append(member)
                tar.extractall(path=self.project_dir, members=members)

            await self._log("success", "WordPress extrait avec succès.")
            return CommandResult(returncode=0, stdout="WordPress extrait", stderr="", command="extract_tarball")
        except Exception as e:
            err_msg = f"Échec de l'extraction WordPress : {str(e)}"
            await self._log("error", err_msg)
            return CommandResult(returncode=1, stdout="", stderr=err_msg, command="extract_tarball")

    async def create_config(self) -> CommandResult:
        """Crée le fichier wp-config.php avec les credentials DDEV."""
        await self._log("info", "Création de wp-config.php...")

        result = await run_wp_cli(
            "config create"
            " --dbname=db"
            " --dbuser=db"
            " --dbpass=db"
            " --dbhost=db"
            " --skip-check"
            " --force",
            str(self.project_dir),
        )

        if result.success:
            await self._log("success", "wp-config.php créé avec les credentials DDEV.")
        else:
            await self._log("error", f"Échec de la création wp-config.php : {result.stderr}")

        return result

    async def install_wordpress(self, domain: str) -> CommandResult:
        """Installe WordPress avec des credentials temporaires."""
        await self._log("info", "Installation de WordPress...")
        await asyncio.sleep(2)

        url = f"https://{domain}"
        result = await run_wp_cli(
            f'core install'
            f' --url="{url}"'
            f' --title="Maintenance"'
            f' --admin_user="{settings.wp_admin_user}"'
            f' --admin_password="{settings.wp_admin_password}"'
            f' --admin_email="{settings.wp_admin_email}"'
            f' --skip-email',
            str(self.project_dir),
        )

        if result.success:
            await self._log("success", f"WordPress installé ({url})")
        else:
            await self._log("error", f"Échec de l'installation WP : {result.stderr}")

        return result

    async def full_install(self, domain: str) -> bool:
        """Effectue l'installation complète de WordPress."""
        steps = [
            ("Téléchargement WordPress", self.download_wordpress),
            ("Création wp-config.php", self.create_config),
            ("Installation WordPress", lambda: self.install_wordpress(domain)),
        ]

        for step_name, step_fn in steps:
            result = await step_fn()
            if not result.success:
                await self._log("error", f"Interruption : {step_name} a échoué.")
                return False

        return True

    async def install_aio_plugin(self) -> CommandResult:
        """Installe All-in-One WP Migration depuis le fichier ZIP local."""
        await self._log("info", "Installation du plugin All-in-One WP Migration...", step="plugin_install")

        zip_path = settings.aio_plugin_zip_path
        if not zip_path.exists():
            await self._log(
                "error",
                f"Fichier ZIP du plugin introuvable : {zip_path}",
                step="plugin_install",
            )
            return CommandResult(
                returncode=1, stdout="", stderr=f"Fichier ZIP introuvable : {zip_path}", command=""
            )

        container_zip = "aio-wp-migration.zip"
        copy_result = await self.ddev.copy_to_container(str(zip_path), container_zip)
        if not copy_result.success:
            return copy_result

        result = await run_wp_cli(
            f"plugin install {container_zip} --activate --force",
            str(self.project_dir),
        )

        (self.project_dir / container_zip).unlink(missing_ok=True)

        if result.success:
            await self._log("success", "Plugin AIO WP Migration installé et activé.", step="plugin_install")
        else:
            await self._log("error", f"Échec installation plugin : {result.stderr}", step="plugin_install")

        return result

    async def is_wordpress_installed(self) -> bool:
        """Vérifie si WordPress est installé."""
        result = await run_wp_cli("core is-installed", str(self.project_dir))
        return result.success
