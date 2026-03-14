"""
Routes CRUD pour les projets.
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import db_session, get_current_user
from api.schemas import ProjectCreateRequest, ProjectUpdateRequest, ProjectDetail, ProjectSummary
from api import background
from engine.storage.models import Project, Chapter, User, ApiKey
from engine.storage.file_manager import FileManager
from config.settings import settings

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_status(project_id: str) -> str:
    return background.get_pipeline_state(project_id)["status"]


def _to_summary(project: Project, status: str) -> ProjectSummary:
    chapters_done = sum(
        1 for ch in project.chapters
        if ch.state == "validated"
    )
    return ProjectSummary(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        status=status,
        chapter_count=len(project.chapters),
        chapters_done=chapters_done,
    )


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    result = await session.execute(
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return [_to_summary(p, _project_status(p.id)) for p in projects]


@router.post("", response_model=ProjectDetail, status_code=201)
async def create_project(
    body: ProjectCreateRequest,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    import uuid
    project_id = str(uuid.uuid4())
    project_dir = os.path.join(settings.projects_dir, project_id)

    # Résolution de la clé API : soit inline, soit via l'ID d'une clé stockée
    resolved_api_key = body.llm.api_key
    if not resolved_api_key and body.llm.api_key_id:
        result = await session.execute(
            select(ApiKey).where(ApiKey.id == body.llm.api_key_id, ApiKey.user_id == current_user.id)
        )
        stored_key = result.scalar_one_or_none()
        if not stored_key:
            raise HTTPException(status_code=404, detail="Clé API introuvable")
        resolved_api_key = stored_key.key_value

    # N'utiliser api_base que pour Ollama — les providers cloud ont leur propre URL
    resolved_api_base = body.llm.api_base if body.llm.provider == "ollama" else None

    project = Project(
        id=project_id,
        name=body.name,
        source_text=body.source_text,
        llm_provider=body.llm.provider,
        llm_model=body.llm.model,
        llm_api_base=resolved_api_base,
        llm_api_key=resolved_api_key,
        llm_thinking=body.llm.thinking,
        target_chapter_count=body.target_chapter_count,
        writing_style=body.writing_style,
        tone_keywords=body.tone_keywords,
        min_validation_score=body.min_validation_score,
        max_revision_attempts=body.max_revision_attempts,
        project_dir=project_dir,
        owner_id=current_user.id,
    )
    # Stocke le pitch dans les metadata du projet
    project.source_text = body.source_text

    session.add(project)
    await session.flush()

    # Initialise la structure fichiers
    fm = FileManager(project_id)
    fm.init_project_structure()

    return ProjectDetail(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        status="idle",
        chapter_count=0,
        chapters_done=0,
        source_text=project.source_text or "",
        llm_provider=project.llm_provider,
        llm_model=project.llm_model,
        llm_thinking=project.llm_thinking,
        target_chapter_count=project.target_chapter_count,
        writing_style=project.writing_style,
        tone_keywords=project.tone_keywords or [],
        min_validation_score=project.min_validation_score,
        max_revision_attempts=project.max_revision_attempts,
    )


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    return ProjectDetail(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        status=_project_status(project_id),
        chapter_count=len(project.chapters),
        chapters_done=sum(1 for ch in project.chapters if ch.state == "validated"),
        source_text=getattr(project, "source_text", ""),
        llm_provider=project.llm_provider,
        llm_model=project.llm_model,
        llm_thinking=project.llm_thinking,
        target_chapter_count=project.target_chapter_count,
        writing_style=project.writing_style,
        tone_keywords=project.tone_keywords or [],
        min_validation_score=project.min_validation_score,
        max_revision_attempts=project.max_revision_attempts,
    )


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: str,
    body: ProjectUpdateRequest,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    if background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Pipeline en cours, impossible de modifier")

    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    if body.name is not None:
        project.name = body.name
    if body.source_text is not None:
        project.source_text = body.source_text
    if body.target_chapter_count is not None:
        project.target_chapter_count = body.target_chapter_count
    if body.writing_style is not None:
        project.writing_style = body.writing_style
    if body.tone_keywords is not None:
        project.tone_keywords = body.tone_keywords
    if body.min_validation_score is not None:
        project.min_validation_score = body.min_validation_score
    if body.max_revision_attempts is not None:
        project.max_revision_attempts = body.max_revision_attempts

    if body.llm is not None:
        resolved_api_key = body.llm.api_key
        if not resolved_api_key and body.llm.api_key_id:
            result = await session.execute(
                select(ApiKey).where(ApiKey.id == body.llm.api_key_id, ApiKey.user_id == current_user.id)
            )
            stored_key = result.scalar_one_or_none()
            if not stored_key:
                raise HTTPException(status_code=404, detail="Clé API introuvable")
            resolved_api_key = stored_key.key_value

        project.llm_provider = body.llm.provider
        project.llm_model = body.llm.model
        project.llm_thinking = body.llm.thinking
        project.llm_api_key = resolved_api_key
        project.llm_api_base = body.llm.api_base if body.llm.provider == "ollama" else None

    await session.flush()

    return ProjectDetail(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        status=_project_status(project_id),
        chapter_count=len(project.chapters),
        chapters_done=sum(1 for ch in project.chapters if ch.state == "validated"),
        source_text=project.source_text or "",
        llm_provider=project.llm_provider,
        llm_model=project.llm_model,
        llm_thinking=project.llm_thinking,
        target_chapter_count=project.target_chapter_count,
        writing_style=project.writing_style,
        tone_keywords=project.tone_keywords or [],
        min_validation_score=project.min_validation_score,
        max_revision_attempts=project.max_revision_attempts,
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: User = Depends(get_current_user),
):
    if background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Pipeline en cours, impossible de supprimer")

    project = await session.get(Project, project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    await session.delete(project)

    # Supprime les fichiers sur disque
    import shutil
    if os.path.exists(project.project_dir):
        shutil.rmtree(project.project_dir)
