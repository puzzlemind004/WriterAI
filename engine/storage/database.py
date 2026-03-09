"""
Initialisation et gestion de la connexion base de données.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from .models import Base
from config.settings import settings


def _make_engine_kwargs() -> dict:
    """Retourne les kwargs pour create_async_engine selon le type de DB."""
    if settings.database_url.startswith("postgresql"):
        return {"connect_args": {"ssl": "disable"}}
    return {}


# Engine async (pour FastAPI)
async_engine = create_async_engine(settings.database_url, echo=False, **_make_engine_kwargs())
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)

# Engine sync (pour Celery workers — SQLite uniquement)
_sync_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
sync_engine = create_engine(_sync_url, echo=False) if _sync_url.startswith("sqlite") else None


async def init_db() -> None:
    """Crée toutes les tables si elles n'existent pas."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dépendance FastAPI pour obtenir une session DB."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
