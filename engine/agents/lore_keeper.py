"""
Agent LorebookKeeper — Gardien et arbitre du lorebook.
Reçoit les changements proposés par LoreExtractor et décide quoi accepter.

Responsabilités :
  - Vérifier que les nouveautés n'existent pas déjà (doublons, alias)
  - Vérifier que les évolutions ne contredisent pas le lore existant
  - Écrire dans le lorebook uniquement ce qui est validé
  - Logger les rejets avec leur justification
"""
import json
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VALIDATE = """Tu es le gardien d'un lorebook de roman. Tu reçois une liste de
changements proposés (nouveautés et évolutions) et le contenu actuel des fiches concernées.

Ton rôle est de valider ou rejeter chaque changement proposé en vérifiant :

Pour les NOUVEAUTÉS :
- Est-ce que cet élément existe déjà sous un nom différent ou légèrement différent ?
- Est-ce que la description est cohérente avec ce qui existe déjà dans le lorebook ?

Pour les ÉVOLUTIONS :
- Est-ce que ce changement contredit une information déjà enregistrée ?
- Est-ce que ce changement est cohérent avec la personnalité/nature de l'élément ?
- Est-ce qu'un autre chapitre a déjà enregistré une évolution qui rend celle-ci impossible ?

Réponds en JSON strictement valide :
{
  "nouveautes_validees": {
    "personnages": [{"nom": "Nom", "description": "Description"}],
    "lieux": [{"nom": "Nom", "description": "Description"}],
    "lore": [{"nom": "Nom", "description": "Description"}]
  },
  "evolutions_validees": [
    {
      "type": "personnage" | "lieu" | "lore",
      "nom": "Nom",
      "evolution": "Texte de l'évolution",
      "impact_potentiel": "faible" | "modéré" | "majeur"
    }
  ],
  "rejets": [
    {
      "element": "Nom de l'élément rejeté",
      "raison": "Explication claire du rejet (doublon, contradiction...)"
    }
  ]
}

Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""

SYSTEM_PROMPT_NEW_CHARACTER = """Tu es un archiviste littéraire. Crée une fiche markdown
complète pour un nouveau personnage à partir des informations fournies.

Structure obligatoire :
## Description physique
## Personnalité
## Rôle dans l'histoire
## Relations
## Histoire personnelle
## Évolutions
## Notes

Génère uniquement le contenu markdown, sans JSON ni titre (le titre sera ajouté séparément).
"""

SYSTEM_PROMPT_NEW_PLACE = """Tu es un archiviste littéraire. Crée une fiche markdown
complète pour un nouveau lieu à partir des informations fournies.

Structure obligatoire :
## Description
## Atmosphère
## Importance narrative
## Habitants / fréquentations
## Évolutions
## Notes

Génère uniquement le contenu markdown, sans JSON ni titre.
"""


class LorebookKeeperAgent(BaseAgent):
    name = "lore_keeper"

    def _run(self, ctx: AgentContext) -> AgentResult:
        chapter_number = ctx.chapter_number
        nouveautes = ctx.extra.get("nouveautes", {})
        evolutions = ctx.extra.get("evolutions", [])

        if not nouveautes and not evolutions:
            return AgentResult(
                success=True,
                summary="Aucun changement à traiter",
                data={"created": [], "evolved": [], "rejected": []},
            )

        fm = FileManager(ctx.project_id)

        # Construit le contexte lorebook existant pour la validation
        lorebook_context = self._build_validation_context(fm, nouveautes, evolutions)

        # Demande au LLM de valider/rejeter les changements proposés
        validated = self._validate_changes(ctx, nouveautes, evolutions, lorebook_context)
        if validated is None:
            # Fallback : on accepte tout sans validation si le LLM échoue
            logger.warning(f"[{self.name}] validation LLM échouée, acceptation directe des changements")
            validated = {
                "nouveautes_validees": nouveautes,
                "evolutions_validees": evolutions,
                "rejets": [],
            }

        # Applique les changements validés
        created = self._apply_creations(ctx, fm, validated.get("nouveautes_validees", {}))
        evolved = self._apply_evolutions(fm, validated.get("evolutions_validees", []), chapter_number)
        rejected = validated.get("rejets", [])

        for rejet in rejected:
            logger.warning(
                f"[{self.name}] rejeté : '{rejet.get('element')}' — {rejet.get('raison')}"
            )

        return AgentResult(
            success=True,
            summary=(
                f"{len(created)} créé(s), {len(evolved)} évolution(s) enregistrée(s), "
                f"{len(rejected)} rejeté(s)"
            ),
            data={
                "created": created,
                "evolved": evolved,
                "rejected": rejected,
            },
        )

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #

    def _build_validation_context(
        self, fm: FileManager, nouveautes: dict, evolutions: list[dict]
    ) -> str:
        """
        Récupère le contenu des fiches existantes concernées par les changements proposés,
        pour donner au LLM le contexte nécessaire à la validation.
        """
        parts = []

        # Pour les nouveautés : récupère tous les noms existants
        existing_chars = fm.list_lorebook_entities("personnages")
        existing_places = fm.list_lorebook_entities("lieux")
        existing_lore = fm.list_lorebook_entities("lore")

        if existing_chars:
            parts.append(f"Personnages existants : {', '.join(existing_chars)}")
        if existing_places:
            parts.append(f"Lieux existants : {', '.join(existing_places)}")
        if existing_lore:
            parts.append(f"Lore existant : {', '.join(existing_lore)}")

        # Pour les évolutions : récupère le contenu complet des fiches concernées
        concerned_names = {evo.get("nom", "") for evo in evolutions}
        for nom in concerned_names:
            fiche = fm.read_character(nom) or fm.read_place(nom)
            if fiche:
                parts.append(f"\n--- Fiche actuelle : {nom} ---\n{fiche[:1500]}")

        return "\n".join(parts) if parts else "Lorebook vide."

    def _validate_changes(
        self,
        ctx: AgentContext,
        nouveautes: dict,
        evolutions: list[dict],
        lorebook_context: str,
    ) -> dict | None:
        user_prompt = f"""Lorebook actuel :
{lorebook_context}

