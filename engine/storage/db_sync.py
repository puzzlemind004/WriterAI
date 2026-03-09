"""
Pont synchrone vers la base de données async.

Le pipeline tourne dans un thread synchrone (ThreadPoolExecutor de FastAPI).
Pour persister en DB depuis ce thread, on utilise run_coroutine_threadsafe
avec la loop asyncio du process principal.

Usage :
    persister = SyncDBPersister(project_id, loop)
    persister.upsert_chapter(number=1, state="writing", brief_path="...")
    persister.update_chapter(number=1, state="validated", score=7.5)
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SyncDBPersister:
    """
    Wrapper synchrone pour persister l'état du pipeline en DB.
    Toutes les méthodes sont synchrones et peuvent être appelées depuis n'importe quel thread.
    """

    def __init__(self, project_id: str, loop: asyncio.AbstractEventLoop):
        self.project_id = project_id
        self._loop = loop

    def _run(self, coro) -> None:
        """Exécute une coroutine depuis un thread synchrone et attend le résultat."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            future.result(timeout=10)
        except Exception as e:
            logger.warning(f"[db_sync] Erreur persistence DB : {e}")

    def upsert_chapter(
        self,
        number: int,
        state: str,
        brief_path: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        """Crée ou met à jour une ligne Chapter (utilisé lors du planning)."""
        self._run(self._async_upsert_chapter(number, state, brief_path, title))

    def update_chapter(
        self,
        number: int,
        state: str,
        content_path: Optional[str] = None,
        score: Optional[float] = None,
        revision_count: Optional[int] = None,
        title: Optional[str] = None,
    ) -> None:
        """Met à jour l'état d'un chapitre existant."""
        self._run(self._async_update_chapter(number, state, content_path, score, revision_count, title))

    def mark_project_status(self, status: str) -> None:
        """Met à jour le statut du projet (running/completed/error)."""
        # Le statut projet est géré en mémoire par background.py
        # Cette méthode est un no-op pour l'instant (statut = état du pipeline en mémoire)
        pass

    # --- Coroutines async ---

    async def _async_upsert_chapter(
        self,
        number: int,
        state: str,
        brief_path: Optional[str],
        title: Optional[str],
    ) -> None:
        from engine.storage.database import AsyncSessionLocal
        from engine.storage.models import Chapter
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chapter).where(
                    Chapter.project_id == self.project_id,
                    Chapter.number == number,
                )
            )
            chapter = result.scalar_one_or_none()

            if chapter is None:
                chapter = Chapter(
                    project_id=self.project_id,
                    number=number,
                    state=state,
                )
                session.add(chapter)
            else:
                chapter.state = state

            if brief_path is not None:
                chapter.brief_path = brief_path
            if title is not None:
                chapter.title = title

            await session.commit()

    async def _async_update_chapter(
        self,
        number: int,
        state: str,
        content_path: Optional[str],
        score: Optional[float],
        revision_count: Optional[int],
        title: Optional[str],
    ) -> None:
        from engine.storage.database import AsyncSessionLocal
        from engine.storage.models import Chapter
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chapter).where(
                    Chapter.project_id == self.project_id,
                    Chapter.number == number,
                )
            )
            chapter = result.scalar_one_or_none()
            if chapter is None:
                logger.warning(f"[db_sync] Chapter {number} introuvable pour update")
                return

            chapter.state = state
            if content_path is not None:
                chapter.content_path = content_path
            if score is not None:
                chapter.last_score = score
            if revision_count is not None:
                chapter.revision_count = revision_count
            if title is not None:
                chapter.title = title

            await session.commit()
