"""
Routes pour lancer, suivre et arrêter le pipeline.
SSE pour le streaming des events en temps réel.
"""
import asyncio
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import db_session
from api.schemas import PipelineStatus
from api import background
from engine.storage.models import Project
from engine.events.bus import bus
from engine.events.types import Event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["pipeline"])


def _build_orchestrator_config(project: Project, source_text: str):
    from engine.pipeline.orchestrator import OrchestratorConfig
    from engine.llm.client import make_ollama_client, make_client

    # Reconstruit le LLMClient depuis les données du projet
    if project.llm_provider == "ollama":
        llm = make_ollama_client(
            model=project.llm_model,
            api_base=project.llm_api_base or "http://localhost:11434",
            thinking=project.llm_thinking,
        )
    else:
        llm = make_client(
            provider=project.llm_provider,
            model=project.llm_model,
            api_key=project.llm_api_key,
            api_base=project.llm_api_base,
        )

    return OrchestratorConfig(
        project_id=project.id,
        llm=llm,
        source_text=source_text,
        target_chapter_count=project.target_chapter_count,
        tone_keywords=project.tone_keywords or [],
        writing_style=project.writing_style or "",
        min_validation_score=project.min_validation_score,
        max_revision_attempts=project.max_revision_attempts,
    )


@router.post("/{project_id}/run", response_model=PipelineStatus)
async def run_pipeline(
    project_id: str,
    session: AsyncSession = Depends(db_session),
):
    if background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Pipeline déjà en cours")

    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    source_text = getattr(project, "source_text", "")
    if not source_text:
        raise HTTPException(status_code=400, detail="Le projet n'a pas de texte source")

    config = _build_orchestrator_config(project, source_text)

    # Lance en arrière-plan sans attendre
    asyncio.create_task(background.run_pipeline_async(project_id, config))

    return PipelineStatus(
        project_id=project_id,
        status="running",
        started_at=datetime.utcnow(),
    )


@router.post("/{project_id}/stop", response_model=PipelineStatus)
async def stop_pipeline(project_id: str):
    """
    Arrêt gracieux — marque le pipeline comme annulé.
    Le pipeline finit l'agent en cours puis s'arrête.
    """
    if not background.is_running(project_id):
        raise HTTPException(status_code=409, detail="Aucun pipeline en cours")

    state = background.get_pipeline_state(project_id)
    state["status"] = "stopping"

    return PipelineStatus(
        project_id=project_id,
        status="stopping",
    )


@router.get("/{project_id}/status", response_model=PipelineStatus)
async def get_status(project_id: str):
    state = background.get_pipeline_state(project_id)
    return PipelineStatus(
        project_id=project_id,
        status=state["status"],
        current_agent=state.get("current_agent"),
        chapters=state.get("chapters", []),
        error=state.get("error"),
        started_at=state.get("started_at"),
        completed_at=state.get("completed_at"),
    )


@router.get("/{project_id}/stream")
async def stream_events(project_id: str):
    """
    Server-Sent Events — pousse les events du pipeline en temps réel.
    Le client s'abonne et reçoit chaque event au format SSE.
    """
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def on_event(event: Event):
            if event.project_id == project_id:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": event.type.value,
                        "payload": event.payload,
                    }
                )

        bus.subscribe_all(on_event)

        try:
            # Envoie l'état actuel immédiatement à la connexion
            state = background.get_pipeline_state(project_id)
            yield f"data: {json.dumps({'type': 'connected', 'status': state['status']})}\n\n"

            while True:
                try:
                    # Attend le prochain event avec timeout (keepalive)
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event_data)}\n\n"

                    # Arrête le stream si le pipeline est terminé
                    if event_data["type"] in ("pipeline_completed", "pipeline_error"):
                        break

                except asyncio.TimeoutError:
                    # Keepalive pour maintenir la connexion
                    yield ": keepalive\n\n"

        finally:
            bus.unsubscribe_all(on_event)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
