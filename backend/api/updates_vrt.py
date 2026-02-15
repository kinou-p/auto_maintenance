"""
Auto Maintenance - Routes API Updates & VRT.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.core.config import settings
from backend.managers.ddev_manager import DDEVManager
from backend.managers.wordpress_manager import WordPressManager
from backend.managers.vrt_manager import VRTManager
from backend.models.database import Project, VRTReport, async_session
from backend.models.schemas import (
    UpdatesApplyRequest,
    UpdatesApplyResponse,
    UpdatesListResponse,
    VRTReportResponse,
    VRTReportItem,
)

router = APIRouter(tags=["updates", "vrt"])


# ── Updates ───────────────────────────────────────────────────────

@router.get("/projects/{project_id}/updates", response_model=UpdatesListResponse)
async def list_updates(project_id: int) -> UpdatesListResponse:
    """Liste les mises à jour disponibles pour un projet."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

    ddev = DDEVManager(project.name)
    wp = WordPressManager(project.name, ddev)
    updates = await wp.list_updates()

    return UpdatesListResponse(
        project_id=project_id,
        core=updates.get("core"),
        plugins=updates.get("plugins", []),
        themes=updates.get("themes", []),
        total_available=updates.get("total_available", 0),
    )


@router.post("/projects/{project_id}/updates/apply", response_model=UpdatesApplyResponse)
async def apply_updates(project_id: int, request: UpdatesApplyRequest) -> UpdatesApplyResponse:
    """Applique les mises à jour sélectionnées."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

    ddev = DDEVManager(project.name)
    wp = WordPressManager(project.name, ddev)

    results = await wp.apply_updates(
        update_core=request.update_core,
        plugin_names=request.plugin_names,
        theme_names=request.theme_names,
    )

    return UpdatesApplyResponse(
        project_id=project_id,
        results=results,
        total_success=sum(1 for r in results if r.success),
        total_failed=sum(1 for r in results if not r.success),
    )


# ── VRT ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/vrt", response_model=VRTReportResponse)
async def get_vrt_report(project_id: int) -> VRTReportResponse:
    """Récupère le rapport VRT d'un projet."""
    async with async_session() as session:
        result = await session.execute(
            select(VRTReport)
            .where(VRTReport.project_id == project_id)
            .order_by(VRTReport.created_at.desc())
        )
        reports = result.scalars().all()

        if not reports:
            raise HTTPException(404, "Aucun rapport VRT trouvé pour ce projet.")

        items = [
            VRTReportItem(
                page_name=r.page_name,
                page_url=r.page_url,
                device=r.device,
                before_screenshot=r.before_screenshot,
                after_screenshot=r.after_screenshot,
                diff_image=r.diff_image,
                diff_percentage=r.diff_percentage,
                ssim_score=r.ssim_score,
                passed=bool(r.passed),
            )
            for r in reports
        ]

        # Récupérer les stats d'update depuis le workflow associé (si dispo)
        updates_stats = {"total": 0, "success": 0, "failed": 0}
        
        # On suppose que tous les items du rapport VRT viennent du même workflow
        # On prend le workflow_id du premier item
        if reports and reports[0].workflow_id:
            from backend.models.database import Workflow
            workflow = await session.get(Workflow, reports[0].workflow_id)
            if workflow and workflow.updates_stats:
                updates_stats = workflow.updates_stats

        return VRTReportResponse(
            project_id=project_id,
            total_pages=len(items),
            total_passed=sum(1 for i in items if i.passed),
            total_failed=sum(1 for i in items if not i.passed),
            updates_total=updates_stats.get("total", 0),
            updates_success=updates_stats.get("success", 0),
            updates_failed=updates_stats.get("failed", 0),
            items=items,
        )


@router.get("/projects/{project_id}/vrt/report-json")
async def get_vrt_json_report(project_id: int) -> dict:
    """Récupère le rapport VRT complet au format JSON."""
    async with async_session() as session:
        project = await session.get(Project, project_id)
        if not project:
            raise HTTPException(404, f"Projet {project_id} introuvable.")

    report_path = settings.reports_dir / f"{project.name}_vrt_report.json"
    if not report_path.exists():
        raise HTTPException(404, "Rapport VRT JSON introuvable.")

    import json
    return json.loads(report_path.read_text())


# ── Fichiers statiques (screenshots, diffs) ──────────────────────

@router.get("/screenshots/{project_name}/{phase}/{filename}")
async def get_screenshot(project_name: str, phase: str, filename: str) -> FileResponse:
    """Sert un fichier screenshot."""
    filepath = settings.screenshots_dir / project_name / phase / filename
    if not filepath.exists():
        raise HTTPException(404, "Screenshot introuvable.")
    return FileResponse(str(filepath), media_type="image/png")
