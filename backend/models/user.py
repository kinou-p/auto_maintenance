"""
Auto Maintenance - Modèle de données Utilisateur (SQLAlchemy).
"""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime

from backend.models.database import Base


class User(Base):
    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    username: str = Column(String(150), nullable=False, unique=True, index=True)
    email: str = Column(String(255), nullable=True)
    hashed_password: str = Column(String(255), nullable=False)
    role: str = Column(String(50), nullable=False, default="admin")
    created_at: datetime = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
