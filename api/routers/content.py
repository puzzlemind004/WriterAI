"""
Routes pour lire le contenu généré : chapitres et lorebook.
Les métadonnées viennent de la DB, le contenu narratif des fichiers markdown.
"""
import logging
from fastapi import APIRouter, HTTPException, Path, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import asyncio
from api.dependencies import db_session, get_current_user
from api.schemas import (
    ChapterResponse, ChapterUpdateRequest, ChapterVersionResponse,
    ChapterRevisionRequest, LorebookResponse,
)
from api import background
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
        content = fm.read_chapter(ch.number) or None
        brief = fm.read_chapter_brief(ch.number) or None
        title = ch.title or _extract_title(content or "")
        chapters.append(ChapterResponse(
            number=ch.number,
            title=title,
            state=ch.state,
            content=content,
            score=ch.last_score,
            revision_count=ch.revision_count,
            brief=brief,
            critic_comments=ch.last_critic_comments or [],
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
    content = fm.read_chapter(number) or None
    brief = fm.read_chapter_brief(number) or None
    title = ch.title or _extract_title(content or "")
    return ChapterResponse(
        number=number,
        title=title,
        state=ch.state,
        content=content or None,
        score=ch.last_score,
        revision_count=ch.revision_count,
        brief=brief,
        critic_comments=ch.last_critic_comments or [],
    )


@router.patch("/{project_id}/chapters/{number}", response_model=ChapterResponse)
async def update_chapter(
    project_id: str,
    number: int = Path(ge=1),
    body: ChapterUpdateRequest = ...,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    if background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Pipeline en cours, impossible de modifier")

    result = await session.execute(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.number == number)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail=f"Chapitre {number} introuvable")

    fm = _get_file_manager(project_id)
    fm.write_chapter(number, body.content)

    if body.title is not None:
        ch.title = body.title
    ch.is_user_controlled = True
    session.add(ch)
    await session.flush()

    brief = fm.read_chapter_brief(number) or None
    return ChapterResponse(
        number=ch.number,
        title=ch.title or _extract_title(body.content),
        state=ch.state,
        content=body.content,
        score=ch.last_score,
        revision_count=ch.revision_count,
        brief=brief,
        critic_comments=ch.last_critic_comments or [],
    )


@router.get("/{project_id}/chapters/{number}/versions", response_model=list[ChapterVersionResponse])
async def get_chapter_versions(
    project_id: str,
    number: int = Path(ge=1),
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    fm = _get_file_manager(project_id)
    version_paths = fm.get_chapter_versions(number)
    versions = []
    for i, path in enumerate(version_paths, start=1):
        content = open(path, encoding="utf-8").read()
        versions.append(ChapterVersionResponse(
            version=i,
            content=content,
            word_count=len(content.split()),
        ))
    return versions


@router.post("/{project_id}/chapters/{number}/revise", response_model=ChapterResponse)
async def revise_chapter(
    project_id: str,
    number: int = Path(ge=1),
    body: ChapterRevisionRequest = ...,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    if background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Pipeline en cours, impossible de lancer une révision")

    result = await session.execute(
        select(Chapter).where(Chapter.project_id == project_id, Chapter.number == number)
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(status_code=404, detail=f"Chapitre {number} introuvable")

    fm = _get_file_manager(project_id)
    chapter_text = fm.read_chapter(number)
    if not chapter_text.strip():
        raise HTTPException(status_code=400, detail="Le chapitre est vide, impossible de réviser")

    # Construction du contexte pour le RevisorAgent
    from engine.agents.revisor import RevisorAgent
    from engine.agents.base import AgentContext
    from engine.llm.client import LLMClient, LLMConfig

    commentaires = [
        f"[Passage ciblé : «\u202f{c.selected_text[:120]}\u202f»] → {c.comment}"
        for c in body.comments
    ]

    llm_config = LLMConfig(
        provider=project.llm_provider,
        model=project.llm_model,
        api_key=project.llm_api_key,
        api_base=project.llm_api_base,
        thinking=project.llm_thinking,
    )
    ctx = AgentContext(
        project_id=project_id,
        llm=LLMClient(llm_config),
        chapter_number=number,
        chapter_id=ch.id,
        extra={
            "commentaires_constructifs": commentaires,
            "points_faibles": [],
            "note_globale": ch.last_score or "?",
            "writing_style": project.writing_style or "",
            "tone_keywords": project.tone_keywords or [],
        },
    )

    agent = RevisorAgent()
    agent_result = await asyncio.to_thread(agent.run, ctx)

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Révision échouée")

    # Relit le contenu révisé depuis le fichier
    content = fm.read_chapter(number) or None
    brief = fm.read_chapter_brief(number) or None
    ch.revision_count = (ch.revision_count or 0) + 1
    ch.is_user_controlled = True
    session.add(ch)
    await session.flush()

    return ChapterResponse(
        number=ch.number,
        title=ch.title or _extract_title(content or ""),
        state=ch.state,
        content=content,
        score=ch.last_score,
        revision_count=ch.revision_count,
        brief=brief,
        critic_comments=ch.last_critic_comments or [],
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
