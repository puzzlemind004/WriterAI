"""
Agent Revisor — Corrige un chapitre selon les commentaires du critique.
Distinct du Writer : il ne repart pas de zéro mais améliore l'existant.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un auteur expérimenté qui révise son propre travail.
Tu reçois un chapitre existant et des commentaires précis d'un éditeur.
Tu dois améliorer le chapitre en tenant compte de ces commentaires
sans perdre ce qui fonctionnait bien.

Règles :
- Traite chaque commentaire constructif.
- Conserve le fil narratif et les événements clés — ne réinvente pas l'histoire.
- Améliore le style, le rythme, la cohérence là où c'est pointé.
- Si tu introduis de nouveaux éléments (personnages, lieux), liste-les.

Réponds en JSON strictement valide avec cette structure :
{
  "chapitre": "Le texte complet du chapitre révisé en markdown",
  "modifications": [
    "Description de la modification 1 apportée",
    "Description de la modification 2"
  ],
  "nouveautes": {
    "personnages": [{"nom": "Nom", "description": "Description courte"}],
    "lieux": [{"nom": "Nom", "description": "Description courte"}],
    "lore": [{"nom": "Nom", "description": "Description courte"}]
  }
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class RevisorAgent(BaseAgent):
    name = "revisor"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        if not chapter_number:
            return AgentResult(
                success=False,
                summary="Numéro de chapitre manquant",
                error="ctx.chapter_number est requis pour RevisorAgent.",
            )

        fm = FileManager(ctx.project_id)
        chapter_text = fm.read_chapter(chapter_number)
        if not chapter_text.strip():
            return AgentResult(
                success=False,
                summary=f"Chapitre {chapter_number} introuvable",
                error="Aucun chapitre à réviser.",
            )

        commentaires = ctx.extra.get("commentaires_constructifs", [])
        points_faibles = ctx.extra.get("points_faibles", [])
        note = ctx.extra.get("note_globale", "?")
        writing_style = ctx.extra.get("writing_style", "")

        if not commentaires and not points_faibles:
            return AgentResult(
                success=False,
                summary="Aucun commentaire de révision fourni",
                error="ctx.extra['commentaires_constructifs'] ou 'points_faibles' requis.",
            )

        user_prompt = f"""## Chapitre {chapter_number} à réviser
(Note actuelle : {note}/10)

{chapter_text}

---

## Points faibles identifiés par l'éditeur

{chr(10).join(f"- {p}" for p in points_faibles) or 'Aucun listé explicitement.'}

---

## Commentaires constructifs à appliquer

{chr(10).join(f"- {c}" for c in commentaires) or 'Aucun commentaire spécifique.'}

---

## Règles d'écriture à respecter
{writing_style or 'Aucune règle spécifique.'}

---

Révise le chapitre en appliquant ces améliorations."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.7, max_tokens=8192)

        try:
            result = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        revised_text = result.get("chapitre", "")
        if not revised_text.strip():
            return AgentResult(
                success=False,
                summary="Chapitre révisé vide",
                error="Le LLM a retourné un chapitre vide.",
                llm_response=response,
            )

        fm.write_chapter(chapter_number, revised_text)

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} révisé ({len(result.get('modifications', []))} modification(s))",
            data={
                "chapter_number": chapter_number,
                "modifications": result.get("modifications", []),
                "nouveautes": result.get("nouveautes", {}),
                "char_count": len(revised_text),
            },
            llm_response=response,
        )
