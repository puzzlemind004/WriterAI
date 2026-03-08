"""
Classe de base pour tous les agents du moteur.
Chaque agent hérite de BaseAgent et implémente run().
"""
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from engine.llm.client import LLMClient, LLMResponse
from engine.events.bus import bus
from engine.events import types as ev

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    """
    Tout ce qu'un agent reçoit pour travailler.
    Chaque agent ne lit que ce dont il a besoin.
    """
    project_id: str
    llm: LLMClient
    chapter_id: Optional[str] = None
    chapter_number: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Ce qu'un agent retourne une fois son travail terminé."""
    success: bool
    summary: str                          # Phrase courte décrivant ce qui a été fait
    data: dict[str, Any] = field(default_factory=dict)  # Résultats structurés
    error: Optional[str] = None
    llm_response: Optional[LLMResponse] = None


class BaseAgent(ABC):
    """
    Classe abstraite dont héritent tous les agents.

    Responsabilités communes gérées ici :
    - Émission des événements started / completed / failed
    - Logging structuré
    - Wrapping des erreurs

    L'agent fils implémente uniquement _run() avec sa logique métier.
    """

    name: str = "base_agent"  # Surchargé par chaque agent fils

    def run(self, ctx: AgentContext) -> AgentResult:
        """
        Point d'entrée public. Ne pas surcharger dans les agents fils.
        Gère les événements et le logging autour de _run().
        """
        logger.info(f"[{self.name}] démarrage — project={ctx.project_id} chapter={ctx.chapter_id}")
        bus.emit(ev.agent_started(ctx.project_id, self.name, ctx.chapter_id))

        try:
            result = self._run(ctx)
        except Exception as e:
            error_msg = f"[{type(e).__name__}] {e}"
            logger.error(f"[{self.name}] échec — {error_msg}")
            bus.emit(ev.agent_failed(ctx.project_id, self.name, error_msg, ctx.chapter_id))
            return AgentResult(success=False, summary="Échec inattendu", error=error_msg)

        if result.success:
            logger.info(f"[{self.name}] terminé — {result.summary}")
            bus.emit(ev.agent_completed(ctx.project_id, self.name, result.summary, ctx.chapter_id))
        else:
            logger.warning(f"[{self.name}] terminé en échec — {result.error}")
            bus.emit(ev.agent_failed(ctx.project_id, self.name, result.error or "", ctx.chapter_id))

        return result

    @abstractmethod
    def _run(self, ctx: AgentContext) -> AgentResult:
        """Logique métier de l'agent. À implémenter dans chaque sous-classe."""
        ...

    @staticmethod
    def _parse_json(content: str) -> dict:
        """
        Parse JSON depuis une réponse LLM.
        Gère les blocs ```json ... ``` et les variantes mal formées.
        Lève ValueError si le JSON est invalide.
        """
        text = content.strip()

        # Retire les blocs de code markdown (``` ou ```json ou ```JSON etc.)
        if text.startswith("```"):
            lines = text.splitlines()
            # Retire la première ligne (```json) et la dernière si c'est ```
            start = 1
            end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
            text = "\n".join(lines[start:end]).strip()

        # Tentative de parse directe
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Tentative de récupération : cherche le premier { ou [ et le dernier } ou ]
        for start_char, end_char in [('{', '}'), ('[', ']')]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass

        raise ValueError(
            f"Impossible de parser le JSON depuis la réponse LLM.\n"
            f"Contenu reçu (200 premiers caractères) : {content[:200]!r}"
        )

    def _llm_call(
        self,
        ctx: AgentContext,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        Raccourci pour appeler le LLM depuis un agent.
        Logue automatiquement la consommation.
        """
        response = ctx.llm.call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.debug(
            f"[{self.name}] LLM — "
            f"in={response.input_tokens} out={response.output_tokens} "
            f"t={response.duration_seconds}s"
        )
        return response
