"""
Auto Maintenance - WordPress Manager.

Gère l'installation de WordPress, les plugins, l'import de fichiers .wpress,
les mises à jour et les opérations WP-CLI via DDEV.
"""

from __future__ import annotations

import asyncio
import json
import re
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

# Cache global des mises à jour (project_name -> (timestamp, result_dict))
_updates_cache: dict[str, tuple[float, dict]] = {}


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
                    # Supprimer le premier composant de dossier (ex: wordpress/wp-includes/... -> wp-includes/...)
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

        # DDEV utilise des credentials standard
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
        """
        Installe WordPress avec des credentials temporaires.

        Args:
            domain: Domaine du site (ex: monsite.ddev.site).
        """
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

        # Copier le ZIP dans le répertoire du projet (monté sur /var/www/html)
        container_zip = "aio-wp-migration.zip"
        copy_result = await self.ddev.copy_to_container(str(zip_path), container_zip)
        if not copy_result.success:
            return copy_result

        # Installer via WP-CLI
        result = await run_wp_cli(
            f"plugin install {container_zip} --activate --force",
            str(self.project_dir),
        )

        # Nettoyer le fichier zip temporaire du projet
        (self.project_dir / container_zip).unlink(missing_ok=True)

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

        # 1. Tentative d'extraction native Python ultra-rapide (5-10 secondes)
        from backend.utils.wpress_extractor import extract_wpress_fast

        await self._log("info", "Extraction ultra-rapide de l'archive .wpress via Python natif...", step="wpress_import")

        async def on_extract_progress(count: int, mb: int, current_fn: str):
            await self._log("info", f"[Extraction Fast] {count} fichiers extraits ({mb} Mo)...", step="wpress_import")

        success_extract = await extract_wpress_fast(wpress_path, self.project_dir, on_progress=on_extract_progress)

        if success_extract:
            await self._log("success", "Extraction des fichiers terminée avec succès en quelques secondes !", step="wpress_import")

            # Importer la BDD SQL si disponible
            sql_files = list(self.project_dir.glob("**/database.sql"))
            if sql_files:
                sql_file = sql_files[0]
                await self._log("info", "Importation de la base de données SQL dans MariaDB...", step="wpress_import")
                rel_sql = sql_file.relative_to(self.project_dir)
                import_res = await run_command(
                    f"ddev import-db --file={rel_sql}",
                    cwd=str(self.project_dir),
                    timeout=300,
                )
                if import_res.success:
                    await self._log("success", "Base de données SQL importée avec succès !", step="wpress_import")
                    sql_file.unlink(missing_ok=True)

                    # Ajuster le table_prefix dans wp-config.php pour les sauvegardes AIO (.wpress)
                    wp_config = self.project_dir / "wp-config.php"
                    if wp_config.exists():
                        content = wp_config.read_text(encoding="utf-8", errors="replace")
                        if "SERVMASK_PREFIX_" not in content:
                            import re
                            content = re.sub(r"\$table_prefix\s*=\s*['\"][^'\"]+['\"];", "$table_prefix = 'SERVMASK_PREFIX_';", content)
                            wp_config.write_text(content, encoding="utf-8")
                            await self._log("info", "Prefixe de table ajusté à 'SERVMASK_PREFIX_' dans wp-config.php.", step="wpress_import")

            return await self._post_import_cleanup()

        # 2. Fallback WP-CLI si l'extraction native ne s'applique pas
        container_path = "/var/www/html/wp-content/ai1wm-backups/"
        await self.ddev.exec_in_container(f"mkdir -p {container_path}")
        filename = Path(wpress_path).name
        copy_result = await self.ddev.copy_to_container(wpress_path, f"{container_path}{filename}")

        if not copy_result.success:
            await self._log("error", "Échec de la copie du fichier .wpress", step="wpress_import")
            return False

        file_size_bytes = Path(wpress_path).stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)
        cli_timeout = max(1800, int(900 + (file_size_mb / 1000) * 600))
        
        await self._log(
            "info",
            f"Tentative d'import via WP-CLI ({file_size_mb:.1f} Mo, timeout: {cli_timeout}s)...",
            step="wpress_import",
        )
        async def on_restore_output(line: str) -> None:
            clean = line.strip()
            if clean:
                await self._log("info", f"[AIO] {clean}", step="wpress_import")

        result = await run_wp_cli(
            f"ai1wm restore {filename} --yes",
            str(self.project_dir),
            timeout=cli_timeout,
            on_output=on_restore_output,
        )

        if result.success:
            await self._log("success", "Import .wpress réussi via WP-CLI.", step="wpress_import")
            return await self._post_import_cleanup()

        # Fallback : import via Playwright (interface web)
        await self._log(
            "warning",
            "WP-CLI a échoué, tentative d'import via l'interface web (Playwright)...",
            step="wpress_import",
        )

        playwright_success = await self._import_via_playwright(wpress_path)

        if playwright_success:
            await self._log("success", "Import .wpress réussi via Playwright.", step="wpress_import")
            return await self._post_import_cleanup()

        await self._log("error", "Échec de l'import .wpress (WP-CLI et Playwright).", step="wpress_import")
        return False

    async def _import_via_playwright(self, wpress_path: str) -> bool:
        """
        Fallback : simule l'import via l'interface web avec Playwright.
        """
        try:
            import sys
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass
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

    async def _post_import_cleanup(self) -> bool:
        """Opérations post-import : search-replace URLs, permaliens, cache, restart."""
        await self._log("info", "Nettoyage post-import...", step="wpress_import")

        # ── 1. Récupérer l'ancienne URL du site (celle du backup importé) ──
        old_url_result = await run_wp_cli(
            "option get siteurl", str(self.project_dir)
        )
        old_site_url = old_url_result.stdout.strip() if old_url_result.success else ""

        # Fallback SQL direct si WP-CLI n'a pas pu lire l'option
        if not old_site_url:
            sql_url_res = await self.ddev.exec_in_container(
                "mysql -u db -pdb db -N -e \"SELECT option_value FROM SERVMASK_PREFIX_options WHERE option_name='siteurl' LIMIT 1;\" 2>/dev/null || mysql -u db -pdb db -N -e \"SELECT option_value FROM wp_options WHERE option_name='siteurl' LIMIT 1;\" 2>/dev/null"
            )
            if sql_url_res.success and sql_url_res.stdout.strip():
                old_site_url = sql_url_res.stdout.strip()

        # URL cible = URL DDEV locale
        new_site_url = await self.ddev.get_url()

        await self._log(
            "info",
            f"[DEBUG] Ancienne URL (backup) : '{old_site_url}' | Nouvelle URL (DDEV) : '{new_site_url}'",
            step="wpress_import",
        )

        # Assurer la mise à jour directe en DB des options siteurl et home
        if new_site_url:
            await self.ddev.exec_in_container(
                f"mysql -u db -pdb db -e \"UPDATE SERVMASK_PREFIX_options SET option_value='{new_site_url}' WHERE option_name IN ('siteurl', 'home');\" 2>/dev/null || mysql -u db -pdb db -e \"UPDATE wp_options SET option_value='{new_site_url}' WHERE option_name IN ('siteurl', 'home');\" 2>/dev/null"
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
                f' --all-tables --skip-columns=guid --report-changed-only --skip-plugins --skip-themes',
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

            # Extraire les domaines et ports
            from urllib.parse import urlparse

            old_parsed = urlparse(old_site_url)
            new_parsed = urlparse(new_site_url)
            
            old_domain = old_parsed.netloc
            new_domain = new_parsed.netloc
            new_port = new_parsed.port

            if old_domain and new_domain and old_domain != new_domain:
                await self._log(
                    "info",
                    f"Search-replace domaines : {old_domain} → {new_domain}",
                    step="wpress_import",
                )
                
                # Si on ajoute juste un port (ex: domain.com -> domain.com:33000)
                # On doit utiliser une regex pour éviter le double port (domain.com:33000:33000)
                # car le remplacement complet d'URL a déjà ajouté le port sur les URLs absolues.
                use_regex = False
                search_term = old_domain
                
                if new_port and old_domain == new_parsed.hostname:
                    import re
                    # Regex : old_domain non suivi par :new_port
                    # Note : on échappe les points pour la regex PHP
                    escaped_domain = re.escape(old_domain)
                    search_term = f"{escaped_domain}(?!:{new_port})"
                    use_regex = True
                    await self._log("info", f"Utilisation de regex pour éviter double port : {search_term}", step="wpress_import")

                cmd = (
                    f'search-replace "{search_term}" "{new_domain}"'
                    f' --all-tables --skip-columns=guid --report-changed-only --skip-plugins --skip-themes'
                )
                if use_regex:
                    cmd += " --regex"

                sr_domain_result = await run_wp_cli(
                    cmd,
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

        # ── 5b. S'assurer que le index.php racine est valide (non écrasé par un index.php de thème) ──
        root_index = self.project_dir / "index.php"
        if root_index.exists():
            content = root_index.read_text(encoding="utf-8", errors="replace")
            if "wp-blog-header.php" not in content:
                wp_index_standard = (
                    "<?php\n"
                    "/** Front to the WordPress application. */\n"
                    "define( 'WP_USE_THEMES', true );\n"
                    "require __DIR__ . '/wp-blog-header.php';\n"
                )
                root_index.write_text(wp_index_standard, encoding="utf-8")
                await self._log("info", "Fichier index.php racine réparé avec succès.", step="wpress_import")

        # ── 5c. Désactiver les plugins conflictuels (masquage d'admin, SSL forcé, etc.) ──
        conflict_plugins = [
            "wps-hide-login",
            "hide-my-wp",
            "rename-wp-login",
            "lockdown-wp-admin",
            "invisible-recaptcha",
            "really-simple-ssl",
            "wp-force-ssl",
            "wordpress-https",
        ]
        deact_cmd = f"plugin deactivate {' '.join(conflict_plugins)} --skip-plugins --skip-themes"
        await run_wp_cli(deact_cmd, str(self.project_dir))
        await self._log("info", "Plugins de masquage admin & SSL forcé désactivés pour l'environnement local.", step="wpress_import")

        # ── 5d. Régénérer un fichier .htaccess standard WordPress ──
        htaccess_file = self.project_dir / ".htaccess"
        standard_htaccess = (
            "# BEGIN WordPress\n"
            "<IfModule mod_rewrite.c>\n"
            "RewriteEngine On\n"
            "RewriteRule ^index\\.php$ - [L]\n"
            "RewriteCond %{REQUEST_FILENAME} !-f\n"
            "RewriteCond %{REQUEST_FILENAME} !-d\n"
            "RewriteRule . /index.php [L]\n"
            "</IfModule>\n"
            "# END WordPress\n"
        )
        try:
            htaccess_file.write_text(standard_htaccess, encoding="utf-8")
            await self._log("info", "Fichier .htaccess réinitialisé au format standard WordPress.", step="wpress_import")
        except Exception as e:
            await self._log("warning", f"Impossible d'écrire le fichier .htaccess : {e}", step="wpress_import")

        # ── 5e. Nettoyer les extensions en double et activer les extensions du site ──

        unlimited_dir = self.project_dir / "wp-content" / "plugins" / "all-in-one-wp-migration-unlimited-main"
        if unlimited_dir.exists():
            shutil.rmtree(unlimited_dir, ignore_errors=True)

        act_result = await run_wp_cli("plugin activate --all", str(self.project_dir))
        if act_result.success:
            await self._log("info", "Extensions du site activées avec succès.", step="wpress_import")
        else:
            await self._log("warning", f"Activation globale partielle (certaines extensions incompatibles PHP 8+), activation plugin par plugin...", step="wpress_import")
            # Tenter d'activer chaque plugin individuellement
            plugins_res = await run_wp_cli("plugin list --field=name --skip-plugins --skip-themes", str(self.project_dir))
            if plugins_res.success:
                import re
                slug_regex = re.compile(r"^[a-zA-Z0-9_\-]+$")
                p_names = [p.strip() for p in plugins_res.stdout.splitlines() if p.strip() and slug_regex.match(p.strip())]
                activated_count = 0
                failed_count = 0
                for p_name in p_names:
                    res = await run_wp_cli(f"plugin activate {p_name}", str(self.project_dir), timeout=15)
                    if res.success:
                        activated_count += 1
                    else:
                        failed_count += 1
                        # Désactiver pour éviter de faire planter les appels WP-CLI ultérieurs
                        await run_wp_cli(f"plugin deactivate {p_name}", str(self.project_dir))
                        await self._log("warning", f"⚠️ Extension '{p_name}' désactivée (incompatible PHP 8+ / Fatal Error).", step="wpress_import")
                await self._log("info", f"Activation individuelle terminée : {activated_count} activée(s), {failed_count} ignorée(s).", step="wpress_import")





        # ── 6. Vérifier les URLs finales en DB après toutes les opérations ──
        final_siteurl = await run_wp_cli("option get siteurl", str(self.project_dir))
        final_home = await run_wp_cli("option get home", str(self.project_dir))
        await self._log(
            "info",
            f"[DEBUG] URLs finales en DB → siteurl: '{final_siteurl.stdout.strip()}' | home: '{final_home.stdout.strip()}'",
            step="wpress_import",
        )

        # Vérifier le thème actif et activer un thème par défaut si aucun n'est actif
        theme_result = await run_wp_cli("theme list --status=active --format=json", str(self.project_dir))
        active_themes = []
        try:
            active_themes = json.loads(theme_result.stdout)
        except Exception:
            pass

        await self._log(
            "info",
            f"[DEBUG] Thème actif : {active_themes} | WP-CLI stdout: '{theme_result.stdout.strip()[:100]}'",
            step="wpress_import",
        )

        if not active_themes:
            await self._log(
                "warning",
                "⚠️ Aucun thème actif détecté en DB après l'importation. Activation d'un thème valide...",
                step="wpress_import",
            )

            # Trouver les thèmes disponibles dans le système de fichiers
            themes_dir = self.project_dir / "wp-content" / "themes"
            fs_themes = []
            if themes_dir.exists():
                fs_themes = [d.name for d in themes_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

            # Préférer les thèmes custom (non twentytwenty*)
            custom_fs = [t for t in fs_themes if not t.startswith("twenty")]
            candidate_fs = custom_fs if custom_fs else fs_themes

            # Essai 1 : via WP-CLI
            wp_activated = False
            all_themes_res = await run_wp_cli("theme list --format=json", str(self.project_dir))
            try:
                all_themes = json.loads(all_themes_res.stdout)
                custom_themes = [t for t in all_themes if not t.get("name", "").startswith("twenty")]
                candidate_themes = custom_themes if custom_themes else all_themes
                if candidate_themes:
                    fallback_theme = candidate_themes[0].get("name")
                    if fallback_theme:
                        activate_res = await run_wp_cli(f"theme activate {fallback_theme}", str(self.project_dir))
                        if activate_res.success:
                            await self._log("success", f"Thème '{fallback_theme}' activé via WP-CLI.", step="wpress_import")
                            wp_activated = True
                        else:
                            await self._log("warning", f"WP-CLI theme activate échoué : {activate_res.stderr[:200]}", step="wpress_import")
            except Exception as e:
                await self._log("warning", f"WP-CLI theme list échoué : {e}", step="wpress_import")

            # Essai 2 : fallback SQL direct si WP-CLI a échoué
            if not wp_activated and candidate_fs:
                fallback_theme = candidate_fs[0]
                await self._log("info", f"Fallback SQL : activation du thème '{fallback_theme}' directement en DB...", step="wpress_import")
                try:
                    # Lire le préfixe depuis wp-config.php
                    table_prefix = "SERVMASK_PREFIX_"
                    wp_config = self.project_dir / "wp-config.php"
                    if wp_config.exists():
                        for line in wp_config.read_text(encoding="utf-8", errors="ignore").splitlines():
                            if "table_prefix" in line and "=" in line:
                                m = re.search(r"""table_prefix\s*=\s*['"]([^'"]+)['"]""", line)
                                if m:
                                    table_prefix = m.group(1)
                                    break
                    sql_stylesheet = f"UPDATE `{table_prefix}options` SET option_value='{fallback_theme}' WHERE option_name='stylesheet';"
                    sql_template = f"UPDATE `{table_prefix}options` SET option_value='{fallback_theme}' WHERE option_name='template';"
                    for sql in [sql_stylesheet, sql_template]:
                        res = await self.ddev.exec_command(f"mysql -uroot -proot db -e \"{sql}\"")
                        await self._log("info", f"SQL thème [{table_prefix}]: rc={res.returncode}", step="wpress_import")
                    await self._log("success", f"Thème '{fallback_theme}' forcé en DB via SQL.", step="wpress_import")
                except Exception as e:
                    await self._log("warning", f"Fallback SQL thème échoué : {e}", step="wpress_import")


        # ── 8. Vérifier que le site répond correctement ──
        # On utilise `ddev exec curl` depuis le container web DDEV (pas httpx depuis le backend)
        # car *.ddev.site résout vers 127.0.0.1 qui est le localhost du container backend,
        # pas le router DDEV sur l'hôte Docker.

        await self._log("info", "Vérification de l'accessibilité du site...", step="wpress_import")
        max_retries = 8
        site_accessible = False
        for attempt in range(max_retries):
            try:
                # Curl depuis l'intérieur du container DDEV web — pas de problème de routage
                curl_result = await self.ddev.exec_in_container(
                    "curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://localhost/ 2>/dev/null || echo 000"
                )
                http_code_str = (curl_result.stdout or "").strip().strip("'\"")
                http_code = int(http_code_str) if http_code_str.isdigit() else 0

                if http_code in (200, 301, 302, 303):
                    await self._log(
                        "success",
                        f"Site accessible avec succès (HTTP {http_code} via ddev exec curl).",
                        step="wpress_import",
                    )
                    site_accessible = True
                    break
                elif http_code == 502 and attempt == 3:
                    await self._log(
                        "warning",
                        "Détection persistante d'une erreur 502. Tentative de redémarrage de DDEV...",
                        step="wpress_import",
                    )
                    await self.ddev.restart()
                    await asyncio.sleep(5)
                else:
                    await self._log(
                        "warning",
                        f"Tentative {attempt + 1}/{max_retries} - Code HTTP {http_code}",
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
                "Le site n'a pas répondu correctement après plusieurs tentatives — continuation du workflow (screenshots possiblement vides).",
                step="wpress_import",
            )
            # On ne bloque plus le workflow sur ce check : les screenshots et mises à jour peuvent quand même être effectuées

        # ── 9. Stabilisation finale ──
        await self._log("info", "Stabilisation du site (5s)...", step="wpress_import")
        await asyncio.sleep(5)
        return True

    # ── Mises à jour ──────────────────────────────────────────────

    async def list_updates(self, use_cache: bool = True) -> dict:
        """
        Liste toutes les mises à jour disponibles (Core, Plugins, Thèmes).
        Utilise le cache mémoire si disponible et frais (< 15 min).
        """
        now = time.time()
        ttl_seconds = settings.updates_cache_ttl_minutes * 60
        if use_cache and self.project_name in _updates_cache:
            cache_time, cached_result = _updates_cache[self.project_name]
            if now - cache_time < ttl_seconds:
                await self._log("info", f"⚡ Mises à jour récupérées depuis le cache ({int(now - cache_time)}s)...", step="updates_list")
                return cached_result

        await self._log("info", "Vérification des mises à jour disponibles (parallèle)...", step="updates_list")

        result: dict = {"core": None, "plugins": [], "themes": [], "total_available": 0}

        # Exécuter les 3 commandes WP-CLI en parallèle
        core_task = run_wp_cli("core check-update --format=json", str(self.project_dir))
        plugins_task = run_wp_cli("plugin list --update=available --format=json", str(self.project_dir))
        themes_task = run_wp_cli("theme list --update=available --format=json", str(self.project_dir))

        core_result, plugins_result, themes_result = await asyncio.gather(
            core_task, plugins_task, themes_task
        )

        import json

        # Core
        if core_result.success and core_result.stdout.strip():
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
        if plugins_result.success and plugins_result.stdout.strip():
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
        if themes_result.success and themes_result.stdout.strip():
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

        _updates_cache[self.project_name] = (time.time(), result)

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

        # Core (Mise à jour rapide via Python natif)
        if update_core:
            await self._log("info", "Mise à jour ultra-rapide du core WordPress...", step="updates_apply")
            await run_wp_cli("option delete core_updater.lock", str(self.project_dir))
            current = await run_wp_cli("core version", str(self.project_dir))
            
            # Utilisation directe du téléchargeur/extracteur Python natif (2 à 5 secondes)
            dl_res = await self.download_wordpress()
            if dl_res.success:
                core_result = CommandResult(
                    returncode=0,
                    stdout="WordPress core mis à jour avec succès via extraction directe Python.",
                    stderr="",
                    command="download_wordpress"
                )
            else:
                await self._log("warning", "Extraction directe échouée, tentative fallback via WP-CLI...", step="updates_apply")
                core_result = await run_wp_cli("core update --force", str(self.project_dir), timeout=120)

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

        # Plugins (Mise à jour groupée)
        if plugin_names:
            valid_plugins = [p for p in plugin_names if p]
            if valid_plugins:
                p_str = " ".join(valid_plugins)
                await self._log("info", f"Mise à jour groupée des plugins ({len(valid_plugins)}) : {p_str}", step="updates_apply")
                update_result = await run_wp_cli(f"plugin update {p_str}", str(self.project_dir), timeout=240)
                
                for plugin_name in valid_plugins:
                    new_info = await run_wp_cli(f"plugin get {plugin_name} --field=version", str(self.project_dir))
                    results.append(UpdateResult(
                        name=plugin_name,
                        type="plugin",
                        success=update_result.success or plugin_name in update_result.stdout,
                        message=update_result.stdout if update_result.success else update_result.stderr,
                        old_version="unknown",
                        new_version=new_info.stdout.strip() if new_info.success else None,
                    ))

        # Thèmes (Mise à jour groupée)
        if theme_names:
            valid_themes = [t for t in theme_names if t]
            if valid_themes:
                t_str = " ".join(valid_themes)
                await self._log("info", f"Mise à jour groupée des thèmes ({len(valid_themes)}) : {t_str}", step="updates_apply")
                update_result = await run_wp_cli(f"theme update {t_str}", str(self.project_dir), timeout=240)
                
                for theme_name in valid_themes:
                    new_info = await run_wp_cli(f"theme get {theme_name} --field=version", str(self.project_dir))
                    results.append(UpdateResult(
                        name=theme_name,
                        type="theme",
                        success=update_result.success or theme_name in update_result.stdout,
                        message=update_result.stdout if update_result.success else update_result.stderr,
                        old_version="unknown",
                        new_version=new_info.stdout.strip() if new_info.success else None,
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

        # Récupérer toutes les pages publiées (max 10)
        page_result = await run_wp_cli(
            'post list --post_type=page --post_status=publish'
            ' --fields=ID,post_title,post_name,url --format=json --skip-plugins --skip-themes',
            str(self.project_dir),
        )
        if page_result.success and page_result.stdout.strip():
            import json
            try:
                all_pages = json.loads(page_result.stdout)
                for pg in all_pages[:10]:
                    url = pg.get("url") or f"{site_url}/?page_id={pg['ID']}"
                    name = pg.get("post_name") or f"page-{pg['ID']}"
                    pages.append({"url": url, "name": name, "type": "page"})
            except (json.JSONDecodeError, KeyError):
                pass

        # Récupérer les articles publiés (max 10)
        posts_result = await run_wp_cli(
            'post list --post_type=post --post_status=publish'
            ' --fields=ID,post_title,post_name,url --format=json --skip-plugins --skip-themes',
            str(self.project_dir),
        )
        if posts_result.success and posts_result.stdout.strip():
            import json
            try:
                all_posts = json.loads(posts_result.stdout)
                for post in all_posts[:10]:
                    url = post.get("url") or f"{site_url}/?p={post['ID']}"
                    name = post.get("post_name") or f"post-{post['ID']}"
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
