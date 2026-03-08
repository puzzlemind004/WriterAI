"""
Agent ActPlanner — Phase 2 du pipeline.
Lit le lorebook et découpe l'histoire en grands actes narratifs.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un scénariste expert en structure narrative. Tu reçois un lorebook complet
décrivant une histoire et tu dois la découper en grands actes narratifs.

Un acte est une grande phase de l'histoire avec une unité dramatique propre
(ex: Acte 1 - La mise en place, Acte 2 - La confrontation, Acte 3 - La résolution).

Tu dois produire une réponse JSON strictement valide avec cette structure :
{
  "actes": [
    {
      "numero": 1,
      "titre": "Titre de l'acte",
      "resume": "Résumé de ce qui se passe dans cet acte (2-3 paragraphes)",
      "enjeux": "Les enjeux dramatiques de cet acte",
      "personnages_cles": ["Personnage1", "Personnage2"],
      "lieux_cles": ["Lieu1", "Lieu2"],
      "evenements_majeurs": ["Événement 1", "Événement 2", "Événement 3"],
      "chapitre_debut": 1,
      "chapitre_fin": 4
    }
  ],
  "total_chapitres_suggere": 12
}

Règles :
- Respecte les conventions narratives (3 actes minimum, 5 maximum pour un roman standard).
- Les chapitres estimés doivent être cohérents avec le nombre cible fourni.
- Chaque acte doit avoir une tension dramatique claire et une évolution.
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class ActPlannerAgent(BaseAgent):
    name = "act_planner"

    def _run(self, ctx: AgentContext) -> AgentResult:
        target_chapters = ctx.extra.get("target_chapter_count", 10)
        tone_keywords = ctx.extra.get("tone_keywords", [])
        writing_style = ctx.extra.get("writing_style", "")

        fm = FileManager(ctx.project_id)
        lorebook_summary = self._build_lorebook_summary(fm)

        if not lorebook_summary.strip():
            return AgentResult(
                success=False,
                summary="Lorebook vide, impossible de planifier les actes",
                error="Aucun contenu trouvé dans le lorebook. Lancer l'Analyzer d'abord.",
            )

        user_prompt = f"""Voici le lorebook de l'histoire :

{lorebook_summary}

---
Nombre de chapitres cible : {target_chapters}
Ton et ambiance : {', '.join(tone_keywords) if tone_keywords else 'Non spécifié'}
Style d'écriture : {writing_style or 'Non spécifié'}

Découpe cette histoire en grands actes narratifs."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.4)

        try:
            plan = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        actes = plan.get("actes", [])
        self._write_acts(fm, actes)

        return AgentResult(
            success=True,
            summary=f"{len(actes)} acte(s) planifié(s) ({plan.get('total_chapitres_suggere', '?')} chapitres suggérés)",
            data={
                "nb_actes": len(actes),
                "total_chapitres_suggere": plan.get("total_chapitres_suggere"),
                "actes": actes,
            },
            llm_response=response,
        )

    def _build_lorebook_summary(self, fm: FileManager) -> str:
        """Assemble un résumé du lorebook pour le contexte de l'agent."""
        parts = []

        story = fm.read_lorebook_file("story.md")
        if story:
            parts.append(f"## Histoire\n{story}")

        themes = fm.read_lorebook_file("themes.md")
        if themes:
            parts.append(f"## Thèmes et ton\n{themes}")

        chronologie = fm.read_lorebook_file("chronologie.md")
        if chronologie:
            parts.append(f"## Chronologie\n{chronologie}")

        characters = fm.read_all_characters()
        if characters:
            parts.append("## Personnages\n" + "\n\n".join(
                f"### {name}\n{content}" for name, content in characters.items()
            ))

        places = fm.read_all_places()
        if places:
            parts.append("## Lieux\n" + "\n\n".join(
                f"### {name}\n{content}" for name, content in places.items()
            ))

        return "\n\n---\n\n".join(parts)

    def _write_acts(self, fm: FileManager, actes: list[dict]) -> None:
        for acte in actes:
            numero = acte.get("numero", 0)
            titre = acte.get("titre", f"Acte {numero}")
            content_lines = [
                f"# Acte {numero} — {titre}\n",
                f"## Résumé\n{acte.get('resume', '')}\n",
                f"## Enjeux\n{acte.get('enjeux', '')}\n",
                f"## Personnages clés\n" + "\n".join(f"- {p}" for p in acte.get("personnages_cles", [])) + "\n",
                f"## Lieux clés\n" + "\n".join(f"- {l}" for l in acte.get("lieux_cles", [])) + "\n",
                f"## Événements majeurs\n" + "\n".join(f"- {e}" for e in acte.get("evenements_majeurs", [])) + "\n",
                f"## Chapitres\nDu chapitre {acte.get('chapitre_debut', '?')} au chapitre {acte.get('chapitre_fin', '?')}\n",
            ]
            fm.write_act(numero, "\n".join(content_lines))
