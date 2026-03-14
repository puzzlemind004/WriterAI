"""
Routes du compte utilisateur : infos, mot de passe, clés API.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import db_session, get_current_user
from api.account.schemas import ChangePasswordRequest, ApiKeyCreate, ApiKeyResponse
from api.auth.schemas import UserResponse
from api.auth.service import hash_password, verify_password
from engine.storage.models import User, ApiKey

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
    current_user.hashed_password = hash_password(body.new_password)
    session.add(current_user)


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    )
    return result.scalars().all()


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    api_key = ApiKey(
        user_id=current_user.id,
        label=body.label,
        provider=body.provider,
    )
    api_key.key_value = body.key_value
    session.add(api_key)
    await session.flush()
    return api_key


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="Clé introuvable")
    await session.delete(api_key)
