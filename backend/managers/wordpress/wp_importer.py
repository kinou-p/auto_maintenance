"""
Sous-manager pour l'import d'archives .wpress et le nettoyage post-importation.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from backend.core.config import settings
from backend.managers.wordpress.wp_base import WPBaseManager
from backend.utils.command import run_command, run_wp_cli


class WPImporterMixin(WPBaseManager):
    """Mixin gérant l'importation d'archives .wpress et la configuration post-import."""

    async def import_wpress(self, wpress_path: str) -> bool:
        """Importe un fichier .wpress via extraction native Python, WP-CLI ou fallback Playwright."""
        await self._log("info", f"Import du fichier .wpress : {wpress_path}", step="wpress_import")

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

            sql_files = list(self.project_dir.glob("**/database.sql"))
            if sql_files:
                sql_file = sql_files[0]
                await self._log("info", "Importation de la base de données SQL dans MariaDB (avec FOREIGN_KEY_CHECKS=0)...", step="wpress_import")
                rel_sql = sql_file.relative_to(self.project_dir)

                await run_command('ddev mysql -e "DROP DATABASE IF EXISTS db; CREATE DATABASE db;"', cwd=str(self.project_dir))

                try:
                    sql_text = sql_file.read_text(encoding="utf-8", errors="replace")
                    if ",0x," in sql_text or "(0x," in sql_text or ",0x)" in sql_text or ",0x;" in sql_text:
                        sql_text = re.sub(r"([,(])0x([,);])", r"\1''\2", sql_text)
                        sql_file.write_text(sql_text, encoding="utf-8")
                except Exception:
                    pass

                import_res = await run_command(
                    ["/usr/bin/bash", "-c", f"(echo 'SET FOREIGN_KEY_CHECKS=0;' && cat '{rel_sql}' && echo 'SET FOREIGN_KEY_CHECKS=1;') | ddev mysql --force"],
                    cwd=str(self.project_dir),
                    timeout=600,
                )
                if not import_res.success:
                    await self._log("warning", f"Import pipe mysql a retourné : {import_res.stderr[:200]}, essai fallback ddev import-db...", step="wpress_import")
                    import_res = await run_command(
                        f"ddev import-db --file={rel_sql}",
                        cwd=str(self.project_dir),
                        timeout=300,
                    )

                if import_res.success:
                    await self._log("success", "Base de données SQL importée avec succès !", step="wpress_import")
                    sql_file.unlink(missing_ok=True)

                    detected_prefix = None
                    prefix_query = await run_command(
                        'ddev mysql -N -e "'
                        'SELECT SUBSTRING(o.table_name, 1, LENGTH(o.table_name) - 7) AS prefix '
                        'FROM information_schema.tables o '
                        'JOIN information_schema.tables p ON p.table_name = CONCAT(SUBSTRING(o.table_name, 1, LENGTH(o.table_name) - 7), \'posts\') '
                        'WHERE o.table_schema = \'db\' '
                        '  AND o.table_name LIKE \'%options\' '
                        '  AND p.table_schema = \'db\' '
                        'ORDER BY (o.table_name = \'SERVMASK_PREFIX_options\') DESC, (o.table_name = \'wp_options\') DESC '
                        'LIMIT 1;"',
                        cwd=str(self.project_dir),
                    )
                    if prefix_query.success and prefix_query.stdout.strip():
                        detected_prefix = prefix_query.stdout.strip()

                    final_prefix = detected_prefix or "SERVMASK_PREFIX_"

                    wp_config = self.project_dir / "wp-config.php"
                    if wp_config.exists():
                        content = wp_config.read_text(encoding="utf-8", errors="replace")
                        content = re.sub(r"\$table_prefix\s*=\s*['\"][^'\"]+['\"];", f"$table_prefix = '{final_prefix}';", content)
                        wp_config.write_text(content, encoding="utf-8")
                        await self._log("info", f"Prefixe de table ajusté à '{final_prefix}' dans wp-config.php.", step="wpress_import")

            return await self._post_import_cleanup()

        # 2. Fallback WP-CLI
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

        # 3. Fallback : import via Playwright
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
        """Fallback : simule l'import via l'interface web avec Playwright."""
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

                await page.goto(f"{site_url}/wp-login.php", wait_until="networkidle")
                await page.fill("#user_login", settings.wp_admin_user)
                await page.fill("#user_pass", settings.wp_admin_password)
                await page.click("#wp-submit")
                await page.wait_for_load_state("networkidle")

                await page.goto(
                    f"{site_url}/wp-admin/admin.php?page=ai1wm_import",
                    wait_until="networkidle",
                )

                file_input = await page.query_selector('input[type="file"]')
                if file_input:
                    await file_input.set_input_files(wpress_path)
                    await page.wait_for_selector(
                        ".ai1wm-import-done, .ai1wm-button-done",
                        timeout=600000,
                    )
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

        old_url_result = await run_wp_cli("option get siteurl", str(self.project_dir))
        old_site_url = old_url_result.stdout.strip() if old_url_result.success else ""

        package_json = self.project_dir / "package.json"
        pkg_prefix = None
        if package_json.exists():
            try:
                pkg_data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
                if not old_site_url:
                    old_site_url = pkg_data.get("SiteURL") or pkg_data.get("HomeURL") or ""
                pkg_prefix = pkg_data.get("Database", {}).get("Prefix")
            except Exception:
                pass

        if not old_site_url:
            prefix_try = f"{pkg_prefix}options" if pkg_prefix else "wp_options"
            sql_url_res = await self.ddev.exec_in_container(
                f"mysql -u db -pdb db -N -e \"SELECT option_value FROM {prefix_try} WHERE option_name='siteurl' LIMIT 1;\" 2>/dev/null || mysql -u db -pdb db -N -e \"SELECT option_value FROM SERVMASK_PREFIX_options WHERE option_name='siteurl' LIMIT 1;\" 2>/dev/null || mysql -u db -pdb db -N -e \"SELECT option_value FROM wp_options WHERE option_name='siteurl' LIMIT 1;\" 2>/dev/null"
            )
            if sql_url_res.success and sql_url_res.stdout.strip():
                old_site_url = sql_url_res.stdout.strip()

        new_site_url = await self.ddev.get_url()

        await self._log(
            "info",
            f"[DEBUG] Ancienne URL (backup) : '{old_site_url}' | Nouvelle URL (DDEV) : '{new_site_url}'",
            step="wpress_import",
        )

        if new_site_url:
            await run_wp_cli(f'option update siteurl "{new_site_url}"', str(self.project_dir))
            await run_wp_cli(f'option update home "{new_site_url}"', str(self.project_dir))

        if old_site_url and old_site_url != new_site_url:
            await self._log(
                "info",
                f"Search-replace : {old_site_url} → {new_site_url}",
                step="wpress_import",
            )

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

                use_regex = False
                search_term = old_domain

                if new_port and old_domain == new_parsed.hostname:
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
            await run_wp_cli(f'option update siteurl "{new_site_url}"', str(self.project_dir))
            await run_wp_cli(f'option update home "{new_site_url}"', str(self.project_dir))
            await self._log("info", f"URLs du site mises à jour : {new_site_url}", step="wpress_import")

        # Purger les caches fichiers
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
            await self.ddev.exec_in_container(
                f"rm -rf /var/www/html/{cache_dir}/* 2>/dev/null; echo ok"
            )

        await run_wp_cli('option update WpFastestCache ""', str(self.project_dir))
        await self._log("info", "WP Fastest Cache désactivé (options vidées).", step="wpress_import")

        await run_wp_cli("cache flush", str(self.project_dir))
        await run_wp_cli("transient delete --all", str(self.project_dir))
        await self._log("info", "Cache objet et transients vidés.", step="wpress_import")

        await run_wp_cli("rewrite flush --hard", str(self.project_dir))
        await self._log("info", "Permaliens régénérés.", step="wpress_import")

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

        unlimited_dir = self.project_dir / "wp-content" / "plugins" / "all-in-one-wp-migration-unlimited-main"
        if unlimited_dir.exists():
            shutil.rmtree(unlimited_dir, ignore_errors=True)

        act_result = await run_wp_cli("plugin activate --all", str(self.project_dir))
        if act_result.success:
            await self._log("info", "Extensions du site activées avec succès.", step="wpress_import")
        else:
            await self._log("warning", "Activation globale partielle (certaines extensions incompatibles PHP 8+), activation plugin par plugin...", step="wpress_import")
            plugins_res = await run_wp_cli("plugin list --field=name --skip-plugins --skip-themes", str(self.project_dir))
            if plugins_res.success:
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
                        await run_wp_cli(f"plugin deactivate {p_name}", str(self.project_dir))
                        await self._log("warning", f"⚠️ Extension '{p_name}' désactivée (incompatible PHP 8+ / Fatal Error).", step="wpress_import")
                await self._log("info", f"Activation individuelle terminée : {activated_count} activée(s), {failed_count} ignorée(s).", step="wpress_import")

        await run_wp_cli(deact_cmd, str(self.project_dir))
        await run_wp_cli("option update rsl_ssl_enabled 0", str(self.project_dir))

        final_siteurl = await run_wp_cli("option get siteurl", str(self.project_dir))
        final_home = await run_wp_cli("option get home", str(self.project_dir))
        await self._log(
            "info",
            f"[DEBUG] URLs finales en DB → siteurl: '{final_siteurl.stdout.strip()}' | home: '{final_home.stdout.strip()}'",
            step="wpress_import",
        )

        pkg_theme = None
        package_json = self.project_dir / "package.json"
        if package_json.exists():
            try:
                pkg_data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
                pkg_theme = pkg_data.get("Stylesheet") or pkg_data.get("Template")
            except Exception:
                pass

        theme_activated = False
        if pkg_theme:
            themes_dir = self.project_dir / "wp-content" / "themes"
            target_theme_slug = pkg_theme
            if themes_dir.exists():
                for d in themes_dir.iterdir():
                    if d.is_dir():
                        d_norm = d.name.lower().replace("-", "").replace("_", "")
                        p_norm = pkg_theme.lower().replace("-", "").replace("_", "")
                        if d_norm == p_norm or d.name.lower() == pkg_theme.lower():
                            target_theme_slug = d.name
                            break

            act_res = await run_wp_cli(f"theme activate {target_theme_slug}", str(self.project_dir))
            if act_res.success:
                await self._log("success", f"Thème original du site '{target_theme_slug}' activé avec succès.", step="wpress_import")
                theme_activated = True
            else:
                await self._log("warning", f"WP-CLI n'a pas pu activer '{target_theme_slug}' : {act_res.stderr[:200]}", step="wpress_import")

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

        if not active_themes and not theme_activated:
            await self._log(
                "warning",
                "⚠️ Aucun thème actif détecté en DB après l'importation. Activation d'un thème valide...",
                step="wpress_import",
            )

            themes_dir = self.project_dir / "wp-content" / "themes"
            fs_themes = []
            if themes_dir.exists():
                fs_themes = [d.name for d in themes_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

            custom_fs = [t for t in fs_themes if not t.startswith("twenty")]
            candidate_fs = custom_fs if custom_fs else fs_themes

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

            if not wp_activated and candidate_fs:
                fallback_theme = candidate_fs[0]
                await self._log("info", f"Fallback SQL : activation du thème '{fallback_theme}' directement en DB...", step="wpress_import")
                try:
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
                        res = await self.ddev.exec_in_container(f"mysql -u db -pdb db -e \"{sql}\"")
                        await self._log("info", f"SQL thème [{table_prefix}]: rc={res.exit_code}", step="wpress_import")
                    await self._log("success", f"Thème '{fallback_theme}' forcé en DB via SQL.", step="wpress_import")
                except Exception as e:
                    await self._log("warning", f"Fallback SQL thème échoué : {e}", step="wpress_import")

        user_chk = await run_wp_cli(f"user get {settings.wp_admin_user} --field=ID", str(self.project_dir))
        if user_chk.success and user_chk.stdout.strip():
            await run_wp_cli(
                f'user update {settings.wp_admin_user} --user_pass="{settings.wp_admin_password}" --role=administrator',
                str(self.project_dir),
            )
            await self._log("info", f"Identifiants de l'administrateur '{settings.wp_admin_user}' mis à jour.", step="wpress_import")
        else:
            await run_wp_cli(
                f'user create {settings.wp_admin_user} {settings.wp_admin_email} --role=administrator --user_pass="{settings.wp_admin_password}"',
                str(self.project_dir),
            )
            await self._log("info", f"Compte administrateur '{settings.wp_admin_user}' créé avec succès.", step="wpress_import")

        await self._log("info", "Vérification de l'accessibilité du site...", step="wpress_import")
        max_retries = 8
        site_accessible = False
        for attempt in range(max_retries):
            try:
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

        await self._log("info", "Stabilisation du site (5s)...", step="wpress_import")
        await asyncio.sleep(5)
        return True
