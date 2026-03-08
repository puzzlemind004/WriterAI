"""
Définition de tous les événements émis par le moteur.
L'UI s'abonne à ces événements pour le suivi en temps réel.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    # Cycle de vie des agents
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    # Chapitres
    CHAPTER_STATE_CHANGED = "chapter.state_changed"
    CHAPTER_CREATED = "chapter.created"

    # Lorebook
    LOREBOOK_UPDATED = "lorebook.updated"

    # Validation
    VALIDATION_RESULT = "validation.result"

    # Pipeline global
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_ERROR = "pipeline.error"


@dataclass
class Event:
    type: EventType
    project_id: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    chapter_id: Optional[str] = None


# --- Helpers pour construire les événements courants ---

def agent_started(project_id: str, agent_name: str, chapter_id: Optional[str] = None) -> Event:
    return Event(
        type=EventType.AGENT_STARTED,
        project_id=project_id,
        chapter_id=chapter_id,
        payload={"agent": agent_name},
    )


def agent_completed(
    project_id: str,
    agent_name: str,
    summary: str,
    chapter_id: Optional[str] = None,
) -> Event:
    return Event(
        type=EventType.AGENT_COMPLETED,
        project_id=project_id,
        chapter_id=chapter_id,
        payload={"agent": agent_name, "summary": summary},
    )


def agent_failed(
    project_id: str,
    agent_name: str,
    error: str,
    chapter_id: Optional[str] = None,
) -> Event:
    return Event(
        type=EventType.AGENT_FAILED,
        project_id=project_id,
        chapter_id=chapter_id,
        payload={"agent": agent_name, "error": error},
    )


def chapter_state_changed(
    project_id: str,
    chapter_id: str,
    old_state: str,
    new_state: str,
) -> Event:
    return Event(
        type=EventType.CHAPTER_STATE_CHANGED,
        project_id=project_id,
        chapter_id=chapter_id,
        payload={"old_state": old_state, "new_state": new_state},
    )


def lorebook_updated(
    project_id: str,
    entity_type: str,
    entity_name: str,
    changed_by: str,
) -> Event:
    return Event(
        type=EventType.LOREBOOK_UPDATED,
        project_id=project_id,
        payload={
            "entity_type": entity_type,
            "entity_name": entity_name,
            "changed_by": changed_by,
        },
    )


def validation_result(
    project_id: str,
    chapter_id: str,
    score: float,
    decision: str,
    comments: list[str],
) -> Event:
    return Event(
        type=EventType.VALIDATION_RESULT,
        project_id=project_id,
        chapter_id=chapter_id,
        payload={"score": score, "decision": decision, "comments": comments},
    )
