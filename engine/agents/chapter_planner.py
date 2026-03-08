"""
Agent ChapterPlanner — Phase 3 du pipeline.
Prend le plan des actes et génère une fiche détaillée par chapitre.
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un auteur expert en construction narrative. Tu reçois le plan des actes
d'une histoire et tu dois créer une fiche détaillée pour chaque chapitre.

Chaque fiche chapitre doit être suffisamment précise pour qu'un rédacteur puisse écrire
le chapitre sans avoir à prendre de décisions narratives majeures.

Tu dois produire une réponse JSON strictement valide avec cette structure :
{
  "chapitres": [
    {
      "numero": 1,
      "titre": "Titre du chapitre",
      "acte": 1,
      "resume_court": "Une phrase résumant le chapitre",
      "resume_detaille": "3 à 5 paragraphes décrivant précisément ce qui se passe",
      "scene_ouverture": "Description de la scène d'ouverture du chapitre",
      "scene_fermeture": "Description de la scène de clôture / cliffhanger éventuel",
      "personnages_presents": ["Personnage1", "Personnage2"],
      "lieu_principal": "Nom du lieu principal",
      "arc_emotionnel": "L'évolution émotionnelle du protagoniste dans ce chapitre",
      "tension_dramatique": "Ce qui crée la tension ou l'enjeu dans ce chapitre",
      "informations_revelees": ["Info révélée au lecteur 1", "Info révélée 2"],
      "ton_specifique": null
    }
  ]
}

Règles :
- Le champ ton_specifique peut être null (on utilisera le ton global) ou une liste de mots-clés
  si ce chapitre doit avoir une atmosphère particulière.
- Chaque chapitre doit faire avancer l'histoire ET développer les personnages.
- Les scènes d'ouverture et de fermeture doivent assurer la continuité entre chapitres.
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""


class ChapterPlannerAgent(BaseAgent):
    name = "chapter_planner"

    def _run(self, ctx: AgentContext) -> AgentResult:
        target_chapters = ctx.extra.get("target_chapter_count", 10)
        tone_keywords = ctx.extra.get("tone_keywords", [])
        writing_style = ctx.extra.get("writing_style", "")

        fm = FileManager(ctx.project_id)
        acts_content = fm.read_all_acts()

        if not acts_content:
            return AgentResult(
                success=False,
                summary="Aucun acte trouvé",
                error="Lancer ActPlannerAgent avant ChapterPlannerAgent.",
            )

        story = fm.read_lorebook_file("story.md")
        themes = fm.read_lorebook_file("themes.md")

        acts_text = "\n\n---\n\n".join(acts_content)

        user_prompt = f"""Voici le plan des actes de l'histoire :

{acts_text}

---
Contexte global :
{story}

Ton et ambiance : {', '.join(tone_keywords) if tone_keywords else 'Non spécifié'}
Style d'écriture : {writing_style or 'Non spécifié'}
Nombre total de chapitres : {target_chapters}

Génère la fiche détaillée pour chacun des {target_chapters} chapitres."""

        response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.5, max_tokens=8192)

        try:
            plan = self._parse_json(response.content)
        except ValueError as e:
            return AgentResult(
                success=False,
                summary="Réponse LLM non parseable",
                error=str(e),
                llm_response=response,
            )

        chapitres = plan.get("chapitres", [])
        briefs_paths = self._write_briefs(fm, chapitres)

        return AgentResult(
            success=True,
            summary=f"{len(chapitres)} fiche(s) chapitre créée(s)",
            data={
                "nb_chapitres": len(chapitres),
                "chapitres": chapitres,
                "briefs_paths": briefs_paths,
            },
            llm_response=response,
        )

    def _write_briefs(self, fm: FileManager, chapitres: list[dict]) -> list[str]:
        paths = []
        for ch in chapitres:
            numero = ch.get("numero", 0)
            lines = [
                f"# Chapitre {numero} — {ch.get('titre', '')}\n",
                f"**Acte :** {ch.get('acte', '?')}  \n",
                f"**Résumé :** {ch.get('resume_court', '')}\n",
                f"\n## Contenu détaillé\n{ch.get('resume_detaille', '')}\n",
                f"\n## Scène d'ouverture\n{ch.get('scene_ouverture', '')}\n",
                f"\n## Scène de fermeture\n{ch.get('scene_fermeture', '')}\n",
                f"\n## Personnages présents\n" + "\n".join(f"- {p}" for p in ch.get("personnages_presents", [])) + "\n",
                f"\n## Lieu principal\n{ch.get('lieu_principal', '')}\n",
                f"\n## Arc émotionnel\n{ch.get('arc_emotionnel', '')}\n",
                f"\n## Tension dramatique\n{ch.get('tension_dramatique', '')}\n",
                f"\n## Informations révélées\n" + "\n".join(f"- {i}" for i in ch.get("informations_revelees", [])) + "\n",
            ]
            if ch.get("ton_specifique"):
                lines.append(f"\n## Ton spécifique\n{', '.join(ch['ton_specifique'])}\n")

            path = fm.write_chapter_brief(numero, "".join(lines))
            paths.append(path)
        return paths