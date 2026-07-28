"""
Auto Maintenance - Screenshot Manager.

Capture des screenshots full-page en résolutions desktop et mobile
avec Playwright pour le Visual Regression Testing.

Optimisations :
- Un seul navigateur Chromium réutilisé pour toutes les captures
- Desktop et mobile capturés en parallèle (2 contextes par page)
- Jusqu'à 3 pages traitées simultanément (6 contextes max)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger

# Nombre max de pages capturées en parallèle (× 2 viewports = 6 contextes)
MAX_CONCURRENT_PAGES = 3

VIEWPORTS = [
    {
        "device": "desktop",
        "width": settings.screenshot_desktop_width,
        "height": settings.screenshot_desktop_height,
        "is_mobile": False,
        "device_scale_factor": 1,
        "user_agent": None,
        "has_touch": False,
    },
    {
        "device": "mobile",
        "width": settings.screenshot_mobile_width,
        "height": settings.screenshot_mobile_height,
        "is_mobile": True,
        "device_scale_factor": 3,
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "has_touch": True,
    },
]


class ScreenshotManager:
    """Capture des screenshots de pages WordPress avec Playwright."""

    def __init__(
        self,
        project_name: str,
        logger: Optional[WorkflowLogger] = None,
    ) -> None:
        self.project_name = project_name
        self.logger = logger
        # Instance Playwright/browser réutilisée
        self._playwright = None
        self._browser = None

    async def _log(self, level: str, message: str, step: str = "screenshots_before") -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step=step)

    def _get_output_dir(self, phase: str, clean_old: bool = True) -> Path:
        output_dir = settings.screenshots_dir / self.project_name / phase
        output_dir.mkdir(parents=True, exist_ok=True)
        if clean_old:
            for f in output_dir.glob("*.png"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
        return output_dir


    def _sanitize_filename(self, name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

    async def _ensure_browser(self):
        """Lance Playwright et le navigateur s'ils ne sont pas déjà actifs."""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
        return self._browser

    async def cleanup(self) -> None:
        """Ferme le navigateur et Playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def capture_screenshots(
        self,
        pages: list[dict],
        phase: str = "before",
    ) -> list[dict]:
        """
        Capture des screenshots pour une liste de pages.
        Traite jusqu'à 3 pages en parallèle, desktop+mobile en parallèle par page.

        Args:
            pages: Liste de dict avec 'url', 'name', 'type'.
            phase: "before" ou "after".

        Returns:
            Liste de dict avec les chemins des screenshots capturés.
        """
        step = f"screenshots_{phase}"
        await self._log("info", f"Capture des screenshots ({phase})...", step=step)

        output_dir = self._get_output_dir(phase)
        results: list[dict] = []

        try:
            browser = await self._ensure_browser()

            # Sémaphore pour limiter à MAX_CONCURRENT_PAGES pages en parallèle
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

            async def capture_with_semaphore(i: int, page_info: dict) -> list[dict]:
                async with semaphore:
                    url = page_info["url"]
                    name = self._sanitize_filename(page_info.get("name", f"page_{i}"))
                    page_type = page_info.get("type", "unknown")

                    await self._log(
                        "info",
                        f"Screenshot [{i+1}/{len(pages)}] : {name} ({url})",
                        step=step,
                    )

                    # Progression
                    progress = ((i) / len(pages)) * 50 + (50 if phase == "after" else 0)
                    if self.logger:
                        await self.logger.progress(step, progress, f"Capture : {name}")

                    return await self._capture_page(
                        browser, url, name, page_type, output_dir, phase
                    )

            # Lancer toutes les pages en parallèle (le sémaphore limite à 3)
            tasks = [
                capture_with_semaphore(i, page_info)
                for i, page_info in enumerate(pages)
            ]
            page_results = await asyncio.gather(*tasks, return_exceptions=True)

            for pr in page_results:
                if isinstance(pr, Exception):
                    await self._log("warning", f"Erreur capture page : {pr}", step=step)
                elif isinstance(pr, list):
                    results.extend(pr)

        except ImportError:
            await self._log("error", "Playwright n'est pas installé. Screenshots ignorés.", step=step)
            return []
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await self._log("error", f"Erreur lors de la capture : {type(e).__name__}: {e}\n{tb[-500:]}", step=step)
            return []

        await self._log(
            "success",
            f"{len(results)} screenshot(s) capturé(s) ({phase}).",
            step=step,
        )

        return results

    async def _capture_page(
        self,
        browser,
        url: str,
        name: str,
        page_type: str,
        output_dir: Path,
        phase: str = "before",
    ) -> list[dict]:
        """
        Capture desktop ET mobile en parallèle pour une page.

        Returns:
            Liste de dict avec les infos de chaque screenshot.
        """
        # Lancer les 2 viewports en parallèle
        tasks = [
            self._capture_viewport(browser, url, name, page_type, output_dir, phase, vp)
            for vp in VIEWPORTS
        ]
        viewport_results = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[dict] = []
        for vr in viewport_results:
            if isinstance(vr, Exception):
                step = f"screenshots_{phase}"
                await self._log("warning", f"Échec screenshot {name}: {vr}", step=step)
            elif vr is not None:
                results.append(vr)

        return results

    async def _capture_viewport(
        self,
        browser,
        url: str,
        name: str,
        page_type: str,
        output_dir: Path,
        phase: str,
        vp: dict,
    ) -> Optional[dict]:
        """
        Capture un screenshot pour un viewport donné.

        Returns:
            Dict avec les infos du screenshot, ou None en cas d'échec.
        """
        step = f"screenshots_{phase}"
        device = vp["device"]
        filename = f"{name}_{device}.png"
        filepath = output_dir / filename

        context_opts = {
            "viewport": {"width": vp["width"], "height": vp["height"]},
            "ignore_https_errors": True,
            "locale": "fr-FR",
            "timezone_id": "Europe/Paris",
            "bypass_csp": True,
        }
        if vp["user_agent"]:
            context_opts["user_agent"] = vp["user_agent"]


        context = await browser.new_context(**context_opts)
        page = await context.new_page()

        try:
            # Naviguer vers la page
            await page.goto(url, wait_until="domcontentloaded", timeout=settings.playwright_timeout)

            # Attendre le chargement complet avec fallback doux
            try:
                await page.wait_for_load_state("load", timeout=10000)
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass

            # Attendre les fonts
            try:
                await page.evaluate("document.fonts.ready")
            except Exception:
                pass

            # Attendre le rendu CSS
            await page.wait_for_timeout(1000)

            # Scroll pour lazy loading
            await self._scroll_page(page)

            # Attendre les images lazy-loaded
            await page.wait_for_timeout(2000)

            # Revenir en haut
            await page.evaluate("""
                async () => {
                    window.scrollTo({top: 0, behavior: 'smooth'});
                    await new Promise(r => setTimeout(r, 500));
                }
            """)
            await page.wait_for_timeout(1000)

            # Masquer les éléments dynamiques
            await self._hide_dynamic_elements(page)

            # Stabilisation
            await page.wait_for_timeout(500)

            # Capture
            await page.screenshot(
                path=str(filepath),
                full_page=True,
                type="png",
            )

            return {
                "page_name": name,
                "page_url": url,
                "page_type": page_type,
                "device": device,
                "filepath": str(filepath),
                "width": vp["width"],
                "height": vp["height"],
            }

        except Exception as e:
            await self._log("warning", f"Échec screenshot {name} ({device}): {e}", step=step)
            return None

        finally:
            await context.close()

    async def _scroll_page(self, page) -> None:
        """Scroll la page de haut en bas pour déclencher le lazy loading et charger les animations."""
        await page.evaluate("""
            async () => {
                const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
                
                // Calculer la hauteur totale de la page
                const getScrollHeight = () => Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight,
                    document.body.offsetHeight,
                    document.documentElement.offsetHeight
                );
                
                let height = getScrollHeight();
                const step = Math.max(Math.floor(height / 15), 300);
                
                // Scroll progressif avec plus de pauses
                for (let i = 0; i < height; i += step) {
                    window.scrollTo({top: i, behavior: 'smooth'});
                    await delay(200);
                    
                    // Recalculer la hauteur (certains éléments peuvent charger du contenu)
                    const newHeight = getScrollHeight();
                    if (newHeight > height) {
                        height = newHeight;
                    }
                }
                
                // Aller complètement en bas
                window.scrollTo({top: height, behavior: 'smooth'});
                await delay(1000);
            }
        """)

    async def _hide_dynamic_elements(self, page) -> None:
        """
        Masque les éléments dynamiques qui pourraient causer des faux positifs VRT.

        Cible : bandeaux cookies, popups, éléments animés.
        """
        await page.evaluate("""
            () => {
                // Sélecteurs courants de bandeaux cookies et popups
                const selectors = [
                    '[class*="cookie"]',
                    '[id*="cookie"]',
                    '[class*="consent"]',
                    '[id*="consent"]',
                    '[class*="gdpr"]',
                    '[id*="gdpr"]',
                    '[class*="popup"]',
                    '[class*="modal"]',
                    '[class*="overlay"]',
                    '.cc-banner',
                    '.cc-window',
                    '#cookie-notice',
                    '.cookie-notice',
                    '[class*="notification-bar"]',
                ];

                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        el.style.display = 'none';
                        el.style.visibility = 'hidden';
                    });
                });

                // Désactiver les animations CSS
                const style = document.createElement('style');
                style.textContent = `
                    *, *::before, *::after {
                        animation: none !important;
                        transition: none !important;
                    }
                `;
                document.head.appendChild(style);
            }
        """)