---

Changements proposés par l'extracteur :

Nouveautés :
{json.dumps(nouveautes, ensure_ascii=False, indent=2)}

Évolutions :
{json.dumps(evolutions, ensure_ascii=False, indent=2)}

Valide ou rejette chaque changement."""

        try:
            response = self._llm_call(ctx, SYSTEM_PROMPT_VALIDATE, user_prompt, temperature=0.1)
            return self._parse_json(response.content)
        except Exception as e:
            logger.error(f"[{self.name}] erreur validation : {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Application des changements validés                                 #
    # ------------------------------------------------------------------ #

    def _apply_creations(
        self, ctx: AgentContext, fm: FileManager, nouveautes_validees: dict
    ) -> list[str]:
        created = []

        for perso in nouveautes_validees.get("personnages", []):
            nom = perso.get("nom", "").strip()
            if not nom:
                continue
            fiche = self._generate_character_fiche(ctx, nom, perso.get("description", ""))
            fm.write_character(nom, fiche)
            created.append(f"personnage:{nom}")

        for lieu in nouveautes_validees.get("lieux", []):
            nom = lieu.get("nom", "").strip()
            if not nom:
                continue
            fiche = self._generate_place_fiche(ctx, nom, lieu.get("description", ""))
            fm.write_place(nom, fiche)
            created.append(f"lieu:{nom}")

        for lore_item in nouveautes_validees.get("lore", []):
            nom = lore_item.get("nom", "").strip()
            if not nom:
                continue
            fm.write_lorebook_file(
                f"lore/{fm._slugify(nom)}.md",
                f"# {nom}\n\n{lore_item.get('description', '')}\n\n## Évolutions\n\n## Notes\n"
            )
            created.append(f"lore:{nom}")

        return created

    def _apply_evolutions(
        self, fm: FileManager, evolutions_validees: list[dict], chapter_number: int | None
    ) -> list[str]:
        evolved = []
        chapter_ref = f"Chapitre {chapter_number}" if chapter_number else "Chapitre ?"

        for evo in evolutions_validees:
            entity_type = evo.get("type", "")
            nom = evo.get("nom", "").strip()
            evolution_text = evo.get("evolution", "").strip()

            if not nom or not evolution_text:
                continue

            new_line = f"- **{chapter_ref}** : {evolution_text}"

            if entity_type == "personnage":
                content = fm.read_character(nom)
                if not content:
                    continue
                fm.write_character(nom, self._inject_evolution(content, new_line))
                evolved.append(f"personnage:{nom}")

            elif entity_type == "lieu":
                content = fm.read_place(nom)
                if not content:
                    continue
                fm.write_place(nom, self._inject_evolution(content, new_line))
                evolved.append(f"lieu:{nom}")

            elif entity_type == "lore":
                slug = fm._slugify(nom)
                content = fm.read_lorebook_file(f"lore/{slug}.md")
                if not content:
                    continue
                fm.write_lorebook_file(f"lore/{slug}.md", self._inject_evolution(content, new_line))
                evolved.append(f"lore:{nom}")

        return evolved

    @staticmethod
    def _inject_evolution(content: str, new_line: str) -> str:
        if "## Évolutions" in content:
            return content.replace("## Évolutions", f"## Évolutions\n{new_line}", 1)
        return content.rstrip() + f"\n\n## Évolutions\n{new_line}\n"

    # ------------------------------------------------------------------ #
    #  Génération des fiches                                               #
    # ------------------------------------------------------------------ #

    def _generate_character_fiche(self, ctx: AgentContext, nom: str, description: str) -> str:
        try:
            response = self._llm_call(
                ctx, SYSTEM_PROMPT_NEW_CHARACTER,
                f"Personnage : {nom}\nDescription : {description}\nCrée la fiche.",
                temperature=0.3,
            )
            return f"# {nom}\n\n{response.content}\n"
        except Exception as e:
            logger.warning(f"[{self.name}] LLM échoué pour personnage '{nom}': {e}")
            return f"# {nom}\n\n{description}\n\n## Évolutions\n\n## Notes\n"

    def _generate_place_fiche(self, ctx: AgentContext, nom: str, description: str) -> str:
        try:
            response = self._llm_call(
                ctx, SYSTEM_PROMPT_NEW_PLACE,
                f"Lieu : {nom}\nDescription : {description}\nCrée la fiche.",
                temperature=0.3,
            )
            return f"# {nom}\n\n{response.content}\n"
        except Exception as e:
            logger.warning(f"[{self.name}] LLM échoué pour lieu '{nom}': {e}")
            return f"# {nom}\n\n{description}\n\n## Évolutions\n\n## Notes\n"