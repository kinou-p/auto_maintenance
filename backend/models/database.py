"""
Auto Maintenance - Modèles de base de données (SQLAlchemy async).

Stocke l'historique des projets, workflows et rapports VRT.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from backend.core.config import settings
from backend.models.user import User  # noqa: F401


# ── Engine & Session ──────────────────────────────────────────────
def _sqlite_connect_args() -> dict:
    """Args SQLite optimisés pour concurrence (WAL + busy timeout)."""
    if "sqlite" not in settings.database_url:
        return {}
    return {
        "check_same_thread": False,
        "timeout": 60.0,
    }


engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    connect_args=_sqlite_connect_args(),
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    """Base déclarative partagée."""
    pass


# ── Enums ─────────────────────────────────────────────────────────
class ProjectStatus(str, enum.Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    WORDPRESS_INSTALLED = "wordpress_installed"
    IMPORTING = "importing"
    READY = "ready"
    PENDING = "pending"
    MAINTENANCE_IN_PROGRESS = "maintenance_in_progress"
    MAINTENANCE_DONE = "maintenance_done"
    ERROR = "error"
    STOPPED = "stopped"
    PAUSED = "paused"
    DELETING = "deleting"


class WorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(str, enum.Enum):
    DDEV_CREATE = "ddev_create"
    DNS_SETUP = "dns_setup"
    WP_INSTALL = "wp_install"
    PLUGIN_INSTALL = "plugin_install"
    WPRESS_IMPORT = "wpress_import"
    SCREENSHOTS_BEFORE = "screenshots_before"
    UPDATES_LIST = "updates_list"
    UPDATES_APPLY = "updates_apply"
    SCREENSHOTS_AFTER = "screenshots_after"
    VRT_COMPARE = "vrt_compare"


# ── Models ────────────────────────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False, unique=True, index=True)
    domain: str = Column(String(255), nullable=False)
    ddev_dir: str = Column(String(512), nullable=True)
    status: ProjectStatus = Column(
        Enum(ProjectStatus), default=ProjectStatus.CREATED, nullable=False
    )
    wpress_file: Optional[str] = Column(String(512), nullable=True)
    created_at: datetime = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relations
    workflows = relationship("Workflow", back_populates="project", cascade="all, delete-orphan")
    vrt_reports = relationship("VRTReport", back_populates="project", cascade="all, delete-orphan")


class Workflow(Base):
    __tablename__ = "workflows"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    project_id: int = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status: WorkflowStatus = Column(
        Enum(WorkflowStatus), default=WorkflowStatus.PENDING, nullable=False
    )
    current_step: Optional[str] = Column(String(50), nullable=True)
    steps_completed: list = Column(JSON, default=list, nullable=False)
    steps_failed: list = Column(JSON, default=list, nullable=False)
    logs: list = Column(JSON, default=list, nullable=False)
    updates_stats: dict = Column(JSON, default=dict, nullable=False)
    options: dict = Column(JSON, default=dict, nullable=False)
    started_at: Optional[datetime] = Column(DateTime, nullable=True)
    completed_at: Optional[datetime] = Column(DateTime, nullable=True)
    created_at: datetime = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    error_message: Optional[str] = Column(Text, nullable=True)

    # Relations
    project = relationship("Project", back_populates="workflows")


class VRTReport(Base):
    __tablename__ = "vrt_reports"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    project_id: int = Column(Integer, ForeignKey("projects.id"), nullable=False)
    workflow_id: int = Column(Integer, ForeignKey("workflows.id"), nullable=True)
    page_url: str = Column(String(512), nullable=False)
    page_name: str = Column(String(255), nullable=False)
    device: str = Column(String(50), nullable=False)  # desktop | mobile
    before_screenshot: str = Column(String(512), nullable=True)
    after_screenshot: str = Column(String(512), nullable=True)
    diff_image: Optional[str] = Column(String(512), nullable=True)
    diff_percentage: Optional[float] = Column(Float, nullable=True)
    ssim_score: Optional[float] = Column(Float, nullable=True)
    passed: Optional[bool] = Column(Integer, nullable=True)  # SQLite n'a pas de bool natif
    created_at: datetime = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relations
    project = relationship("Project", back_populates="vrt_reports")


# ── Init DB ───────────────────────────────────────────────────────
from sqlalchemy import text

async def init_db() -> None:
    """Crée les tables si elles n'existent pas et active le mode WAL pour éviter tout verrouillage."""
    async with engine.begin() as conn:
        if "sqlite" in settings.database_url:
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA busy_timeout=60000;"))
            await conn.execute(text("PRAGMA synchronous=NORMAL;"))
            await conn.execute(text("PRAGMA foreign_keys=ON;"))
        await conn.run_sync(Base.metadata.create_all)

        # Migrations légères (colonnes ajoutées sans Alembic)
        if "sqlite" in settings.database_url:
            result = await conn.execute(text("PRAGMA table_info(workflows)"))
            columns = {row[1] for row in result.fetchall()}
            if "options" not in columns:
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN options JSON DEFAULT '{}'"))
            if "updates_stats" not in columns:
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN updates_stats JSON DEFAULT '{}'"))
