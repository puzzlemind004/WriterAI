"""
Agent Writer — Rédige un chapitre complet.
Reçoit la fiche chapitre, le lorebook sélectif, l'état du monde
et les règles d'écriture. Produit le chapitre rédigé + les nouveautés inventées.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un auteur de romans talentueux. Tu reçois une fiche chapitre détaillée,
des informations sur le monde (lorebook), l'état du monde à la fin du chapitre précédent,
et des règles d'écriture à respecter.

Tu dois écrire le chapitre complet en respectant scrupuleusement :
- Le contenu décrit dans la fiche chapitre (ne pas dévier de l'arc narratif prévu)
- La cohérence avec le lorebook (personnages, lieux, règles du monde, époque, technologie)
- La continuité depuis le chapitre précédent
- Le ton et le style demandés
- Les règles d'écriture fournies

Règles d'écriture générales :
- Privilégie le "show don't tell" : montre les émotions par les actions et sensations, pas par les noms
- Les dialogues doivent révéler le caractère des personnages, pas exposer l'intrigue
- Alterne descriptions, actions et dialogues pour maintenir le rythme
- Chaque scène doit faire avancer l'histoire ou révéler un personnage
- Longueur minimale : 1500 mots. Visée : 2000-3000 mots.
- Varie le rythme des phrases : courtes pour l'action, longues pour l'atmosphère
- Évite les formules répétitives : ne réutilise pas la même métaphore ou comparaison deux fois

INTERDICTIONS ABSOLUES :
- Ne jamais écrire de méta-commentaire sur ta propre narration ("le chapitre se termine sur...", "la scène s'ouvre sur...", "le récit suit...")
- Ne jamais résumer ce qui vient de se passer au lieu de le montrer
- Ne jamais faire parler un personnage pour expliquer l'intrigue au lecteur (dialogue d'exposition)
- Respecter scrupuleusement la technologie et l'époque de l'univers (ex: monde médiéval-fantastique = pas d'armes à feu, pas de technologie moderne)
- Ne pas introduire de personnages ou lieux qui ne sont pas dans le lorebook ou la fiche

Réponds UNIQUEMENT avec le texte du chapitre, rien d'autre.
Commence directement par le titre du chapitre sur la première ligne (ex: # Titre),
puis le texte. Pas de commentaire, pas d'explication, pas de JSON.
"""


class WriterAgent(BaseAgent):
    name = "writer"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        if not chapter_number:
            return AgentResult(
                success=False,
                summary="Numéro de chapitre manquant",
                error="ctx.chapter_number est requis pour WriterAgent.",
            )

        fm = FileManager(ctx.project_id)
        brief = fm.read_chapter_brief(chapter_number)
        if not brief.strip():
            return AgentResult(
                success=False,
                summary=f"Fiche chapitre {chapter_number} introuvable",
                error=f"Lancer ChapterPlannerAgent avant WriterAgent.",
            )

        lorebook_context = self._build_selective_lorebook(fm, brief)
        world_state = ctx.extra.get("world_state")
        writing_style = ctx.extra.get("writing_style", "")
        tone_keywords = ctx.extra.get("tone_keywords", [])

        user_prompt = self._build_prompt(
            chapter_number, brief, lorebook_context,
            world_state, writing_style, tone_keywords
        )

        response = self._llm_call(
            ctx, SYSTEM_PROMPT, user_prompt,
            temperature=0.8, max_tokens=16384,
            timeout=1800,  # 30 minutes — filet de sécurité, ne devrait jamais se déclencher
        )

        chapter_text = response.content.strip()

        if not chapter_text:
            return AgentResult(
                success=False,
                summary="Chapitre vide généré",
                error="Le LLM a retourné une réponse vide.",
                llm_response=response,
            )

        # Extrait le titre de la première ligne si présent (# Titre)
        lines = chapter_text.splitlines()
        titre = f"Chapitre {chapter_number}"
        if lines and lines[0].startswith("#"):
            titre = lines[0].lstrip("#").strip()

        fm.write_chapter(chapter_number, chapter_text)

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} rédigé ({len(chapter_text)} caractères)",
            data={
                "chapter_number": chapter_number,
                "titre": titre,
                "char_count": len(chapter_text),
                "nouveautes": {},  # Délégué au LoreExtractor
            },
            llm_response=response,
        )

    def _build_selective_lorebook(self, fm: FileManager, brief: str) -> str:
        """
        Construit un lorebook sélectif : uniquement les personnages et lieux
        mentionnés dans la fiche chapitre.
        """
        parts = []
        brief_lower = brief.lower()

        characters = fm.read_all_characters()
        relevant_chars = {
            name: content for name, content in characters.items()
            if name.lower() in brief_lower
        }
        # Si aucun personnage détecté, on les inclut tous (sécurité)
        if not relevant_chars:
            relevant_chars = characters

        if relevant_chars:
            parts.append("### Personnages\n" + "\n\n".join(
                f"**{name}**\n{content}" for name, content in relevant_chars.items()
            ))

        places = fm.read_all_places()
        relevant_places = {
            name: content for name, content in places.items()
            if name.lower() in brief_lower
        }
        if not relevant_places and places:
            # Inclut tous les lieux si aucun détecté dans le brief
            relevant_places = places

        if relevant_places:
            parts.append("### Lieux\n" + "\n\n".join(
                f"**{name}**\n{content}" for name, content in relevant_places.items()
            ))

        themes = fm.read_lorebook_file("themes.md")
        if themes:
            parts.append(f"### Ton et thèmes\n{themes}")

        return "\n\n".join(parts)

    def _build_prompt(
        self,
        chapter_number: int,
        brief: str,
        lorebook_context: str,
        world_state: dict | None,
        writing_style: str,
        tone_keywords: list[str],
    ) -> str:
        world_state_text = ""
        if world_state:
            world_state_text = f"""
## État du monde au début de ce chapitre
(Fin du chapitre précédent)

**Positions des personnages :**
{chr(10).join(f"- {name}: {state}" for name, state in world_state.get('position_personnages', {}).items())}

**Derniers événements :**
{chr(10).join(f"- {e}" for e in world_state.get('derniers_evenements', []))}

**Tensions en cours :**
{chr(10).join(f"- {t}" for t in world_state.get('tensions_en_cours', []))}

**Ambiance :** {world_state.get('ambiance_fin_chapitre', '')}
"""

        return f"""## Fiche du chapitre {chapter_number} à rédiger

{brief}

---

## Lorebook (contexte du monde)

{lorebook_context}

---
{world_state_text}
## Règles d'écriture spécifiques
{writing_style or 'Aucune règle spécifique — applique les règles générales.'}

## Ton demandé
{', '.join(tone_keywords) if tone_keywords else 'Non spécifié — reste cohérent avec les thèmes.'}

---

Rédige maintenant le chapitre {chapter_number} complet."""
