"""
Agent Analyzer — Phase 1 du pipeline.
Reçoit le(s) document(s) d'entrée fournis par l'utilisateur
et construit le lorebook initial complet.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un analyste littéraire expert. Tu reçois un ou plusieurs documents
décrivant une histoire (pitch, synopsis, notes, manuscrit partiel...).
Ton travail est d'en extraire toutes les informations structurées pour construire un lorebook complet.

Tu dois produire une réponse JSON strictement valide avec cette structure :
{
  "personnages": [
    {
      "nom": "Nom du personnage",
      "contenu": "Fiche markdown complète : description physique, personnalité, rôle, histoire, relations..."
    }
  ],
  "lieux": [
    {
      "nom": "Nom du lieu",
      "contenu": "Fiche markdown complète : description, atmosphère, importance narrative..."
    }
  ],
  "lore": [
    {
      "nom": "Nom de l'élément de lore",
      "contenu": "Fiche markdown : règles du monde, magie, technologie, histoire du monde..."
    }
  ],
  "chronologie": "Contenu markdown de la timeline des événements (du plus ancien au plus récent)",
  "themes": "Contenu markdown : ton, ambiance, thèmes principaux, style narratif souhaité",
  "story": "Contenu markdown : résumé de l'arc narratif global, début-milieu-fin, enjeux principaux"
}

Règles :
- Si une information n'est pas dans le document source, n'invente pas — laisse le champ vide ou minimal.
- Les fiches personnages et lieux doivent être en markdown avec des titres (##) pour chaque section.
- Sois exhaustif : mieux vaut trop d'informations que pas assez.
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class AnalyzerAgent(BaseAgent):
    name = "analyzer"

    def _run(self, ctx: AgentContext) -> AgentResult:
        source_text = ctx.extra.get("source_text", "")
        if not source_text.strip():
            return AgentResult(
                success=False,
                summary="Aucun document source fourni",
                error="Le champ 'source_text' est vide dans le contexte.",
            )

        user_prompt = f"""Voici le(s) document(s) source à analyser :

---
{source_text}
---

Construis le lorebook complet en JSON."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.3)

        try:
            lorebook = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        fm = FileManager(ctx.project_id)
        self._write_lorebook(fm, lorebook)

        counts = {
            "personnages": len(lorebook.get("personnages", [])),
            "lieux": len(lorebook.get("lieux", [])),
            "lore": len(lorebook.get("lore", [])),
        }

        return AgentResult(
            success=True,
            summary=(
                f"Lorebook créé : {counts['personnages']} personnage(s), "
                f"{counts['lieux']} lieu(x), {counts['lore']} élément(s) de lore"
            ),
            data=counts,
            llm_response=response,
        )

    def _write_lorebook(self, fm: FileManager, lorebook: dict) -> None:
        """Écrit toutes les entrées du lorebook dans les fichiers markdown."""
        for perso in lorebook.get("personnages", []):
            if perso.get("nom") and perso.get("contenu"):
                fm.write_character(perso["nom"], perso["contenu"])

        for lieu in lorebook.get("lieux", []):
            if lieu.get("nom") and lieu.get("contenu"):
                fm.write_place(lieu["nom"], lieu["contenu"])

        for lore_item in lorebook.get("lore", []):
            if lore_item.get("nom") and lore_item.get("contenu"):
                fm.write_lorebook_file(f"lore/{fm._slugify(lore_item['nom'])}.md", lore_item["contenu"])

        if lorebook.get("chronologie"):
            fm.write_lorebook_file("chronologie.md", lorebook["chronologie"])

        if lorebook.get("themes"):
            fm.write_lorebook_file("themes.md", lorebook["themes"])

        if lorebook.get("story"):
            fm.write_lorebook_file("story.md", lorebook["story"])
