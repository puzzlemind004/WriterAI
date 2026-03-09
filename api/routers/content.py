"""
Routes pour lire le contenu généré : chapitres et lorebook.
"""
import logging
from fastapi import APIRouter, HTTPException, Path
from api.schemas import ChapterResponse, LorebookResponse
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["content"])


def _extract_title(content: str, chapter_number: int) -> str | None:
    if not content:
        return None
    lines = content.splitlines()
    if lines and lines[0].startswith("#"):
        return lines[0].lstrip("#").strip()
    return None


def _get_file_manager(project_id: str) -> FileManager:
    try:
        return FileManager(project_id)
    except Exception as e:
        logger.error(f"Impossible d'accéder au projet {project_id} : {e}")
        raise HTTPException(status_code=404, detail="Projet introuvable ou inaccessible")


@router.get("/{project_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(project_id: str):
    fm = _get_file_manager(project_id)
    result = []
    chapter_num = 1

    try:
        while True:
            content = fm.read_chapter(chapter_num)
            brief = fm.read_chapter_brief(chapter_num)
            if not content and not brief:
                break
            result.append(ChapterResponse(
                number=chapter_num,
                title=_extract_title(content, chapter_num),
                state="validated" if content else "planned",
                content=content or None,
                score=None,
                revision_count=0,
            ))
            chapter_num += 1
    except Exception as e:
        logger.error(f"Erreur lecture chapitres projet {project_id} : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture des chapitres")

    return result


@router.get("/{project_id}/chapters/{number}", response_model=ChapterResponse)
async def get_chapter(
    project_id: str,
    number: int = Path(ge=1, description="Numéro du chapitre (>= 1)"),
):
    fm = _get_file_manager(project_id)

    try:
        content = fm.read_chapter(number)
        brief = fm.read_chapter_brief(number)
    except Exception as e:
        logger.error(f"Erreur lecture chapitre {number} projet {project_id} : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture du chapitre")

    if not content and not brief:
        raise HTTPException(status_code=404, detail=f"Chapitre {number} introuvable")

    return ChapterResponse(
        number=number,
        title=_extract_title(content, number),
        state="validated" if content else "planned",
        content=content or None,
        score=None,
        revision_count=0,
    )


@router.get("/{project_id}/lorebook", response_model=LorebookResponse)
async def get_lorebook(project_id: str):
    fm = _get_file_manager(project_id)

    try:
        characters = fm.read_all_characters()
        places = fm.read_all_places()
        lore = _read_all_lore(fm)
    except Exception as e:
        logger.error(f"Erreur lecture lorebook projet {project_id} : {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la lecture du lorebook")

    return LorebookResponse(
        characters=characters,
        places=places,
        lore=lore,
    )


def _read_all_lore(fm: FileManager) -> dict[str, str]:
    entities = fm.list_lorebook_entities("lore")
    result = {}
    for name in entities:
        content = fm.read_lorebook_file(f"lore/{name}.md")
        if content:
            result[name] = content
    return result
