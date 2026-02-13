"""
Auto Maintenance - WordPress Manager.

Gère l'installation de WordPress, les plugins, l'import de fichiers .wpress,
les mises à jour et les opérations WP-CLI via DDEV.
"""

from __future__ import annotations

import asyncio
import httpx
import shutil
import time
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.managers.ddev_manager import DDEVManager
from backend.models.schemas import UpdateItem, UpdateResult
from backend.utils.command import CommandResult, run_command, run_wp_cli


class WordPressManager:
    """Gère toutes les opérations WordPress via WP-CLI et DDEV."""

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

    # ── Installation WordPress ────────────────────────────────────

    async def download_wordpress(self) -> CommandResult:
        """Télécharge WordPress (version FR) avec cache local pour éviter les re-téléchargements."""
        locale = settings.wp_locale
        cache_dir = settings.wp_cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Déterminer le préfixe de langue (fr_FR -> fr)
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
            # Télécharger depuis wordpress.org
            base_url = f"https://{lang_prefix}.wordpress.org" if lang_prefix else "https://wordpress.org"
            url = f"{base_url}/{tarball_name}"
            await self._log("info", f"Téléchargement de WordPress ({locale}) depuis {base_url}...")

            result = await run_command(
                f'curl -fSL -o "{cached_tarball}" "{url}"',
                timeout=120,
            )
            if not result.success:
                await self._log("error", f"Échec du téléchargement WordPress : {result.stderr}")
                return result
            await self._log("success", "WordPress téléchargé et mis en cache.")

        # Extraire dans le répertoire du projet
        await self._log("info", "Extraction de WordPress dans le projet...")
        result = await run_command(
            f'tar -xzf "{cached_tarball}" --strip-components=1 -C "{self.project_dir}"',
            timeout=60,
        )

        if result.success:
            await self._log("success", "WordPress extrait avec succès.")
        else:
            await self._log("error", f"Échec de l'extraction WordPress : {result.stderr}")

        return result

    async def create_config(self) -> CommandResult:
        """Crée le fichier wp-config.php avec les credentials DDEV."""
        await self._log("info", "Création de wp-config.php...")

        # DDEV utilise des credentials standard
        result = await run_wp_cli(
            "config create"
            " --dbname=db"
            " --dbuser=db"
            " --dbpass=db"
            " --dbhost=db"
            " --force",
            str(self.project_dir),
        )

        if result.success:
            await self._log("success", "wp-config.php créé avec les credentials DDEV.")
        else:
            await self._log("error", f"Échec de la création wp-config.php : {result.stderr}")

        return result

    async def install_wordpress(self, domain: str) -> CommandResult:
        """
        Installe WordPress avec des credentials temporaires.

        Args:
            domain: Domaine du site (ex: monsite.ddev.site).
        """
        await self._log("info", "Installation de WordPress...")

        url = f"https://{domain}"
        result = await run_wp_cli(
            f'core install'
            f' --url="{url}"'
            f' --title="Site en maintenance"'
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
        """
        Effectue l'installation complète de WordPress.

        Returns:
            True si toutes les étapes ont réussi.
        """
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

    # ── Plugins ───────────────────────────────────────────────────

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

        # Copier le ZIP dans le conteneur
        container_zip = "/tmp/aio-wp-migration.zip"
        copy_result = await self.ddev.copy_to_container(str(zip_path), container_zip)
        if not copy_result.success:
            return copy_result

        # Installer via WP-CLI
        result = await run_wp_cli(
            f"plugin install {container_zip} --activate --force",
            str(self.project_dir),
        )

        if result.success:
            await self._log("success", "Plugin AIO WP Migration installé et activé.", step="plugin_install")
        else:
            await self._log("error", f"Échec installation plugin : {result.stderr}", step="plugin_install")

        return result

    # ── Import .wpress ────────────────────────────────────────────

    async def import_wpress(self, wpress_path: str) -> bool:
        """
        Importe un fichier .wpress via WP-CLI ou fallback Playwright.

        Args:
            wpress_path: Chemin local du fichier .wpress.

        Returns:
            True si l'import a réussi.
        """
        await self._log("info", f"Import du fichier .wpress : {wpress_path}", step="wpress_import")

        # Vérifier que le fichier existe
        if not Path(wpress_path).exists():
            await self._log("error", f"Fichier .wpress introuvable : {wpress_path}", step="wpress_import")
            return False

        # Copier le fichier dans le conteneur
        container_path = "/var/www/html/wp-content/ai1wm-backups/"
        await self.ddev.exec_in_container(f"mkdir -p {container_path}")
        filename = Path(wpress_path).name
        copy_result = await self.ddev.copy_to_container(wpress_path, f"{container_path}{filename}")

        if not copy_result.success:
            await self._log("error", "Échec de la copie du fichier .wpress", step="wpress_import")
            return False

        # Tenter l'import via WP-CLI
        await self._log("info", "Tentative d'import via WP-CLI...", step="wpress_import")
        result = await run_wp_cli(
            f"ai1wm restore {filename} --yes",
            str(self.project_dir),
            timeout=600,
        )

        if result.success:
            await self._log("success", "Import .wpress réussi via WP-CLI.", step="wpress_import")
            await self._post_import_cleanup()
            return True

        # Fallback : import via Playwright (interface web)
        await self._log(
            "warning",
            "WP-CLI a échoué, tentative d'import via l'interface web (Playwright)...",
            step="wpress_import",
        )

        playwright_success = await self._import_via_playwright(wpress_path)

        if playwright_success:
            await self._log("success", "Import .wpress réussi via Playwright.", step="wpress_import")
            await self._post_import_cleanup()
            return True

        await self._log("error", "Échec de l'import .wpress (WP-CLI et Playwright).", step="wpress_import")
        return False

    async def _import_via_playwright(self, wpress_path: str) -> bool:
        """
        Fallback : simule l'import via l'interface web avec Playwright.
        """
        try:
            from playwright.async_api import async_playwright

            site_url = await self.ddev.get_url()

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(ignore_https_errors=True)
                page = await context.new_page()

                # Se connecter à l'admin WordPress
                await page.goto(f"{site_url}/wp-login.php", wait_until="networkidle")
                await page.fill("#user_login", settings.wp_admin_user)
                await page.fill("#user_pass", settings.wp_admin_password)
                await page.click("#wp-submit")
                await page.wait_for_load_state("networkidle")

                # Aller sur la page d'import AIO
                await page.goto(
                    f"{site_url}/wp-admin/admin.php?page=ai1wm_import",
                    wait_until="networkidle",
                )

                # Upload du fichier
                file_input = await page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(wpress_path)

                    # Attendre la fin de l'import (timeout 10 minutes)
                    await page.wait_for_selector(
                        ".ai1wm-import-done, .ai1wm-button-done",
                        timeout=600000,
                    )

                    # Cliquer sur le bouton de confirmation si présent
                    done_btn = await page.query_selector(".ai1wm-button-done")
                    if done_btn:
                        await done_btn.click()

                    await browser.close()
                    return True

                await browser.close()
                return False

        except Exception as e:
            await self._log("error", f"Erreur Playwright : {e}", step="wpress_import")
            return False

    async def _post_import_cleanup(self) -> None:
        """Opérations post-import : search-replace URLs, permaliens, cache, restart."""
        await self._log("info", "Nettoyage post-import...", step="wpress_import")

        # ── 1. Récupérer l'ancienne URL du site (celle du backup importé) ──
        old_url_result = await run_wp_cli(
            "option get siteurl", str(self.project_dir)
        )
        old_site_url = old_url_result.stdout.strip() if old_url_result.success else ""

        # URL cible = URL DDEV locale
        new_site_url = await self.ddev.get_url()

        await self._log(
            "info",
            f"[DEBUG] Ancienne URL (backup) : '{old_site_url}' | Nouvelle URL (DDEV) : '{new_site_url}'",
            step="wpress_import",
        )

        # ── 2. Search-replace complet dans toute la base de données ──
        if old_site_url and old_site_url != new_site_url:
            await self._log(
                "info",
                f"Search-replace : {old_site_url} → {new_site_url}",
                step="wpress_import",
            )

            # Remplacer l'URL complète (avec scheme)
            sr_result = await run_wp_cli(
                f'search-replace "{old_site_url}" "{new_site_url}"'
                f' --all-tables --skip-columns=guid --report-changed-only',
                str(self.project_dir),
                timeout=300,
            )
            if sr_result.success:
                await self._log(
                    "success",
                    f"Search-replace terminé.\n{sr_result.stdout.strip()}",
                    step="wpress_import",
                )
            else:
                await self._log(
                    "warning",
                    f"Search-replace (URL complète) a rencontré un problème : {sr_result.stderr}",
                    step="wpress_import",
                )

            # Extraire les domaines (sans scheme) pour couvrir les chemins relatifs
            from urllib.parse import urlparse

            old_domain = urlparse(old_site_url).netloc
            new_domain = urlparse(new_site_url).netloc

            if old_domain and new_domain and old_domain != new_domain:
                await self._log(
                    "info",
                    f"Search-replace domaines : {old_domain} → {new_domain}",
                    step="wpress_import",
                )
                sr_domain_result = await run_wp_cli(
                    f'search-replace "{old_domain}" "{new_domain}"'
                    f' --all-tables --skip-columns=guid --report-changed-only',
                    str(self.project_dir),
                    timeout=300,
                )
                if sr_domain_result.success:
                    await self._log(
                        "success",
                        f"Search-replace domaines terminé.\n{sr_domain_result.stdout.strip()}",
                        step="wpress_import",
                    )
                else:
                    await self._log(
                        "warning",
                        f"Search-replace domaines : {sr_domain_result.stderr}",
                        step="wpress_import",
                    )
        else:
            # Les URLs sont déjà identiques, ou on n'a pas pu lire l'ancienne
            # Forcer quand même une mise à jour des options siteurl/home
            await run_wp_cli(
                f'option update siteurl "{new_site_url}"', str(self.project_dir)
            )
            await run_wp_cli(
                f'option update home "{new_site_url}"', str(self.project_dir)
            )
            await self._log(
                "info",
                f"URLs du site mises à jour : {new_site_url}",
                step="wpress_import",
            )

        # ── 3. Purger les fichiers de cache sur le disque (WP Fastest Cache, etc.) ──
        await self._log("info", "Purge des caches fichiers (WP Fastest Cache, etc.)...", step="wpress_import")
        cache_dirs = [
            "wp-content/cache",
            "wp-content/wp-fastest-cache",
            "wp-content/cache/wpfc-minified",
            "wp-content/cache/wp-rocket",
            "wp-content/cache/autoptimize",
            "wp-content/litespeed",
            "wp-content/et-cache",
        ]
        for cache_dir in cache_dirs:
            rm_result = await self.ddev.exec_in_container(
                f"rm -rf /var/www/html/{cache_dir}/* 2>/dev/null; echo ok"
            )
            if rm_result.success:
                # Vérifier si le dossier existait
                check = await self.ddev.exec_in_container(
                    f"test -d /var/www/html/{cache_dir} && echo exists || echo missing"
                )
                if "exists" in check.stdout:
                    await self._log(
                        "info",
                        f"Cache purgé : {cache_dir}",
                        step="wpress_import",
                    )

        # Désactiver WP Fastest Cache temporairement pour éviter qu'il recrache les caches avec les anciennes URLs
        await run_wp_cli(
            'option update WpFastestCache ""',
            str(self.project_dir),
        )
        await self._log("info", "WP Fastest Cache désactivé (options vidées).", step="wpress_import")

        # ── 4. Vider le cache objet WP et les transients ──
        await run_wp_cli("cache flush", str(self.project_dir))
        await run_wp_cli("transient delete --all", str(self.project_dir))
        await self._log("info", "Cache objet et transients vidés.", step="wpress_import")

        # ── 5. Régénérer les permaliens ──
        await run_wp_cli("rewrite flush --hard", str(self.project_dir))
        await self._log("info", "Permaliens régénérés.", step="wpress_import")

        # ── 6. Vérifier les URLs finales en DB après toutes les opérations ──
        final_siteurl = await run_wp_cli("option get siteurl", str(self.project_dir))
        final_home = await run_wp_cli("option get home", str(self.project_dir))
        await self._log(
            "info",
            f"[DEBUG] URLs finales en DB → siteurl: '{final_siteurl.stdout.strip()}' | home: '{final_home.stdout.strip()}'",
            step="wpress_import",
        )

        # Vérifier le thème actif et l'URL du stylesheet
        theme_result = await run_wp_cli("theme list --status=active --format=json", str(self.project_dir))
        await self._log(
            "info",
            f"[DEBUG] Thème actif : {theme_result.stdout.strip()}",
            step="wpress_import",
        )

        # ── 8. Vérifier que le site répond correctement ──
        await self._log("info", "Vérification de l'accessibilité du site...", step="wpress_import")
        max_retries = 8
        site_accessible = False
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                    response = await client.get(new_site_url)
                    # Vérifier que le site répond ET que le HTML contient des assets CSS
                    if response.status_code == 200:
                        body = response.text
                        has_css = '<link' in body and ('stylesheet' in body or '.css' in body)
                        # Log les premiers tags <link> pour debug
                        import re
                        css_links = re.findall(r'<link[^>]*stylesheet[^>]*href=["\']([^"\']+)["\']', body)
                        if css_links:
                            await self._log(
                                "info",
                                f"[DEBUG] CSS trouvés dans le HTML ({len(css_links)}) : {css_links[:3]}",
                                step="wpress_import",
                            )
                        else:
                            # Chercher tous les <link> pour comprendre
                            all_links = re.findall(r'<link[^>]*>', body[:3000])
                            await self._log(
                                "warning",
                                f"[DEBUG] Aucun CSS stylesheet trouvé. Tags <link> présents : {all_links[:5]}",
                                step="wpress_import",
                            )
                            # Log les premiers 500 caractères du HTML
                            await self._log(
                                "warning",
                                f"[DEBUG] Début du HTML : {body[:500]}",
                                step="wpress_import",
                            )
                        if has_css:
                            await self._log(
                                "success",
                                "Site accessible avec CSS chargé correctement.",
                                step="wpress_import",
                            )
                            site_accessible = True
                            break
                        else:
                            await self._log(
                                "warning",
                                f"Tentative {attempt + 1}/{max_retries} - Site accessible mais CSS non détecté, nouvelle tentative...",
                                step="wpress_import",
                            )
                    else:
                        await self._log(
                            "warning",
                            f"Tentative {attempt + 1}/{max_retries} - Code HTTP {response.status_code}",
                            step="wpress_import",
                        )
            except Exception as e:
                await self._log(
                    "warning",
                    f"Tentative {attempt + 1}/{max_retries} - Erreur : {e}",
                    step="wpress_import",
                )
            await asyncio.sleep(3)

        if not site_accessible:
            await self._log(
                "warning",
                "Le site pourrait ne pas être complètement fonctionnel. "
                "Les screenshots pourraient être affectés.",
                step="wpress_import",
            )

        # ── 9. Stabilisation finale ──
        await self._log("info", "Stabilisation du site (5s)...", step="wpress_import")
        await asyncio.sleep(5)

    # ── Mises à jour ──────────────────────────────────────────────

    async def list_updates(self) -> dict:
        """
        Liste toutes les mises à jour disponibles (Core, Plugins, Thèmes).

        Returns:
            Dict avec les mises à jour triées par type.
        """
        await self._log("info", "Vérification des mises à jour disponibles...", step="updates_list")

        result: dict = {"core": None, "plugins": [], "themes": [], "total_available": 0}

        # Core
        core_result = await run_wp_cli(
            "core check-update --format=json", str(self.project_dir)
        )
        if core_result.success and core_result.stdout.strip():
            import json
            try:
                core_updates = json.loads(core_result.stdout)
                if core_updates:
                    update = core_updates[0]
                    current = await run_wp_cli("core version", str(self.project_dir))
                    result["core"] = UpdateItem(
                        name="wordpress",
                        type="core",
                        current_version=current.stdout.strip(),
                        new_version=update.get("version", ""),
                        status="available",
                    )
                    result["total_available"] += 1
            except (json.JSONDecodeError, IndexError):
                pass

        # Plugins
        plugins_result = await run_wp_cli(
            "plugin list --update=available --format=json", str(self.project_dir)
        )
        if plugins_result.success and plugins_result.stdout.strip():
            import json
            try:
                plugins = json.loads(plugins_result.stdout)
                for p in plugins:
                    result["plugins"].append(UpdateItem(
                        name=p.get("name", ""),
                        type="plugin",
                        current_version=p.get("version", ""),
                        new_version=p.get("update_version", ""),
                        status="available",
                    ))
                result["total_available"] += len(plugins)
            except json.JSONDecodeError:
                pass

        # Thèmes
        themes_result = await run_wp_cli(
            "theme list --update=available --format=json", str(self.project_dir)
        )
        if themes_result.success and themes_result.stdout.strip():
            import json
            try:
                themes = json.loads(themes_result.stdout)
                for t in themes:
                    result["themes"].append(UpdateItem(
                        name=t.get("name", ""),
                        type="theme",
                        current_version=t.get("version", ""),
                        new_version=t.get("update_version", ""),
                        status="available",
                    ))
                result["total_available"] += len(themes)
            except json.JSONDecodeError:
                pass

        await self._log(
            "info",
            f"{result['total_available']} mise(s) à jour disponible(s).",
            step="updates_list",
        )

        return result

    async def apply_updates(
        self,
        update_core: bool = False,
        plugin_names: list[str] | None = None,
        theme_names: list[str] | None = None,
    ) -> list[UpdateResult]:
        """
        Applique les mises à jour sélectionnées.

        Args:
            update_core: Mettre à jour WordPress core.
            plugin_names: Liste de plugins à mettre à jour.
            theme_names: Liste de thèmes à mettre à jour.

        Returns:
            Liste des résultats de mise à jour.
        """
        await self._log("info", "Application des mises à jour...", step="updates_apply")
        results: list[UpdateResult] = []

        # Core
        if update_core:
            await self._log("info", "Mise à jour du core WordPress...", step="updates_apply")
            current = await run_wp_cli("core version", str(self.project_dir))
            core_result = await run_wp_cli("core update", str(self.project_dir), timeout=180)
            new_version = await run_wp_cli("core version", str(self.project_dir))

            results.append(UpdateResult(
                name="wordpress",
                type="core",
                success=core_result.success,
                message=core_result.stdout if core_result.success else core_result.stderr,
                old_version=current.stdout.strip(),
                new_version=new_version.stdout.strip() if core_result.success else None,
            ))

            # Mettre à jour la base de données après update core
            if core_result.success:
                await run_wp_cli("core update-db", str(self.project_dir))

        # Plugins
        for plugin_name in (plugin_names or []):
            await self._log("info", f"Mise à jour du plugin : {plugin_name}", step="updates_apply")
            # Récupérer la version actuelle
            info_result = await run_wp_cli(
                f"plugin get {plugin_name} --field=version", str(self.project_dir)
            )
            old_version = info_result.stdout.strip() if info_result.success else "unknown"

            update_result = await run_wp_cli(
                f"plugin update {plugin_name}", str(self.project_dir), timeout=120
            )

            new_info = await run_wp_cli(
                f"plugin get {plugin_name} --field=version", str(self.project_dir)
            )

            results.append(UpdateResult(
                name=plugin_name,
                type="plugin",
                success=update_result.success,
                message=update_result.stdout if update_result.success else update_result.stderr,
                old_version=old_version,
                new_version=new_info.stdout.strip() if update_result.success else None,
            ))

        # Thèmes
        for theme_name in (theme_names or []):
            await self._log("info", f"Mise à jour du thème : {theme_name}", step="updates_apply")
            info_result = await run_wp_cli(
                f"theme get {theme_name} --field=version", str(self.project_dir)
            )
            old_version = info_result.stdout.strip() if info_result.success else "unknown"

            update_result = await run_wp_cli(
                f"theme update {theme_name}", str(self.project_dir), timeout=120
            )

            new_info = await run_wp_cli(
                f"theme get {theme_name} --field=version", str(self.project_dir)
            )

            results.append(UpdateResult(
                name=theme_name,
                type="theme",
                success=update_result.success,
                message=update_result.stdout if update_result.success else update_result.stderr,
                old_version=old_version,
                new_version=new_info.stdout.strip() if update_result.success else None,
            ))

        # Résumé
        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        await self._log(
            "success" if fail_count == 0 else "warning",
            f"Mises à jour terminées : {success_count} réussie(s), {fail_count} échouée(s).",
            step="updates_apply",
        )

        # Vider le cache après les mises à jour
        await run_wp_cli("cache flush", str(self.project_dir))

        return results

    # ── Utilitaires ───────────────────────────────────────────────

    async def get_site_urls(self) -> list[str]:
        """
        Récupère les URLs principales du site pour les screenshots.

        Returns:
            Liste d'URLs : accueil, premier article, page contact.
        """
        site_url = await self.ddev.get_url()
        urls = [site_url]  # Accueil

        # Premier article
        posts_result = await run_wp_cli(
            'post list --post_type=post --post_status=publish --posts_per_page=1 --field=url',
            str(self.project_dir),
        )
        if posts_result.success and posts_result.stdout.strip():
            urls.append(posts_result.stdout.strip().split("\n")[0])

        # Page Contact ou première page
        contact_result = await run_wp_cli(
            'post list --post_type=page --post_status=publish --name=contact --field=url',
            str(self.project_dir),
        )
        if contact_result.success and contact_result.stdout.strip():
            urls.append(contact_result.stdout.strip().split("\n")[0])
        else:
            # Première page disponible
            page_result = await run_wp_cli(
                'post list --post_type=page --post_status=publish --posts_per_page=1 --field=url',
                str(self.project_dir),
            )
            if page_result.success and page_result.stdout.strip():
                first_page = page_result.stdout.strip().split("\n")[0]
                if first_page not in urls:
                    urls.append(first_page)

        return urls

    async def get_page_info(self) -> list[dict]:
        """
        Récupère toutes les pages WordPress publiées pour les screenshots.

        Returns:
            Liste de dict avec url, name, type.
        """
        site_url = await self.ddev.get_url()
        pages: list[dict] = []

        # Page d'accueil
        pages.append({"url": site_url, "name": "accueil", "type": "home"})

        # Récupérer toutes les pages publiées
        page_result = await run_wp_cli(
            'post list --post_type=page --post_status=publish'
            ' --fields=ID,post_title,post_name --format=json',
            str(self.project_dir),
        )
        if page_result.success and page_result.stdout.strip():
            import json
            try:
                all_pages = json.loads(page_result.stdout)
                for pg in all_pages:
                    url_result = await run_wp_cli(
                        f"post get {pg['ID']} --field=url", str(self.project_dir)
                    )
                    url = url_result.stdout.strip() if url_result.success else f"{site_url}/?page_id={pg['ID']}"
                    name = pg.get("post_name", f"page-{pg['ID']}")
                    pages.append({"url": url, "name": name, "type": "page"})
            except (json.JSONDecodeError, KeyError):
                pass

        # Récupérer les articles publiés (limité à 10 max)
        posts_result = await run_wp_cli(
            'post list --post_type=post --post_status=publish'
            ' --fields=ID,post_title,post_name --format=json',
            str(self.project_dir),
        )
        if posts_result.success and posts_result.stdout.strip():
            import json
            try:
                all_posts = json.loads(posts_result.stdout)
                for post in all_posts[:10]:
                    url_result = await run_wp_cli(
                        f"post get {post['ID']} --field=url", str(self.project_dir)
                    )
                    url = url_result.stdout.strip() if url_result.success else f"{site_url}/?p={post['ID']}"
                    name = post.get("post_name", f"post-{post['ID']}")
                    pages.append({"url": url, "name": name, "type": "post"})
            except (json.JSONDecodeError, KeyError):
                pass

        await self._log(
            "info",
            f"{len(pages)} page(s) WordPress trouvée(s) pour les screenshots.",
            step="wp_install"
        )

        return pages

    async def is_wordpress_installed(self) -> bool:
        """Vérifie si WordPress est installé dans le projet."""
        result = await run_wp_cli("core is-installed", str(self.project_dir))
        return result.success
