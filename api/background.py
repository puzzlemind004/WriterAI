"""
Gestion des pipelines en arrière-plan.
Un seul pipeline par projet à la fois, stocké en mémoire.
Les events sont broadcastés via l'EventBus existant.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

logger = logging.getLogger(__name__)

# Lock global pour protéger _pipelines contre les accès concurrents
_lock = threading.Lock()

# État en mémoire des pipelines actifs : { project_id: dict }
_pipelines: dict[str, dict] = {}

# Thread pool pour exécuter le pipeline synchrone sans bloquer la boucle async
_executor = ThreadPoolExecutor(max_workers=4)


def get_pipeline_state(project_id: str) -> dict:
    with _lock:
        return dict(_pipelines.get(project_id, {
            "status": "idle",
            "current_agent": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
            "chapters": [],
        }))


def is_running(project_id: str) -> bool:
    with _lock:
        return _pipelines.get(project_id, {}).get("status") == "running"


def _update_state(project_id: str, **kwargs) -> None:
    """Met à jour l'état d'un pipeline de façon thread-safe."""
    with _lock:
        if project_id in _pipelines:
            _pipelines[project_id].update(kwargs)


async def run_pipeline_async(project_id: str, config) -> None:
    """
    Lance le pipeline dans un thread séparé pour ne pas bloquer FastAPI.
    Le pipeline est synchrone — on l'exécute via ThreadPoolExecutor.
    """
    from engine.pipeline.orchestrator import Orchestrator
    from engine.events.bus import bus
    from engine.events.types import EventType, Event

    with _lock:
        _pipelines[project_id] = {
            "status": "running",
            "current_agent": None,
            "error": None,
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "chapters": [],
        }

    def on_event(event: Event) -> None:
        if event.project_id != project_id:
            return
        if event.type == EventType.AGENT_STARTED:
            _update_state(project_id, current_agent=event.payload.get("agent"))
        elif event.type == EventType.AGENT_COMPLETED:
            _update_state(project_id, current_agent=None)
        elif event.type == EventType.PIPELINE_COMPLETED:
            _update_state(project_id, status="completed", current_agent=None, completed_at=datetime.utcnow())
        elif event.type == EventType.PIPELINE_ERROR:
            _update_state(project_id, status="error", error=event.payload.get("error"), completed_at=datetime.utcnow())

    bus.subscribe_all(on_event)
    loop = asyncio.get_event_loop()

    try:
        def _run() -> dict:
            # Injecte la loop asyncio pour que l'orchestrateur puisse persister en DB
            config.event_loop = loop
            orchestrator = Orchestrator(config)
            return orchestrator.run()

        report = await loop.run_in_executor(_executor, _run)
        _update_state(project_id, chapters=report.get("chapters", []))

    except Exception as e:
        logger.error(f"[background] Pipeline {project_id} échoué : {e}")
        _update_state(
            project_id,
            status="error",
            error=str(e),
            completed_at=datetime.utcnow(),
        )
    finally:
        bus.unsubscribe_all(on_event)
