"""
Sous-manager pour la détection et l'application des mises à jour WordPress.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

from backend.core.config import settings
from backend.managers.wordpress.wp_base import WPBaseManager
from backend.models.schemas import UpdateItem, UpdateResult
from backend.utils.command import CommandResult, run_wp_cli

# Cache global des mises à jour (project_name -> (timestamp, result_dict))
_updates_cache: dict[str, tuple[float, dict]] = {}


class WPUpdatesMixin(WPBaseManager):
    """Mixin pour lister et appliquer les mises à jour WordPress."""

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

        core_task = run_wp_cli("core check-update --format=json", str(self.project_dir))
        plugins_task = run_wp_cli("plugin list --update=available --format=json", str(self.project_dir))
        themes_task = run_wp_cli("theme list --update=available --format=json", str(self.project_dir))

        core_result, plugins_result, themes_result = await asyncio.gather(
            core_task, plugins_task, themes_task
        )

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
        """Applique les mises à jour sélectionnées."""
        await self._log("info", "Application des mises à jour...", step="updates_apply")
        results: list[UpdateResult] = []

        # Core
        if update_core:
            await self._log("info", "Mise à jour ultra-rapide du core WordPress...", step="updates_apply")
            await run_wp_cli("option delete core_updater.lock", str(self.project_dir))
            current = await run_wp_cli("core version", str(self.project_dir))

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

            if core_result.success:
                await run_wp_cli("core update-db", str(self.project_dir))

        # Plugins
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

        # Thèmes
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

        success_count = sum(1 for r in results if r.success)
        fail_count = len(results) - success_count
        await self._log(
            "success" if fail_count == 0 else "warning",
            f"Mises à jour terminées : {success_count} réussie(s), {fail_count} échouée(s).",
            step="updates_apply",
        )

        await run_wp_cli("cache flush", str(self.project_dir))

        return results
