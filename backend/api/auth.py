"""
Auto Maintenance - Endpoints d'authentification (Setup Admin, Login, Me).
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func

from backend.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from backend.models.database import async_session
from backend.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Schemas Pydantic ──────────────────────────────────────────────
class SetupStatusResponse(BaseModel):
    is_setup_completed: bool


class AdminSetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


# ── Endpoints ─────────────────────────────────────────────────────

@router.get("/setup-status", response_model=SetupStatusResponse)
async def get_setup_status() -> SetupStatusResponse:
    """
    Vérifie si l'application a déjà été configurée avec au moins un utilisateur administrateur.
    """
    async with async_session() as session:
        result = await session.execute(select(func.count(User.id)))
        count = result.scalar() or 0
        return SetupStatusResponse(is_setup_completed=count > 0)


@router.post("/setup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def setup_admin(payload: AdminSetupRequest) -> TokenResponse:
    """
    Création initiale du premier utilisateur Administrateur (premier lancement uniquement).
    """
    async with async_session() as session:
        result = await session.execute(select(func.count(User.id)))
        count = result.scalar() or 0
        if count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="L'application a déjà été initialisée. Veuillez vous connecter.",
            )

        # Créer le premier administrateur
        new_admin = User(
            username=payload.username.strip(),
            email=payload.email.strip() if payload.email else None,
            hashed_password=hash_password(payload.password),
            role="admin",
        )
        session.add(new_admin)
        await session.commit()
        await session.refresh(new_admin)

        # Générer le token d'accès immédiat
        access_token = create_access_token(data={"sub": new_admin.id, "username": new_admin.username})

        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(new_admin),
        )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """
    Authentification d'un utilisateur et génération d'un token JWT.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == payload.username.strip())
        )
        user = result.scalar_one_or_none()

        if not user or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Nom d'utilisateur ou mot de passe incorrect",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = create_access_token(data={"sub": user.id, "username": user.username})

        return TokenResponse(
            access_token=access_token,
            user=UserResponse.model_validate(user),
        )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """
    Retourne les informations de l'utilisateur connecté.
    """
    return UserResponse.model_validate(current_user)
