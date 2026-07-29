"""
Auto Maintenance - Endpoints d'administration des paramètres système.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.models.database import async_session
from backend.models.settings import SystemSetting
from backend.core.config import settings

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Schemas Pydantic ──────────────────────────────────────────────
class SystemSettingsSchema(BaseModel):
    vrt_min_ssim_score: float = Field(default=0.95, ge=0.0, le=1.0, description="Taux SSIM minimal pour validation PASS")
    vrt_max_diff_percentage: float = Field(default=5.0, ge=0.0, le=100.0, description="Seuil max de différence de pixels (%)")
    vrt_anti_aliasing_tolerance: int = Field(default=2, ge=0, le=20, description="Tolérance anti-aliasing (px)")
    vrt_enable_dom_snapshot: bool = Field(default=True, description="Masquer les éléments dynamiques lors des captures")
    screenshot_stabilize_delay: int = Field(default=1000, ge=0, le=10000, description="Délai de stabilisation avant capture (ms)")
    screenshot_load_timeout: int = Field(default=15000, ge=1000, le=60000, description="Timeout de chargement de page (ms)")
    screenshot_enabled_devices: str = Field(default="desktop,mobile", description="Appareils actifs séparés par virgule")
    max_concurrent_workflows: int = Field(default=2, ge=1, le=10, description="Nombre de workflows simultanés max")
    playwright_timeout: int = Field(default=60000, ge=5000, le=300000, description="Timeout Playwright (ms)")
    wp_locale: str = Field(default="fr_FR", description="Langue WordPress par défaut")
    wp_admin_email: str = Field(default="admin@localhost.local", description="Email administrateur WordPress par défaut")


# ── Helper ────────────────────────────────────────────────────────
async def get_system_settings_db() -> dict:
    """Récupère les paramètres enregistrés en BDD ou retombe sur les défauts."""
    async with async_session() as session:
        result = await session.execute(select(SystemSetting).where(SystemSetting.key == "global"))
        setting = result.scalar_one_or_none()
        default_dict = SystemSettingsSchema().model_dump()
        if setting and setting.value:
            merged = {**default_dict, **setting.value}
            return merged
        return default_dict


# ── Endpoints ─────────────────────────────────────────────────────
@router.get("", response_model=SystemSettingsSchema)
async def get_settings() -> SystemSettingsSchema:
    """Récupère la configuration système actuelle."""
    settings_dict = await get_system_settings_db()
    return SystemSettingsSchema(**settings_dict)


@router.put("", response_model=SystemSettingsSchema)
async def update_settings(payload: SystemSettingsSchema) -> SystemSettingsSchema:
    """Met à jour les paramètres système."""
    async with async_session() as session:
        result = await session.execute(select(SystemSetting).where(SystemSetting.key == "global"))
        setting = result.scalar_one_or_none()
        
        new_values = payload.model_dump()
        if not setting:
            setting = SystemSetting(key="global", value=new_values)
            session.add(setting)
        else:
            setting.value = new_values
        
        await session.commit()
        await session.refresh(setting)

        # Synchroniser les variables globales modifiables en mémoire
        settings.max_concurrent_workflows = payload.max_concurrent_workflows
        settings.playwright_timeout = payload.playwright_timeout
        settings.vrt_threshold = payload.vrt_max_diff_percentage
        settings.vrt_anti_aliasing_tolerance = payload.vrt_anti_aliasing_tolerance
        settings.wp_locale = payload.wp_locale
        settings.wp_admin_email = payload.wp_admin_email

        return SystemSettingsSchema(**setting.value)
