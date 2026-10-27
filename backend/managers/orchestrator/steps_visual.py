"""
Auto Maintenance - Étapes Visuelles (Screenshots, Comparaison VRT).
"""

from __future__ import annotations

import httpx

from backend.core.websocket import ws_manager
from backend.managers.orchestrator.exceptions import StepError
from backend.models.database import VRTReport, async_session


class WorkflowVisualStepsMixin:
    """Mixin pour les étapes de captures d'écran et de comparaison visuelle (VRT)."""

    async def _step_screenshots(self, phase: str) -> None:
        """Étape 6/9 : Capture des screenshots."""
        assert self._wp is not None
        assert self._screenshots is not None

        step = f"screenshots_{phase}"

        # Vérifier que le site est accessible avant de capturer
        site_url = await self._wp.ddev.get_url()
        try:
            async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
                response = await client.get(site_url)
                if response.status_code >= 400:
                    await self.logger.warning(
                        f"Le site répond avec le code {response.status_code}. "
                        f"Les screenshots pourraient être incorrects.",
                        step=step,
                    )
                else:
                    body = response.text
                    has_css = ('<link' in body and ('stylesheet' in body or '.css' in body)) or '<style' in body
                    if not has_css:
                        await self.logger.warning(
                            "Aucune feuille de style CSS ou balise <style> détectée dans le HTML. "
                            "Les screenshots risquent de montrer du HTML brut.",
                            step=step,
                        )
        except Exception as e:
            await self.logger.warning(
                f"Impossible de vérifier l'accessibilité du site : {e}",
                step=step,
            )

        pages = await self._wp.get_page_info()
        if not pages:
            pages = [{"name": "home", "url": site_url, "title": "Accueil"}]

        page_names = [p.get("name", "page") for p in pages]
        await self.logger.info(
            f"🔍 {len(pages)} page(s) détectée(s) pour la capture ({phase}) : {', '.join(page_names)}",
            step=step,
        )

        try:
            results = await self._screenshots.capture_screenshots(pages, phase)
            if not results:
                raise StepError(f"Aucun screenshot capturé pour la phase '{phase}'.")
            await self.logger.info(
                f"{len(results)} screenshot(s) capturé(s) ({phase}).",
                step=step,
            )
        except StepError:
            raise
        except Exception as e:
            raise StepError(f"Échec de la capture des screenshots ({phase}) : {e}")

    async def _step_vrt_compare(self) -> None:
        """Étape 10 : Comparaison visuelle avant/après."""
        assert self._vrt is not None
        report = await self._vrt.compare_all()

        total_p = report.get("total_pages", 0)
        passed_p = report.get("total_passed", 0)
        failed_p = report.get("total_failed", 0)

        await self.logger.info(
            f"📊 Synthèse VRT : {passed_p}/{total_p} test(s) visuel(s) validé(s) ({failed_p} écart(s) détecté(s)).",
            step="vrt_compare",
        )

        for item in report.get("items", []):
            p_name = item.get("page_name", "page")
            dev = item.get("device", "desktop")
            ssim = item.get("ssim_score", 0.0)
            diff = item.get("diff_percentage", 0.0)
            is_passed = item.get("passed", False)
            verdict = "PASSED ✅" if is_passed else "FAILED ⚠️"
            await self.logger.info(
                f"  • {p_name} ({dev}) -> SSIM: {ssim:.4f} | Diff: {diff:.2f}% | Statut: {verdict}",
                step="vrt_compare",
            )

        # Sauvegarder les résultats VRT en DB
        async with async_session() as session:
            for item in report.get("items", []):
                vrt_report = VRTReport(
                    project_id=self.project_id,
                    workflow_id=self.workflow_id,
                    page_url=item.get("page_url", ""),
                    page_name=item.get("page_name", ""),
                    device=item.get("device", "unknown"),
                    before_screenshot=item.get("before_path"),
                    after_screenshot=item.get("after_path"),
                    diff_image=item.get("diff_image"),
                    diff_percentage=item.get("diff_percentage"),
                    ssim_score=item.get("ssim_score"),
                    passed=1 if item.get("passed") else 0,
                )
                session.add(vrt_report)
            await session.commit()

        # Envoyer le rapport via WebSocket
        await ws_manager.send_to_project(self.project_id, {
            "type": "vrt_report",
            "data": report,
        })

        if total_p == 0:
            raise StepError("Aucune comparaison VRT n'a pu être réalisée (captures introuvables ou incomplètes).")

        fail_on_vrt = self.options.get("fail_on_vrt_regressions", True)
        if failed_p > 0 and fail_on_vrt:
            raise StepError(f"Régression(s) visuelle(s) critique(s) détectée(s) : {failed_p}/{total_p} test(s) visuel(s) en échec.")
