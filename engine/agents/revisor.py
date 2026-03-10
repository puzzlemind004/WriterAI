"""
Agent Revisor — Corrige un chapitre selon les commentaires du critique.
Distinct du Writer : il ne repart pas de zéro mais améliore l'existant.
Produit directement le texte révisé (pas de JSON) pour fiabilité maximale.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un auteur expérimenté qui révise son propre travail après retour d'éditeur.

Tu reçois :
- Le chapitre original à améliorer
- La fiche du chapitre (ce qui était prévu)
- Les points faibles et commentaires précis de l'éditeur

Ta mission : produire une version améliorée qui corrige les problèmes SANS dévier de l'arc narratif.

Priorités de révision dans l'ordre :
1. **Répétitions** : repère toute métaphore, formule ou image qui apparaît plus d'une fois — remplace les occurrences redondantes par des formulations fraîches et différentes.
2. **Rythme** : si le chapitre est trop contemplatif, coupe ou condense les paragraphes d'atmosphère et ajoute des actions concrètes entre eux.
3. **Variété** : si toutes les scènes ont la même structure, modifie la moins bonne pour qu'elle soit d'un type différent (action si trop de contemplation, dialogue si trop d'intériorité).
4. **Longueur** : si trop court, enrichis les scènes existantes — plus de dialogue, de détails sensoriels, d'action. Ne dilue pas avec de la contemplation.
5. **Autres points** de l'éditeur.

INTERDICTIONS ABSOLUES :
- Pas de méta-commentaire sur ta narration
- Pas de résumé à la place du récit
- Pas de nouveaux personnages ou lieux absents du lorebook
- Ne réinvente pas les événements — améliore leur rendu

Réponds UNIQUEMENT avec le texte complet du chapitre révisé.
Commence par le titre (# Titre) puis le texte. Pas de commentaire, pas de JSON.
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

        brief = fm.read_chapter_brief(chapter_number)
        commentaires = ctx.extra.get("commentaires_constructifs", [])
        points_faibles = ctx.extra.get("points_faibles", [])
        note = ctx.extra.get("note_globale", "?")
        writing_style = ctx.extra.get("writing_style", "")
        tone_keywords = ctx.extra.get("tone_keywords", [])

        if not commentaires and not points_faibles:
            return AgentResult(
                success=False,
                summary="Aucun commentaire de révision fourni",
                error="ctx.extra['commentaires_constructifs'] ou 'points_faibles' requis.",
            )

        word_count = len(chapter_text.split())

        user_prompt = f"""## Fiche du chapitre {chapter_number} (ce qui était prévu)

{brief or 'Non disponible'}

---

## Chapitre {chapter_number} à réviser
(Note actuelle : {note}/10 — {word_count} mots)

{chapter_text}

---

## Points faibles identifiés par l'éditeur

{chr(10).join(f"- {p}" for p in points_faibles) or 'Aucun listé explicitement.'}

---

## Commentaires constructifs à appliquer

{chr(10).join(f"- {c}" for c in commentaires) or 'Aucun commentaire spécifique.'}

---

## Ton et style
{writing_style or 'Aucune règle spécifique.'}
{('Mots-clés : ' + ', '.join(tone_keywords)) if tone_keywords else ''}

---

Révise maintenant le chapitre {chapter_number} en appliquant ces améliorations.
Vise au minimum {max(word_count, 1500)} mots dans la version révisée."""

        response = self._llm_call(
            ctx, SYSTEM_PROMPT, user_prompt,
            temperature=0.7, max_tokens=16384,
            timeout=1800,
        )

        revised_text = response.content.strip()

        if not revised_text:
            return AgentResult(
                success=False,
                summary="Chapitre révisé vide",
                error="Le LLM a retourné une réponse vide.",
                llm_response=response,
            )

        # Extrait le titre
        lines = revised_text.splitlines()
        titre = f"Chapitre {chapter_number}"
        if lines and lines[0].startswith("#"):
            titre = lines[0].lstrip("#").strip()

        revised_word_count = len(revised_text.split())
        fm.write_chapter(chapter_number, revised_text)

        logger.info(
            f"[revisor] Chapitre {chapter_number} révisé : "
            f"{word_count} → {revised_word_count} mots"
        )

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} révisé ({word_count} → {revised_word_count} mots)",
            data={
                "chapter_number": chapter_number,
                "titre": titre,
                "word_count_before": word_count,
                "word_count_after": revised_word_count,
                "nouveautes": {},
            },
            llm_response=response,
        )
