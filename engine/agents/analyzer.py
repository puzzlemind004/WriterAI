"""
Agent Analyzer — Phase 1 du pipeline.
Reçoit le(s) document(s) d'entrée et construit le lorebook initial.

Architecture : 5 extractions séquentielles avec des prompts courts et ciblés.
Chaque extraction est un appel LLM indépendant focalisé sur un seul type d'information.
Cela évite les prompts monolithiques qui font boucler les modèles locaux.

Extractions :
  1. Personnages
  2. Lieux
  3. Lore (règles du monde, magie, factions...)
  4. Story (arc narratif global)
  5. Thèmes (ton, ambiance, style)
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

# Prompt système commun à toutes les extractions
_SYSTEM = (
    "Tu es un analyste littéraire. "
    "Tu reçois un document décrivant une histoire et tu extrais des informations précises. "
    "Réponds UNIQUEMENT avec du JSON valide, sans texte avant ou après."
)

# Budget tokens par extraction — les réponses JSON sont courtes,
# 4096 est largement suffisant.
_MAX_TOKENS = 4096


class AnalyzerAgent(BaseAgent):
    name = "analyzer"

    def _run(self, ctx: AgentContext) -> AgentResult:
        source = ctx.extra.get("source_text", "").strip()
        if not source:
            return AgentResult(
                success=False,
                summary="Aucun document source fourni",
                error="Le champ 'source_text' est vide dans le contexte.",
            )

        fm = FileManager(ctx.project_id)
        counts = {"personnages": 0, "lieux": 0, "lore": 0}
        errors = []

        # --- 1. Personnages ---
        logger.info(f"[{self.name}] extraction des personnages...")
        personnages = self._extract_characters(ctx, source)
        if personnages:
            for p in personnages:
                nom = p.get("nom", "").strip()
                contenu = p.get("contenu", "").strip()
                if nom and contenu:
                    fm.write_character(nom, f"# {nom}\n\n{contenu}\n\n## Évolutions\n\n## Notes\n")
                    counts["personnages"] += 1
        else:
            errors.append("extraction personnages échouée")

        # --- 2. Lieux ---
        logger.info(f"[{self.name}] extraction des lieux...")
        lieux = self._extract_places(ctx, source)
        if lieux:
            for l in lieux:
                nom = l.get("nom", "").strip()
                contenu = l.get("contenu", "").strip()
                if nom and contenu:
                    fm.write_place(nom, f"# {nom}\n\n{contenu}\n\n## Évolutions\n\n## Notes\n")
                    counts["lieux"] += 1
        else:
            errors.append("extraction lieux échouée")

        # --- 3. Lore ---
        logger.info(f"[{self.name}] extraction du lore...")
        lore_items = self._extract_lore(ctx, source)
        if lore_items:
            for item in lore_items:
                nom = item.get("nom", "").strip()
                contenu = item.get("contenu", "").strip()
                if nom and contenu:
                    fm.write_lorebook_file(
                        f"lore/{fm._slugify(nom)}.md",
                        f"# {nom}\n\n{contenu}\n\n## Évolutions\n\n## Notes\n"
                    )
                    counts["lore"] += 1

        # --- 4. Story ---
        logger.info(f"[{self.name}] extraction de l'arc narratif...")
        story = self._extract_story(ctx, source)
        if story:
            fm.write_lorebook_file("story.md", f"# Histoire\n\n{story}\n")

        # --- 5. Thèmes ---
        logger.info(f"[{self.name}] extraction des thèmes...")
        themes = self._extract_themes(ctx, source)
        if themes:
            fm.write_lorebook_file("themes.md", f"# Thèmes et ton\n\n{themes}\n")

        # L'Analyzer réussit même partiellement — mieux vaut un lorebook
        # incomplet que bloquer tout le pipeline
        if counts["personnages"] == 0 and counts["lieux"] == 0:
            return AgentResult(
                success=False,
                summary="Lorebook vide — aucune extraction n'a fonctionné",
                error="; ".join(errors) if errors else "Aucun personnage ni lieu extrait",
            )

        return AgentResult(
            success=True,
            summary=(
                f"Lorebook créé : {counts['personnages']} personnage(s), "
                f"{counts['lieux']} lieu(x), {counts['lore']} élément(s) de lore"
            ),
            data=counts,
        )

    # ------------------------------------------------------------------ #
    #  Extractions spécialisées                                            #
    # ------------------------------------------------------------------ #

    def _extract_characters(self, ctx: AgentContext, source: str) -> list[dict]:
        """Extrait les personnages. Retourne [] en cas d'échec."""
        user_prompt = (
            f"Document :\n---\n{source}\n---\n\n"
            "Liste tous les personnages mentionnés.\n"
            "Format : "
            '{"personnages": [{"nom": "Nom", "contenu": "Description, personnalité, rôle dans l\'histoire"}]}'
        )
        try:
            response = self._llm_call(ctx, _SYSTEM, user_prompt, temperature=0.2, max_tokens=_MAX_TOKENS)
            data = self._parse_json(response.content)
            result = data.get("personnages", [])
            logger.info(f"[{self.name}] {len(result)} personnage(s) extrait(s)")
            return result
        except Exception as e:
            logger.warning(f"[{self.name}] extraction personnages échouée : {e}")
            return []

    def _extract_places(self, ctx: AgentContext, source: str) -> list[dict]:
        """Extrait les lieux. Retourne [] en cas d'échec."""
        user_prompt = (
            f"Document :\n---\n{source}\n---\n\n"
            "Liste tous les lieux importants mentionnés.\n"
            "Format : "
            '{"lieux": [{"nom": "Nom", "contenu": "Description, atmosphère, importance narrative"}]}'
        )
        try:
            response = self._llm_call(ctx, _SYSTEM, user_prompt, temperature=0.2, max_tokens=_MAX_TOKENS)
            data = self._parse_json(response.content)
            result = data.get("lieux", [])
            logger.info(f"[{self.name}] {len(result)} lieu(x) extrait(s)")
            return result
        except Exception as e:
            logger.warning(f"[{self.name}] extraction lieux échouée : {e}")
            return []

    def _extract_lore(self, ctx: AgentContext, source: str) -> list[dict]:
        """Extrait les éléments de lore (magie, factions, règles du monde...). Retourne [] si rien."""
        user_prompt = (
            f"Document :\n---\n{source}\n---\n\n"
            "Liste les éléments importants du monde (magie, factions, artefacts, règles, histoire du monde...).\n"
            "Si aucun élément de ce type n'est mentionné, retourne {\"lore\": []}.\n"
            "Format : "
            '{"lore": [{"nom": "Nom de l\'élément", "contenu": "Description"}]}'
        )
        try:
            response = self._llm_call(ctx, _SYSTEM, user_prompt, temperature=0.2, max_tokens=_MAX_TOKENS)
            data = self._parse_json(response.content)
            result = data.get("lore", [])
            logger.info(f"[{self.name}] {len(result)} élément(s) de lore extrait(s)")
            return result
        except Exception as e:
            logger.warning(f"[{self.name}] extraction lore échouée : {e}")
            return []

    def _extract_story(self, ctx: AgentContext, source: str) -> str:
        """Extrait l'arc narratif global. Retourne '' en cas d'échec."""
        system = (
            "Tu es un analyste littéraire. "
            "Tu reçois un document décrivant une histoire et tu rédiges un résumé narratif. "
            "Réponds UNIQUEMENT avec le texte du résumé, sans JSON, sans balise, sans titre."
        )
        user_prompt = (
            f"Document :\n---\n{source}\n---\n\n"
            "Résume l'arc narratif global de cette histoire en 3 à 5 paragraphes "
            "(début, milieu, fin, enjeux principaux, évolution des personnages)."
        )
        try:
            response = self._llm_call(ctx, system, user_prompt, temperature=0.3, max_tokens=_MAX_TOKENS)
            content = response.content.strip()
            if not content:
                raise ValueError("Réponse vide")
            return content
        except Exception as e:
            logger.warning(f"[{self.name}] extraction story échouée : {e}")
            return ""

    def _extract_themes(self, ctx: AgentContext, source: str) -> str:
        """Extrait le ton, l'ambiance et les thèmes. Retourne '' en cas d'échec."""
        system = (
            "Tu es un analyste littéraire. "
            "Tu reçois un document décrivant une histoire et tu décris son ton et ses thèmes. "
            "Réponds UNIQUEMENT avec le texte descriptif, sans JSON, sans balise, sans titre."
        )
        user_prompt = (
            f"Document :\n---\n{source}\n---\n\n"
            "Décris le ton, l'ambiance, les thèmes principaux et le style narratif de cette histoire."
        )
        try:
            response = self._llm_call(ctx, system, user_prompt, temperature=0.3, max_tokens=_MAX_TOKENS)
            content = response.content.strip()
            if not content:
                raise ValueError("Réponse vide")
            return content
        except Exception as e:
            logger.warning(f"[{self.name}] extraction thèmes échouée : {e}")
            return ""
