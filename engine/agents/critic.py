"""
Agent Critic — Évalue un chapitre rédigé et produit une note + des commentaires.
La grille d'évaluation est configurable par projet.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

# Grille d'évaluation par défaut — surchargeable via ctx.extra["critic_grid"]
DEFAULT_CRITIC_GRID = """
1. **Cohérence avec le lorebook** (0-10) : Personnages, lieux et règles du monde respectés ?
   Pénalise (-2 par occurrence) : anachronismes, personnages absents du lorebook.

2. **Respect de la fiche chapitre** (0-10) : Le contenu prévu a-t-il été couvert ?
   Pénalise : événements manquants, déviation de l'arc prévu.

3. **Qualité narrative** (0-10) : Style, rythme, densité événementielle.
   Pénalise sévèrement :
   - Répétitions de métaphores ou formules dans le même chapitre (-2 par doublon détecté)
   - Plus de 3 paragraphes contemplatifs d'affilée sans événement concret (-2)
   - Méta-commentaires sur la narration (-2 chacun)
   - Dialogues d'exposition (-1 chacun)
   - Moins de 1500 mots (-3)

4. **Variété de rythme** (0-10) : Le chapitre alterne-t-il action, dialogue et introspection ?
   Pénalise : chapitre entièrement contemplatif (-4), absence de dialogue (-2), absence d'action physique (-2).

5. **Engagement** (0-10) : Le chapitre donne-t-il envie de lire la suite ?
   La tension monte-t-elle ? Y a-t-il un événement marquant ?
"""

SYSTEM_PROMPT = """Tu es un éditeur littéraire expérimenté et exigeant. Tu évalues un chapitre
de roman selon une grille de critères précise.

Tu dois produire une réponse JSON strictement valide avec cette structure :
{
  "note_globale": 7.5,
  "notes_detaillees": {
    "coherence_lorebook": 8.0,
    "respect_fiche": 7.0,
    "qualite_narrative": 8.0,
    "variete_rythme": 6.0,
    "engagement": 7.0
  },
  "points_forts": [
    "Ce qui fonctionne bien dans ce chapitre"
  ],
  "points_faibles": [
    "Ce qui ne fonctionne pas ou pourrait être amélioré"
  ],
  "commentaires_constructifs": [
    "Suggestion précise et actionnable pour améliorer le chapitre"
  ],
  "verdict": "Un paragraphe de synthèse expliquant la note globale"
}

Règles :
- Sois honnête et précis. Une note de 10 est exceptionnelle, 7 est bon, 5 est passable.
- Les commentaires constructifs doivent être ACTIONNABLES (dire comment corriger, pas juste quoi).
- Note globale = moyenne pondérée des notes détaillées.
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class CriticAgent(BaseAgent):
    name = "critic"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        if not chapter_number:
            return AgentResult(
                success=False,
                summary="Numéro de chapitre manquant",
                error="ctx.chapter_number est requis pour CriticAgent.",
            )

        fm = FileManager(ctx.project_id)
        chapter_text = fm.read_chapter(chapter_number)
        if not chapter_text.strip():
            return AgentResult(
                success=False,
                summary=f"Chapitre {chapter_number} introuvable",
                error="Lancer WriterAgent avant CriticAgent.",
            )

        brief = fm.read_chapter_brief(chapter_number)
        critic_grid = ctx.extra.get("critic_grid", DEFAULT_CRITIC_GRID)

        # Lorebook sélectif pour la vérification de cohérence
        characters = fm.read_all_characters()
        chapter_lower = chapter_text.lower()
        relevant_chars = {
            name: content for name, content in characters.items()
            if name.lower() in chapter_lower
        }

        lorebook_context = ""
        if relevant_chars:
            lorebook_context = "### Personnages concernés\n" + "\n\n".join(
                f"**{name}**\n{content}" for name, content in relevant_chars.items()
            )

        user_prompt = f"""## Chapitre {chapter_number} à évaluer

{chapter_text}

---

## Fiche chapitre (ce qui était prévu)

{brief or 'Non disponible'}

---

## Lorebook (référence de cohérence)

{lorebook_context or 'Non disponible'}

---

## Grille d'évaluation à appliquer

{critic_grid}

---

Évalue ce chapitre selon la grille ci-dessus."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.2)

        try:
            evaluation = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        note = evaluation.get("note_globale", 0.0)

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} noté {note}/10",
            data={
                "chapter_number": chapter_number,
                "note_globale": note,
                "notes_detaillees": evaluation.get("notes_detaillees", {}),
                "points_forts": evaluation.get("points_forts", []),
                "points_faibles": evaluation.get("points_faibles", []),
                "commentaires_constructifs": evaluation.get("commentaires_constructifs", []),
                "verdict": evaluation.get("verdict", ""),
            },
            llm_response=response,
        )
