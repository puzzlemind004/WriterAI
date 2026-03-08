"""
Agent LoreExtractor — S'exécute après le Writer, avant le LorebookKeeper.
Responsabilité unique : lire le chapitre rédigé et en extraire tous les
changements à apporter au lorebook (nouveautés + évolutions).

Il ne juge pas, ne valide pas, n'écrit rien — il détecte et structure.
C'est le LorebookKeeper qui décidera quoi faire de ces informations.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un analyste littéraire spécialisé dans la continuité narrative.
Tu lis un chapitre de roman et tu identifies deux catégories de changements à apporter au lorebook :

**Catégorie 1 — Nouveautés** : éléments qui n'existaient pas avant ce chapitre
(nouveau personnage, nouveau lieu, nouvelle règle du monde, nouvel objet important...).

**Catégorie 2 — Évolutions** : changements significatifs sur des éléments déjà connus
(changement d'allégeance, mort, blessure importante, révélation sur le passé,
nouvelle relation, changement de statut, transformation physique ou psychologique,
destruction d'un lieu, changement politique...).

Ne retiens PAS : actions ordinaires, déplacements temporaires, dialogues sans conséquence durable,
émotions passagères, descriptions stylistiques.

Réponds en JSON strictement valide :
{
  "nouveautes": {
    "personnages": [
      {"nom": "Nom", "description": "Description complète pour créer la fiche"}
    ],
    "lieux": [
      {"nom": "Nom", "description": "Description complète pour créer la fiche"}
    ],
    "lore": [
      {"nom": "Nom de l'élément", "description": "Description complète"}
    ]
  },
  "evolutions": [
    {
      "type": "personnage" | "lieu" | "lore",
      "nom": "Nom exact tel qu'il apparaît dans la liste des éléments connus",
      "evolution": "Description précise et concise du changement (une phrase)",
      "impact_potentiel": "faible" | "modéré" | "majeur"
    }
  ]
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class LoreExtractorAgent(BaseAgent):
    name = "lore_extractor"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        if not chapter_number:
            return AgentResult(
                success=False,
                summary="Numéro de chapitre manquant",
                error="ctx.chapter_number est requis pour LoreExtractorAgent.",
            )

        fm = FileManager(ctx.project_id)
        chapter_text = fm.read_chapter(chapter_number)

        if not chapter_text.strip():
            return AgentResult(
                success=False,
                summary=f"Chapitre {chapter_number} introuvable",
                error="Lancer WriterAgent avant LoreExtractorAgent.",
            )

        # Fournit la liste des éléments connus pour aider le LLM
        # à distinguer nouveautés vs évolutions
        known_characters = fm.list_lorebook_entities("personnages")
        known_places = fm.list_lorebook_entities("lieux")
        known_lore = fm.list_lorebook_entities("lore")

        known_context = self._build_known_context(known_characters, known_places, known_lore)

        # Récupère aussi les nouveautés signalées par le Writer
        # (filet de sécurité : le Writer peut avoir raté des éléments)
        writer_nouveautes = ctx.extra.get("nouveautes", {})

        user_prompt = f"""Éléments déjà connus dans le lorebook :
{known_context}

---

Chapitre {chapter_number} à analyser :

{chapter_text}

---

Nouveautés déjà signalées par le rédacteur (à compléter/corriger si nécessaire) :
{json.dumps(writer_nouveautes, ensure_ascii=False, indent=2)}

Extrais tous les changements à apporter au lorebook."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.1)

        try:
            extracted = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        nb_nouveautes = (
            len(extracted.get("nouveautes", {}).get("personnages", []))
            + len(extracted.get("nouveautes", {}).get("lieux", []))
            + len(extracted.get("nouveautes", {}).get("lore", []))
        )
        nb_evolutions = len(extracted.get("evolutions", []))

        return AgentResult(
            success=True,
            summary=f"{nb_nouveautes} nouveauté(s) et {nb_evolutions} évolution(s) détectée(s)",
            data={
                "nouveautes": extracted.get("nouveautes", {}),
                "evolutions": extracted.get("evolutions", []),
                "chapter_number": chapter_number,
            },
            llm_response=response,
        )

    def _build_known_context(
        self,
        characters: list[str],
        places: list[str],
        lore: list[str],
    ) -> str:
        parts = []
        if characters:
            parts.append(f"Personnages : {', '.join(characters)}")
        if places:
            parts.append(f"Lieux : {', '.join(places)}")
        if lore:
            parts.append(f"Éléments de lore : {', '.join(lore)}")
        return "\n".join(parts) if parts else "Aucun élément encore enregistré."
