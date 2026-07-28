"""
Auto Maintenance - Schémas Pydantic pour validation API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Project ───────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    domain: Optional[str] = None  # Auto-généré si absent
    wpress_filename: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    domain: str
    status: str
    wpress_file: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectList(BaseModel):
    projects: list[ProjectResponse]
    total: int


# ── Workflow ──────────────────────────────────────────────────────
class WorkflowStart(BaseModel):
    project_id: int
    steps: Optional[list[str]] = None  # None = toutes les étapes
    selected_updates: Optional[list[str]] = None  # plugins/thèmes à mettre à jour
    import_only: bool = False  # Si True: setup DDEV/WP + import .wpress sans maintenance


class WorkflowResponse(BaseModel):
    id: int
    project_id: int
    status: str
    current_step: Optional[str] = None
    steps_completed: list[str] = []
    steps_failed: list[str] = []
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Updates ───────────────────────────────────────────────────────
class UpdateItem(BaseModel):
    name: str
    type: str  # core | plugin | theme
    current_version: str
    new_version: str
    status: str = "available"  # available | updated | failed


class UpdatesListResponse(BaseModel):
    project_id: int
    core: Optional[UpdateItem] = None
    plugins: list[UpdateItem] = []
    themes: list[UpdateItem] = []
    total_available: int = 0


class UpdatesApplyRequest(BaseModel):
    project_id: int
    update_core: bool = False
    plugin_names: list[str] = []
    theme_names: list[str] = []


class UpdateResult(BaseModel):
    name: str
    type: str
    success: bool
    message: str
    old_version: str
    new_version: Optional[str] = None


class UpdatesApplyResponse(BaseModel):
    project_id: int
    results: list[UpdateResult]
    total_success: int
    total_failed: int


# ── VRT ───────────────────────────────────────────────────────────
class VRTReportItem(BaseModel):
    page_name: str
    page_url: str
    device: str
    before_screenshot: Optional[str] = None
    after_screenshot: Optional[str] = None
    diff_image: Optional[str] = None
    diff_percentage: Optional[float] = None
    ssim_score: Optional[float] = None
    passed: Optional[bool] = None


class VRTReportResponse(BaseModel):
    project_id: int
    total_pages: int
    total_passed: int
    total_failed: int
    updates_total: int = 0
    updates_success: int = 0
    updates_failed: int = 0
    items: list[VRTReportItem]


# ── WebSocket ─────────────────────────────────────────────────────
class LogMessage(BaseModel):
    timestamp: str
    level: str  # info | warning | error | success | debug
    step: Optional[str] = None
    message: str
    details: Optional[dict] = None
    progress: Optional[float] = None  # 0-100


class WorkflowProgress(BaseModel):
    workflow_id: int
    project_id: int
    status: str
    current_step: Optional[str] = None
    progress: float = 0.0  # 0-100
    estimated_remaining: Optional[int] = None  # secondes


# ── Generic ───────────────────────────────────────────────────────
class StatusResponse(BaseModel):
    status: str
    message: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    step: Optional[str] = None
