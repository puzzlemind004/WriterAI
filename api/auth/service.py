"""
Service d'authentification : hashing, JWT, refresh tokens.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.settings import settings
from engine.storage.models import RefreshToken, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Passwords ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# --- Access tokens (JWT) ---

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Retourne le user_id ou lève HTTP 401."""
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise credentials_error
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise credentials_error
        return user_id
    except JWTError:
        raise credentials_error


# --- Refresh tokens ---

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_refresh_token(
    session: AsyncSession,
    user_id: str,
    user_agent: Optional[str] = None,
) -> str:
    """Crée un refresh token en DB et retourne le token brut."""
    raw = secrets.token_hex(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    rt = RefreshToken(
        token_hash=token_hash,
        user_id=user_id,
        expires_at=expires_at,
        user_agent=user_agent,
    )
    session.add(rt)
    await session.flush()
    return raw


async def rotate_refresh_token(
    session: AsyncSession,
    raw_token: str,
    user_agent: Optional[str] = None,
) -> tuple[str, str]:
    """
    Vérifie le refresh token, le révoque, et émet un nouveau couple (refresh, access).
    Retourne (new_raw_refresh_token, new_access_token).
    """
    token_hash = _hash_token(raw_token)
    result = await session.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
    )
    rt = result.scalar_one_or_none()

    if rt is None or rt.revoked or rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide ou expiré",
        )

    # Révoque l'ancien (flush immédiat pour libérer le lock dès que possible)
    rt.revoked = True
    await session.flush()

    # Émet le nouveau
    new_access = create_access_token(rt.user_id)
    new_refresh = await create_refresh_token(session, rt.user_id, user_agent)

    return new_refresh, new_access


async def revoke_refresh_token(session: AsyncSession, raw_token: str) -> None:
    """Révoque un refresh token (logout)."""
    token_hash = _hash_token(raw_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        rt.revoked = True
