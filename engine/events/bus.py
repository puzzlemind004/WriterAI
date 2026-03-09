"""
Bus d'événements simple basé sur des callbacks.
Les consommateurs (UI, logger, tests) s'abonnent à des types d'événements.
"""
import logging
import threading
from collections import defaultdict
from typing import Callable
from .types import Event, EventType

logger = logging.getLogger(__name__)

Handler = Callable[[Event], None]


class EventBus:
    def __init__(self):
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._global_handlers: list[Handler] = []
        self._lock = threading.Lock()

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        """Abonne un handler à un type d'événement spécifique."""
        with self._lock:
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Handler) -> None:
        """Abonne un handler à tous les événements (utile pour le logging)."""
        with self._lock:
            self._global_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        with self._lock:
            if handler in self._handlers[event_type]:
                self._handlers[event_type].remove(handler)

    def unsubscribe_all(self, handler: Handler) -> None:
        """Désabonne un handler global ajouté via subscribe_all."""
        with self._lock:
            if handler in self._global_handlers:
                self._global_handlers.remove(handler)

    def emit(self, event: Event) -> None:
        """Émet un événement vers tous les handlers abonnés."""
        logger.debug(f"Event [{event.type}] project={event.project_id} chapter={event.chapter_id}")

        # Snapshot thread-safe des handlers avant d'appeler (évite un deadlock
        # si un handler appelle subscribe/unsubscribe pendant l'émission)
        with self._lock:
            global_handlers = list(self._global_handlers)
            typed_handlers = list(self._handlers[event.type])

        for handler in global_handlers:
            self._safe_call(handler, event)

        for handler in typed_handlers:
            self._safe_call(handler, event)

    def _safe_call(self, handler: Handler, event: Event) -> None:
        try:
            handler(event)
        except Exception as e:
            logger.error(f"Erreur dans le handler {handler.__name__}: {e}")


# Instance globale du bus — importée par tous les agents
bus = EventBus()
