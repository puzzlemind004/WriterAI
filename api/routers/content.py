"""
Routes pour lire le contenu généré : chapitres et lorebook.
Les métadonnées viennent de la DB, le contenu narratif des fichiers markdown.
"""
import logging
from fastapi import APIRouter, HTTPException, Path, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import db_session, get_current_user
from api.schemas import ChapterResponse, LorebookResponse
from engine.storage.file_manager import FileManager
from engine.storage.models import Chapter, Project, User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["content"])


def _get_file_manager(project_id: str) -> FileManager:
    try:
        return FileManager(project_id)
    except Exception as e:
        logger.error(f"Impossible d'accéder au projet {project_id} : {e}")
        raise HTTPException(status_code=404, detail="Projet introuvable ou inaccessible")


def _extract_title(content: str) -> str | None:
    if not content:
        return None
    lines = content.splitlines()
    if lines and lines[0].startswith("#"):
        return lines[0].lstrip("#").strip()
    return None


@router.get("/{project_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(
    project_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    # Vérifie que le projet existe et appartient à l'utilisateur
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    # Récupère les chapitres depuis la DB
    result = await session.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.number)
    )
    db_chapters = result.scalars().all()

    if not db_chapters:
        # Fallback : lecture des fichiers markdown si la DB est vide (migration, test e2e ancien)
        return _list_chapters_from_files(project_id)

    fm = _get_file_manager(project_id)
    chapters = []
    for ch in db_chapters:
        content = fm.read_chapter(ch.number) if ch.content_path else None
        title = ch.title or _extract_title(content or "")
        chapters.append(ChapterResponse(
            number=ch.number,
            title=title,
            state=ch.state,
            content=content or None,
            score=ch.last_score,
            revision_count=ch.revision_count,
        ))
    return chapters


@router.get("/{project_id}/chapters/{number}", response_model=ChapterResponse)
async def get_chapter(
    project_id: str,
    number: int = Path(ge=1, description="Numéro du chapitre (>= 1)"),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    result = await session.execute(
        select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.number == number,
        )
    )
    ch = result.scalar_one_or_none()

    if ch is None:
        # Fallback fichiers
        fm = _get_file_manager(project_id)
        content = fm.read_chapter(number)
        brief = fm.read_chapter_brief(number)
        if not content and not brief:
            raise HTTPException(status_code=404, detail=f"Chapitre {number} introuvable")
        return ChapterResponse(
            number=number,
            title=_extract_title(content),
            state="validated" if content else "planned",
            content=content or None,
            score=None,
            revision_count=0,
        )

    fm = _get_file_manager(project_id)
    content = fm.read_chapter(number) if ch.content_path else None
    title = ch.title or _extract_title(content or "")
    return ChapterResponse(
        number=number,
        title=title,
        state=ch.state,
        content=content or None,
        score=ch.last_score,
        revision_count=ch.revision_count,
    )


@router.get("/{project_id}/lorebook", response_model=LorebookResponse)
async def get_lorebook(
    project_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    fm = _get_file_manager(project_id)
    try:
        characters = fm.read_all_characters()
        places = fm.read_all_places()
        lore = _read_all_lore(fm)
    except Exception as e:
        logger.error(f"Erreur lecture lorebook projet {project_id} : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture du lorebook")

    return LorebookResponse(characters=characters, places=places, lore=lore)


def _read_all_lore(fm: FileManager) -> dict[str, str]:
    entities = fm.list_lorebook_entities("lore")
    return {
        name: content
        for name in entities
        if (content := fm.read_lorebook_file(f"lore/{name}.md"))
    }


def _list_chapters_from_files(project_id: str) -> list[ChapterResponse]:
    """Fallback : construit la liste des chapitres depuis les fichiers markdown."""
    try:
        fm = FileManager(project_id)
        result = []
        chapter_num = 1
        while True:
            content = fm.read_chapter(chapter_num)
            brief = fm.read_chapter_brief(chapter_num)
            if not content and not brief:
                break
            result.append(ChapterResponse(
                number=chapter_num,
                title=_extract_title(content),
                state="validated" if content else "planned",
                content=content or None,
                score=None,
                revision_count=0,
            ))
            chapter_num += 1
        return result
    except Exception as e:
        logger.error(f"Fallback lecture chapitres {project_id} : {e}")
        return []
