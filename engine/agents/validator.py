"""
Agent Validator — Décide si un chapitre est validé ou doit être révisé.
Prend en compte la note du critique, le nombre de révisions déjà faites,
et le seuil de validation configuré.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.events.bus import bus
from engine.events.types import Event, EventType

logger = logging.getLogger(__name__)


class ValidatorAgent(BaseAgent):
    name = "validator"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        note = ctx.extra.get("note_globale")
        commentaires = ctx.extra.get("commentaires_constructifs", [])
        revision_count = ctx.extra.get("revision_count", 0)
        min_score = ctx.extra.get("min_validation_score", 7.0)
        max_revisions = ctx.extra.get("max_revision_attempts", 5)

        if note is None:
            return AgentResult(
                success=False,
                summary="Note manquante",
                error="ctx.extra['note_globale'] est requis. Lancer CriticAgent avant ValidatorAgent.",
            )

        if not isinstance(note, (int, float)) or not (0.0 <= note <= 10.0):
            return AgentResult(
                success=False,
                summary="Note invalide",
                error=f"note_globale doit être un nombre entre 0 et 10, reçu : {note!r}",
            )

        if chapter_number is not None and (not isinstance(chapter_number, int) or chapter_number < 1):
            return AgentResult(
                success=False,
                summary="Numéro de chapitre invalide",
                error=f"chapter_number doit être un entier >= 1, reçu : {chapter_number!r}",
            )

        # Cas 1 : note suffisante → validation
        if note >= min_score:
            return AgentResult(
                success=True,
                summary=f"Chapitre {chapter_number} validé (note {note}/10 >= seuil {min_score})",
                data={
                    "decision": "VALIDATED",
                    "note": note,
                    "revision_count": revision_count,
                },
            )

        # Cas 2 : trop de révisions → on valide quand même pour ne pas boucler indéfiniment
        if revision_count >= max_revisions:
            logger.warning(
                f"[{self.name}] Chapitre {chapter_number} : "
                f"seuil non atteint ({note}/10) mais {revision_count} révisions déjà faites. "
                f"Validation forcée."
            )
            # Notifie explicitement l'UI que la validation est forcée
            bus.emit(Event(
                type=EventType.VALIDATION_RESULT,
                project_id=ctx.project_id,
                chapter_id=ctx.chapter_id,
                payload={
                    "score": note,
                    "decision": "VALIDATED_FORCED",
                    "comments": commentaires,
                    "warning": (
                        f"Validation forcée après {revision_count} révisions. "
                        f"Note finale : {note}/10 (seuil : {min_score}/10). "
                        f"Vérification manuelle recommandée."
                    ),
                },
            ))
            return AgentResult(
                success=True,
                summary=(
                    f"Chapitre {chapter_number} validé de force après {revision_count} révisions "
                    f"(note finale {note}/10)"
                ),
                data={
                    "decision": "VALIDATED_FORCED",
                    "note": note,
                    "revision_count": revision_count,
                    "reason": "Nombre maximum de révisions atteint",
                },
            )

        # Cas 3 : révision demandée
        return AgentResult(
            success=True,
            summary=(
                f"Chapitre {chapter_number} à réviser "
                f"(note {note}/10 < seuil {min_score}, révision {revision_count + 1}/{max_revisions})"
            ),
            data={
                "decision": "REVISION_REQUESTED",
                "note": note,
                "revision_count": revision_count,
                "commentaires": commentaires,
            },
        )
