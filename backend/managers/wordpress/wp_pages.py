"""
Sous-manager pour l'inspection des URLs et pages WordPress.
"""

from __future__ import annotations

import json
from backend.managers.wordpress.wp_base import WPBaseManager
from backend.utils.command import run_wp_cli


class WPPagesMixin(WPBaseManager):
    """Mixin pour inspecter les URLs et pages d'un site WordPress."""

    async def get_site_urls(self) -> list[str]:
        """Récupère les URLs principales du site pour les screenshots."""
        site_url = await self.ddev.get_url()
        urls = [site_url]

        posts_result = await run_wp_cli(
            'post list --post_type=post --post_status=publish --posts_per_page=1 --field=url',
            str(self.project_dir),
        )
        if posts_result.success and posts_result.stdout.strip():
            urls.append(posts_result.stdout.strip().split("\n")[0])

        contact_result = await run_wp_cli(
            'post list --post_type=page --post_status=publish --name=contact --field=url',
            str(self.project_dir),
        )
        if contact_result.success and contact_result.stdout.strip():
            urls.append(contact_result.stdout.strip().split("\n")[0])
        else:
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
        """Récupère toutes les pages WordPress publiées pour les screenshots."""
        site_url = await self.ddev.get_url()
        pages: list[dict] = []

        pages.append({"url": site_url, "name": "accueil", "type": "home"})

        page_result = await run_wp_cli(
            'post list --post_type=page --post_status=publish'
            ' --fields=ID,post_title,post_name,url --format=json --skip-plugins --skip-themes',
            str(self.project_dir),
        )
        if page_result.success and page_result.stdout.strip():
            try:
                all_pages = json.loads(page_result.stdout)
                for pg in all_pages[:10]:
                    url = pg.get("url") or f"{site_url}/?page_id={pg['ID']}"
                    name = pg.get("post_name") or f"page-{pg['ID']}"
                    pages.append({"url": url, "name": name, "type": "page"})
            except (json.JSONDecodeError, KeyError):
                pass

        posts_result = await run_wp_cli(
            'post list --post_type=post --post_status=publish'
            ' --fields=ID,post_title,post_name,url --format=json --skip-plugins --skip-themes',
            str(self.project_dir),
        )
        if posts_result.success and posts_result.stdout.strip():
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
