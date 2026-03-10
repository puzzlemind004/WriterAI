"""
Agent ContinuityReader — Exécuté avant chaque rédaction de chapitre.
Lit le chapitre précédent (validé) et en extrait l'état du monde courant
pour garantir la continuité narrative.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant de continuité narrative. Tu lis le dernier chapitre
d'un roman et tu extrais un état du monde précis à la fin de ce chapitre.

Cet état sera injecté dans le contexte du rédacteur du chapitre suivant
pour garantir la cohérence narrative.

Réponds en JSON strictement valide avec cette structure :
{
  "position_personnages": {
    "NomPersonnage": "Où est ce personnage et dans quel état physique/émotionnel"
  },
  "derniers_evenements": [
    "Événement important 1 qui vient de se passer",
    "Événement important 2"
  ],
  "tensions_en_cours": [
    "Tension ou conflit non résolu 1",
    "Tension non résolue 2"
  ],
  "informations_recentes": [
    "Information importante révélée dans ce chapitre"
  ],
  "ambiance_fin_chapitre": "Description de l'ambiance et du ton à la fin du chapitre"
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class ContinuityReaderAgent(BaseAgent):
    name = "continuity_reader"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        if not chapter_number or chapter_number <= 1:
            # Pas de chapitre précédent pour le premier chapitre
            return AgentResult(
                success=True,
                summary="Premier chapitre, pas de continuité à lire",
                data={"world_state": None},
            )

        fm = FileManager(ctx.project_id)
        previous_chapter = fm.read_chapter(chapter_number - 1)

        if not previous_chapter.strip():
            return AgentResult(
                success=True,
                summary=f"Chapitre {chapter_number - 1} non trouvé, continuité ignorée",
                data={"world_state": None},
            )

        # Limite à 3000 mots max pour éviter de surcharger le contexte sur les longs chapitres
        words = previous_chapter.split()
        if len(words) > 3000:
            truncated = ' '.join(words[:500]) + '\n\n[...]\n\n' + ' '.join(words[-2500:])
            chapter_excerpt = f"[Chapitre tronqué — début et fin]\n\n{truncated}"
        else:
            chapter_excerpt = previous_chapter

        user_prompt = f"""Voici le chapitre {chapter_number - 1} :

{chapter_excerpt}

---
Extrais l'état du monde à la fin de ce chapitre."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.1)

        try:
            world_state = self._parse_json(response.content)
        except ValueError as e:
            # Non bloquant : on continue sans état de continuité plutôt que de bloquer le pipeline
            logger.warning(f"[{self.name}] impossible de parser l'état du monde : {e}")
            return AgentResult(
                success=True,
                summary="État du monde non parseable, continuité ignorée",
                data={"world_state": None},
                llm_response=response,
            )

        return AgentResult(
            success=True,
            summary=f"État du monde extrait depuis le chapitre {chapter_number - 1}",
            data={"world_state": world_state},
            llm_response=response,
        )
