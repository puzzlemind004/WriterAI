"""
Endpoint pour lister les modèles disponibles selon la source choisie.
- source=local  → interroge Ollama via OLLAMA_API_BASE (défaut: host.docker.internal:11434)
- source=<id>   → liste statique selon le provider de la clé API stockée
"""
import httpx
import logging
import os
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import db_session, get_current_user
from engine.storage.models import User, ApiKey

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["models"])

# Modèles courants par provider cloud (liste statique, non exhaustive)
CLOUD_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o3-mini",
        "o4-mini",
    ],
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "gemini": [
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-small-latest",
        "codestral-latest",
    ],
    "cohere": [
        "command-r-plus",
        "command-r",
    ],
}

OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://host.docker.internal:11434")


@router.get("")
async def list_models(
    source: str = Query("local", description="'local' ou l'id d'une clé API"),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Retourne { models: [...], provider: "..." }
    """
    if source == "local":
        models = await _fetch_ollama_models()
        return {"provider": "ollama", "models": models}

    # Résolution via clé stockée
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == source, ApiKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        return {"provider": "unknown", "models": []}

    models = CLOUD_MODELS.get(key.provider, [])
    return {"provider": key.provider, "models": models}


async def _fetch_ollama_models() -> list[str]:
    """Interroge l'API Ollama locale pour lister les modèles installés."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_API_BASE}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.warning(f"Impossible de contacter Ollama : {e}")
        return []
