"""
Agent ChapterPlanner — Phase 3 du pipeline.
Prend le plan des actes et génère une fiche détaillée par chapitre.

Architecture : un appel LLM par chapitre pour éviter les timeouts sur les modèles locaux.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un auteur expert en construction narrative. Tu reçois le plan d'un acte
et tu dois créer la fiche détaillée d'UN SEUL chapitre précis.

La fiche doit être suffisamment précise pour qu'un rédacteur puisse écrire le chapitre
sans avoir à prendre de décisions narratives majeures.

Réponds avec un JSON strictement valide contenant UN objet chapitre :
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

Règles :
- Le champ ton_specifique peut être null ou une liste de mots-clés si ce chapitre a une atmosphère particulière.
- Le chapitre doit faire avancer l'histoire ET développer les personnages.
- La scène de fermeture doit assurer la continuité avec le chapitre suivant.
- Réponds UNIQUEMENT avec le JSON brut, sans texte avant ou après, sans bloc ```json.
"""


class ChapterPlannerAgent(BaseAgent):
    name = "chapter_planner"

    def _run(self, ctx: AgentContext) -> AgentResult:
        tone_keywords = ctx.extra.get("tone_keywords", [])
        writing_style = ctx.extra.get("writing_style", "")
        total_chapters = ctx.extra.get("total_chapitres_from_acts", 0)

        fm = FileManager(ctx.project_id)
        acts_data = ctx.extra.get("actes_data", [])

        # Fallback : relit les fichiers actes si actes_data non fourni
        if not acts_data:
            acts_content = fm.read_all_acts()
            if not acts_content:
                return AgentResult(
                    success=False,
                    summary="Aucun acte trouvé",
                    error="Lancer ActPlannerAgent avant ChapterPlannerAgent.",
                )
            # Reconstruit la liste des chapitres depuis les fichiers actes
            acts_data = self._parse_acts_from_files(acts_content)

        story = fm.read_lorebook_file("story.md")
        tone_str = ', '.join(tone_keywords) if tone_keywords else 'Non spécifié'

        chapitres = []
        briefs_paths = []
        errors = []
        # Fil narratif cumulatif : scène de fermeture du dernier chapitre planifié
        # + personnages/lieux déjà introduits pour éviter les incohérences
        narrative_thread: dict = {
            "last_closing_scene": "",
            "introduced_characters": set(),
            "visited_places": set(),
        }

        for acte in acts_data:
            acte_num = acte.get("numero", "?")
            ch_debut = acte.get("chapitre_debut", 1)
            ch_fin = acte.get("chapitre_fin", 1)

            for ch_num in range(ch_debut, ch_fin + 1):
                logger.info(f"[{self.name}] fiche chapitre {ch_num} (acte {acte_num})...")

                user_prompt = self._build_prompt(
                    ch_num, acte, story, tone_str, writing_style,
                    total_chapters, narrative_thread
                )

                try:
                    response = self._llm_call(ctx, SYSTEM_PROMPT, user_prompt, temperature=0.5)
                    ch_data = self._parse_json(response.content)
                    # Garantit le bon numéro même si le LLM dévie
                    ch_data["numero"] = ch_num
                    ch_data["acte"] = acte_num
                    chapitres.append(ch_data)
                    path = self._write_brief(fm, ch_data)
                    briefs_paths.append(path)
                    # Met à jour le fil narratif pour le chapitre suivant
                    narrative_thread["last_closing_scene"] = ch_data.get("scene_fermeture", "")
                    narrative_thread["introduced_characters"].update(
                        ch_data.get("personnages_presents", [])
                    )
                    narrative_thread["visited_places"].add(ch_data.get("lieu_principal", ""))
                except Exception as e:
                    logger.warning(f"[{self.name}] fiche chapitre {ch_num} échouée : {e}")
                    errors.append(f"chapitre {ch_num} : {e}")

        if not chapitres:
            return AgentResult(
                success=False,
                summary="Aucune fiche chapitre générée",
                error="; ".join(errors) if errors else "Échec inconnu",
            )

        summary = f"{len(chapitres)} fiche(s) chapitre créée(s)"
        if errors:
            summary += f" ({len(errors)} échec(s))"

        return AgentResult(
            success=True,
            summary=summary,
            data={
                "nb_chapitres": len(chapitres),
                "chapitres": chapitres,
                "briefs_paths": briefs_paths,
            },
        )

    def _build_prompt(
        self,
        ch_num: int,
        acte: dict,
        story: str,
        tone_str: str,
        writing_style: str,
        total_chapters: int,
        narrative_thread: dict,
    ) -> str:
        acte_resume = acte.get("resume", "")
        acte_enjeux = acte.get("enjeux", "")
        acte_evenements = acte.get("evenements_majeurs", [])
        ch_debut = acte.get("chapitre_debut", ch_num)
        ch_fin = acte.get("chapitre_fin", ch_num)
        nb_ch_acte = ch_fin - ch_debut + 1
        position = ch_num - ch_debut + 1

        evenements_str = "\n".join(f"- {e}" for e in acte_evenements) if acte_evenements else "Non spécifié"

        # Fil narratif — continuité depuis le chapitre précédent
        continuity_block = ""
        if narrative_thread["last_closing_scene"]:
            chars = ", ".join(sorted(narrative_thread["introduced_characters"])) or "aucun encore"
            places = ", ".join(p for p in sorted(narrative_thread["visited_places"]) if p) or "aucun encore"
            continuity_block = f"""
## CONTINUITÉ OBLIGATOIRE
La scène d'ouverture du chapitre {ch_num} doit s'enchaîner directement avec cette scène de fermeture du chapitre {ch_num - 1} :
"{narrative_thread['last_closing_scene']}"

Personnages déjà introduits dans l'histoire (ne pas en inventer de nouveaux sans justification) :
{chars}

Lieux déjà visités :
{places}
"""

        return f"""Contexte global de l'histoire :
{story or 'Non disponible'}

---
Acte {acte.get('numero')} — {acte.get('titre', '')}
Résumé de l'acte : {acte_resume}
Enjeux : {acte_enjeux}
Événements majeurs de l'acte :
{evenements_str}
Chapitres de cet acte : {ch_debut} à {ch_fin} ({nb_ch_acte} chapitre(s))
{continuity_block}
---
Ton et ambiance : {tone_str}
Style d'écriture : {writing_style or 'Non spécifié'}
Nombre total de chapitres dans le livre : {total_chapters}

Génère la fiche du chapitre {ch_num} (chapitre {position}/{nb_ch_acte} de cet acte)."""

    def _parse_acts_from_files(self, acts_content: list[str]) -> list[dict]:
        """
        Reconstruit une liste minimale d'actes depuis les fichiers markdown
        quand actes_data n'est pas disponible dans le contexte.
        """
        acts = []
        for i, content in enumerate(acts_content, start=1):
            # Extrait chapitre_debut et chapitre_fin depuis la ligne "Du chapitre X au chapitre Y"
            import re
            match = re.search(r"Du chapitre (\d+) au chapitre (\d+)", content)
            if match:
                acts.append({
                    "numero": i,
                    "titre": "",
                    "resume": "",
                    "enjeux": "",
                    "evenements_majeurs": [],
                    "chapitre_debut": int(match.group(1)),
                    "chapitre_fin": int(match.group(2)),
                })
        return acts

    def _write_brief(self, fm: FileManager, ch: dict) -> str:
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

        return fm.write_chapter_brief(numero, "".join(lines))
