"""
Auto Maintenance - VRT Manager (Visual Regression Testing).

Compare les screenshots avant/après maintenance en utilisant :
- SSIM (Structural Similarity Index) pour la similarité structurelle
- Pixel diff pour la comparaison pixel par pixel
- Génération d'images de diff avec zones modifiées en surbrillance

Stratégie de comparaison :
─────────────────────────
1. **SSIM (scikit-image)** : Mesure la similarité structurelle entre deux images.
   Score de 0 à 1 (1 = identique). Très résistant aux petites variations
   de compression JPEG, anti-aliasing et rendu de polices.

2. **Pixel diff (Pillow + numpy)** : Comparaison pixel par pixel avec
   tolérance configurable. Génère une image de diff visuelle.

3. **Seuils de tolérance** :
   - < 0.5% de diff pixel : PASS (changements cosmétiques mineurs)
   - 0.5% - 5% : WARNING (vérification manuelle recommandée)
   - > 5% : FAIL (régression visuelle probable)

4. **Gestion des faux positifs** :
   - Masquage des éléments dynamiques (cookies, timestamps) lors du screenshot
   - Tolérance anti-aliasing configurable
   - SSIM qui résiste au lazy loading partial
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

from backend.core.config import settings
from backend.core.websocket import WorkflowLogger
from backend.api.settings import get_system_settings_db


class VRTManager:
    """Compare visuellement les screenshots avant/après maintenance."""

    def __init__(
        self,
        project_name: str,
        logger: Optional[WorkflowLogger] = None,
    ) -> None:
        self.project_name = project_name
        self.logger = logger
        self.threshold = settings.vrt_threshold  # % seuil de diff par défaut
        self.min_ssim = getattr(settings, "vrt_min_ssim_score", 0.95)
        self.aa_tolerance = settings.vrt_anti_aliasing_tolerance
        self.diff_color = (
            settings.vrt_diff_color_r,
            settings.vrt_diff_color_g,
            settings.vrt_diff_color_b,
        )

    async def _load_db_settings(self) -> None:
        """Charge les paramètres de comparaison visuelle enregistrés en base de données."""
        try:
            db_sys = await get_system_settings_db()
            self.min_ssim = float(db_sys.get("vrt_min_ssim_score", 0.95))
            self.threshold = float(db_sys.get("vrt_max_diff_percentage", settings.vrt_threshold))
            self.aa_tolerance = int(db_sys.get("vrt_anti_aliasing_tolerance", settings.vrt_anti_aliasing_tolerance))
        except Exception:
            pass

    async def _log(self, level: str, message: str) -> None:
        if self.logger:
            await getattr(self.logger, level)(message, step="vrt_compare")

    # ── Comparaison principale ────────────────────────────────────

    async def compare_all(self) -> dict:
        """
        Compare tous les screenshots before/after d'un projet.

        Returns:
            Rapport complet de comparaison VRT.
        """
        await self._load_db_settings()
        await self._log("info", f"Démarrage de la comparaison visuelle (SSIM min: {self.min_ssim}, Diff max: {self.threshold}%)...")

        before_dir = settings.screenshots_dir / self.project_name / "before"
        after_dir = settings.screenshots_dir / self.project_name / "after"
        diff_dir = settings.screenshots_dir / self.project_name / "diff"
        diff_dir.mkdir(parents=True, exist_ok=True)

        if not before_dir.exists():
            await self._log("error", "Répertoire 'before' introuvable.")
            return {"error": "Répertoire before manquant", "items": []}

        if not after_dir.exists():
            await self._log("error", "Répertoire 'after' introuvable.")
            return {"error": "Répertoire after manquant", "items": []}

        # Trouver les paires de screenshots
        before_files = {f.name: f for f in before_dir.glob("*.png")}
        after_files = {f.name: f for f in after_dir.glob("*.png")}

        common_files = set(before_files.keys()) & set(after_files.keys())

        if not common_files:
            await self._log("warning", "Aucune paire de screenshots trouvée.")
            return {"items": [], "total_pages": 0, "total_passed": 0, "total_failed": 0}

        results: list[dict] = []

        async def compare_single(i: int, filename: str) -> dict:
            await self._log("info", f"Comparaison [{i+1}/{len(common_files)}] : {filename}")
            if self.logger:
                progress = ((i + 1) / len(common_files)) * 100
                await self.logger.progress("vrt_compare", progress, f"Comparaison : {filename}")

            # Vérifier la présence des DOM Snapshots correspondants
            dom_before_file = before_dir / filename.replace(".png", ".dom.json")
            dom_after_file = after_dir / filename.replace(".png", ".dom.json")
            dom_similarity = None
            if dom_before_file.exists() and dom_after_file.exists():
                try:
                    dom_before = json.loads(dom_before_file.read_text(encoding="utf-8"))
                    dom_after = json.loads(dom_after_file.read_text(encoding="utf-8"))
                    dom_similarity = self._compare_dom_trees(dom_before.get("tree"), dom_after.get("tree"))
                except Exception:
                    pass

            result = await self.compare_images(
                str(before_files[filename]),
                str(after_files[filename]),
                str(diff_dir / f"diff_{filename}"),
            )

            parts = filename.replace(".png", "").rsplit("_", 1)
            page_name = parts[0] if len(parts) > 1 else filename
            device = parts[1] if len(parts) > 1 else "unknown"

            rel_before = f"/static/data/screenshots/{self.project_name}/before/{filename}"
            rel_after = f"/static/data/screenshots/{self.project_name}/after/{filename}"
            rel_diff = f"/static/data/screenshots/{self.project_name}/diff/diff_{filename}"

            result.update({
                "page_name": page_name,
                "device": device,
                "before_path": rel_before,
                "after_path": rel_after,
                "diff_image": rel_diff,
                "dom_similarity": dom_similarity,
            })
            return result


        tasks = [compare_single(i, fn) for i, fn in enumerate(sorted(common_files))]
        results = await asyncio.gather(*tasks)

        # Calcul des totaux
        total_passed = sum(1 for r in results if r.get("passed", False))
        total_failed = len(results) - total_passed

        report = {
            "project_name": self.project_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_pages": len(results),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "threshold": self.threshold,
            "items": results,
        }

        # Sauvegarder le rapport JSON
        report_path = settings.reports_dir / f"{self.project_name}_vrt_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        await self._log("success", f"Rapport VRT sauvegardé : {report_path}")

        summary_level = "success" if total_failed == 0 else "warning"
        await self._log(
            summary_level,
            f"VRT terminé : {total_passed}/{len(results)} passé(s), {total_failed} échoué(s).",
        )

        return report

    async def compare_images(
        self,
        before_path: str,
        after_path: str,
        diff_output_path: str,
    ) -> dict:
        """
        Compare deux images et génère une image de diff (exécuté hors du thread principal).
        """
        def _process():
            before_img = Image.open(before_path).convert("RGB")
            after_img = Image.open(after_path).convert("RGB")

            if before_img.size != after_img.size:
                max_w = max(before_img.width, after_img.width)
                max_h = max(before_img.height, after_img.height)

                before_resized = Image.new("RGB", (max_w, max_h), (255, 255, 255))
                before_resized.paste(before_img, (0, 0))

                after_resized = Image.new("RGB", (max_w, max_h), (255, 255, 255))
                after_resized.paste(after_img, (0, 0))

                before_img = before_resized
                after_img = after_resized

            before_arr = np.array(before_img, dtype=np.float64)
            after_arr = np.array(after_img, dtype=np.float64)

            pixel_diff = np.abs(before_arr - after_arr)
            tolerance = self.aa_tolerance
            diff_mask = np.any(pixel_diff > tolerance, axis=2)

            total_pixels = diff_mask.size
            diff_pixels = int(np.sum(diff_mask))
            diff_percentage = (diff_pixels / total_pixels) * 100

            ssim_score = self._compute_ssim(before_arr, after_arr)
            diff_image = self._generate_diff_image(before_img, after_img, diff_mask)
            diff_image.save(diff_output_path, "PNG")

            passed = (ssim_score >= self.min_ssim) and (diff_percentage <= self.threshold)

            return {
                "diff_percentage": round(diff_percentage, 4),
                "diff_pixels": diff_pixels,
                "total_pixels": total_pixels,
                "ssim_score": round(ssim_score, 6),
                "diff_image": diff_output_path,
                "passed": passed,
                "verdict": self._get_verdict(diff_percentage),
            }

        try:
            import asyncio
            return await asyncio.to_thread(_process)
        except Exception as e:
            await self._log("error", f"Erreur de comparaison : {e}")
            return {
                "diff_percentage": -1,
                "ssim_score": -1,
                "diff_image": None,
                "passed": False,
                "error": str(e),
                "verdict": "error",
            }

    def _compute_ssim(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """
        Calcule le SSIM (Structural Similarity Index) entre deux images.

        Implémentation simplifiée basée sur la formule originale de Wang et al.
        Sans dépendance à scikit-image (mais compatible si installé).
        """
        try:
            # Essayer d'utiliser scikit-image si disponible
            from skimage.metrics import structural_similarity
            # Convertir en niveaux de gris pour SSIM
            gray1 = np.mean(img1, axis=2)
            gray2 = np.mean(img2, axis=2)
            return float(structural_similarity(gray1, gray2, data_range=255))
        except ImportError:
            pass

        # Fallback : implémentation manuelle simplifiée
        gray1 = np.mean(img1, axis=2).astype(np.float64)
        gray2 = np.mean(img2, axis=2).astype(np.float64)

        # Constantes de stabilisation
        c1 = (0.01 * 255) ** 2
        c2 = (0.03 * 255) ** 2

        mu1 = np.mean(gray1)
        mu2 = np.mean(gray2)
        sigma1_sq = np.var(gray1)
        sigma2_sq = np.var(gray2)
        sigma12 = np.mean((gray1 - mu1) * (gray2 - mu2))

        ssim = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / (
            (mu1**2 + mu2**2 + c1) * (sigma1_sq + sigma2_sq + c2)
        )

        return float(ssim)

    def _generate_diff_image(
        self,
        before: Image.Image,
        after: Image.Image,
        diff_mask: np.ndarray,
    ) -> Image.Image:
        """
        Génère une image de diff composite montrant les zones modifiées.

        Layout : before | diff overlay | after (3 panneaux côte à côte).
        Les zones différentes sont surlignées en couleur configurée.
        """
        width, height = before.size

        # Créer l'image de diff (overlay sur l'image after)
        overlay = after.copy()
        overlay_arr = np.array(overlay)

        # Surbrillance des pixels différents
        overlay_arr[diff_mask] = self.diff_color

        diff_overlay = Image.fromarray(overlay_arr)

        # Blend pour la transparence
        diff_blended = Image.blend(after, diff_overlay, alpha=0.4)

        # Composite : 3 panneaux
        composite_width = width * 3 + 20  # 10px de marge entre chaque
        composite = Image.new("RGB", (composite_width, height + 40), (30, 30, 30))

        # Coller les images
        composite.paste(before, (0, 40))
        composite.paste(diff_blended, (width + 10, 40))
        composite.paste(after, (width * 2 + 20, 40))

        # Ajouter les labels
        draw = ImageDraw.Draw(composite)
        try:
            from PIL import ImageFont
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except (OSError, ImportError):
            font = ImageFont.load_default()

        draw.text((width // 2 - 30, 10), "AVANT", fill=(255, 255, 255), font=font)
        draw.text((width + 10 + width // 2 - 20, 10), "DIFF", fill=self.diff_color, font=font)
        draw.text((width * 2 + 20 + width // 2 - 30, 10), "APRÈS", fill=(255, 255, 255), font=font)

        return composite

    def _get_verdict(self, diff_percentage: float) -> str:
        """Retourne le verdict basé sur le pourcentage de différence."""
        if diff_percentage < 0:
            return "error"
        if diff_percentage <= 0.5:
            return "pass"
        if diff_percentage <= 5.0:
            return "warning"
        return "fail"

    def _compare_dom_trees(self, tree_before: Optional[dict], tree_after: Optional[dict]) -> float:
        """Calcule un score de similarité entre deux arbres DOM (0.0 à 1.0)."""
        if not tree_before or not tree_after:
            return 0.0

        def flatten_nodes(node) -> list[str]:
            if not isinstance(node, dict):
                return []
            if node.get("type") == "text":
                return [f"text:{node.get('content', '')}"]
            
            nodes = [f"tag:{node.get('tag', '')}#id:{node.get('id', '')}.cls:{node.get('class', '')}"]
            for child in node.get("children", []):
                nodes.extend(flatten_nodes(child))
            return nodes

        nodes1 = set(flatten_nodes(tree_before))
        nodes2 = set(flatten_nodes(tree_after))

        if not nodes1 and not nodes2:
            return 1.0
        
        intersection = len(nodes1 & nodes2)
        union = len(nodes1 | nodes2)
        return round(intersection / union, 4) if union > 0 else 1.0

