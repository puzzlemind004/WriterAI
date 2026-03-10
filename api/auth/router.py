"""
Routes d'authentification : register, login, refresh, logout, me.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import db_session, get_current_user
from api.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from api.auth.service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    rotate_refresh_token, revoke_refresh_token,
)
from config.settings import settings
from engine.storage.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.refresh_token_expire_days * 86400,
    )


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(db_session),
):
    # Vérifie unicité email (même message générique pour éviter l'énumération)
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    session.add(user)
    await session.flush()
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    access_token = create_access_token(user.id)
    user_agent = request.headers.get("user-agent")
    raw_refresh = await create_refresh_token(session, user.id, user_agent)

    _set_refresh_cookie(response, raw_refresh)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    raw_token = request.cookies.get(_REFRESH_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Refresh token manquant")

    user_agent = request.headers.get("user-agent")
    new_refresh, new_access = await rotate_refresh_token(session, raw_token, user_agent)

    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(access_token=new_access)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
):
    raw_token = request.cookies.get(_REFRESH_COOKIE)
    if raw_token:
        await revoke_refresh_token(session, raw_token)

    response.delete_cookie(key=_REFRESH_COOKIE, path="/")


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return current_user
