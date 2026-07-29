"""
Auto Maintenance - Modèle de paramètres système (SQLAlchemy).
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, JSON, DateTime
from backend.models.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    key: str = Column(String(100), unique=True, nullable=False, index=True)
    value: dict = Column(JSON, nullable=False, default=dict)
    updated_at: datetime = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
