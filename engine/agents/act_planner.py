"""
Agent ActPlanner — Phase 2 du pipeline.
Lit le lorebook et découpe l'histoire en grands actes narratifs.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_FREE = """Tu es un scénariste expert en structure narrative. Tu reçois un lorebook complet
décrivant une histoire et tu dois la découper en grands actes narratifs, en décidant toi-même
du nombre de chapitres le plus adapté à cette histoire.

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
      "chapitre_fin": 3
    }
  ],
  "total_chapitres": 10
}

Règles ABSOLUES sur la numérotation des chapitres :
- Le premier acte commence TOUJOURS au chapitre 1.
- Chaque acte commence là où le précédent s'arrête + 1 (pas de trou, pas de chevauchement).
- Le dernier acte se termine au chapitre égal à "total_chapitres".
- 3 actes minimum, 5 maximum. Chaque acte doit avoir au moins 1 chapitre.
- Réponds UNIQUEMENT avec le JSON brut, sans texte avant ou après, sans bloc ```json.
"""

SYSTEM_PROMPT_FIXED = """Tu es un scénariste expert en structure narrative. Tu reçois un lorebook complet
décrivant une histoire et un nombre de chapitres IMPOSÉ. Tu dois découper l'histoire en grands actes narratifs
qui couvrent EXACTEMENT ce nombre de chapitres — ni plus, ni moins.

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
      "chapitre_fin": 3
    }
  ],
  "total_chapitres": 10
}

Règles ABSOLUES sur la numérotation des chapitres :
- Le premier acte commence TOUJOURS au chapitre 1.
- Chaque acte commence là où le précédent s'arrête + 1 (pas de trou, pas de chevauchement).
- Le dernier acte se termine EXACTEMENT au chapitre N (le nombre cible fourni).
- "total_chapitres" doit être égal au nombre cible fourni.
- 3 actes minimum, 5 maximum. Chaque acte doit avoir au moins 1 chapitre.
- Réponds UNIQUEMENT avec le JSON brut, sans texte avant ou après, sans bloc ```json.
"""


class ActPlannerAgent(BaseAgent):
    name = "act_planner"

    def _run(self, ctx: AgentContext) -> AgentResult:
        # None ou 0 = mode libre, le LLM décide du nombre de chapitres
        target_chapters = ctx.extra.get("target_chapter_count") or None
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

        if target_chapters:
            system_prompt = SYSTEM_PROMPT_FIXED
            chapter_line = f"Nombre de chapitres cible : {target_chapters} (OBLIGATOIRE)"
        else:
            system_prompt = SYSTEM_PROMPT_FREE
            chapter_line = "Nombre de chapitres : libre — choisis le nombre le plus adapté à cette histoire."

        user_prompt = f"""Voici le lorebook de l'histoire :

{lorebook_summary}

---
{chapter_line}
Ton et ambiance : {', '.join(tone_keywords) if tone_keywords else 'Non spécifié'}
Style d'écriture : {writing_style or 'Non spécifié'}

Découpe cette histoire en grands actes narratifs."""

        response = self._llm_call(ctx, system_prompt, user_prompt, temperature=0.4)

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
        if not actes:
            return AgentResult(
                success=False,
                summary="Aucun acte retourné par le LLM",
                error="Le champ 'actes' est vide dans la réponse.",
                llm_response=response,
            )

        # En mode libre, on fait confiance au LLM pour total_chapitres
        # En mode fixe, on force la valeur cible
        total_chapters = target_chapters if target_chapters else plan.get("total_chapitres", len(actes))
        actes = self._normalize_chapter_ranges(actes, total_chapters)
        self._write_acts(fm, actes)

        return AgentResult(
            success=True,
            summary=f"{len(actes)} acte(s) planifié(s) ({total_chapters} chapitres)",
            data={
                "nb_actes": len(actes),
                "total_chapitres": total_chapters,
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

    def _normalize_chapter_ranges(self, actes: list[dict], total: int) -> list[dict]:
        """
        Redistribue les chapitres sur les actes si le LLM n'a pas respecté la contrainte.
        Garantit : acte[0].chapitre_debut=1, acte[-1].chapitre_fin=total, pas de trous.
        """
        n = len(actes)
        # Vérifie si la numérotation est déjà correcte
        already_ok = (
            actes[0].get("chapitre_debut") == 1
            and actes[-1].get("chapitre_fin") == total
            and all(
                actes[i].get("chapitre_fin", 0) + 1 == actes[i + 1].get("chapitre_debut", 0)
                for i in range(n - 1)
            )
        )
        if already_ok:
            return actes

        logger.warning(
            f"[{self.name}] Numérotation chapitres incorrecte — redistribution sur {total} chapitres"
        )

        # Redistribution équitable : on répartit les chapitres en tranches égales
        chapters_per_act = total // n
        remainder = total % n
        current = 1
        for i, acte in enumerate(actes):
            size = chapters_per_act + (1 if i < remainder else 0)
            acte["chapitre_debut"] = current
            acte["chapitre_fin"] = current + size - 1
            current += size
        return actes

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
