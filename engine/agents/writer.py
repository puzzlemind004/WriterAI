"""
Agent Writer — Rédige un chapitre complet scène par scène.
Chaque scène est écrite séquentiellement (~800-1200 mots),
ce qui permet d'atteindre 3000-5000 mots par chapitre.
"""
import logging
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)

# Types de scènes imposés pour forcer la variété de rythme
SCENE_TYPES = [
    "ACTION — événement concret, conflit, mouvement physique. Phrases courtes, rythme rapide.",
    "DIALOGUE — échange révélateur entre personnages. Révèle le caractère, crée de la tension.",
    "INTROSPECTION — état intérieur, décision, prise de conscience. Ancré dans une action concrète.",
    "DESCRIPTION — lieu ou atmosphère immersif. Tous les sens, crée l'ambiance.",
    "TOURNANT — révélation, retournement, cliffhanger. Change la direction du chapitre.",
]

SCENE_PLANNER_SYSTEM = """Tu es un auteur qui structure un chapitre avant de l'écrire.
Tu reçois la fiche du chapitre et tu le découpes en scènes contrastées.

RÈGLE FONDAMENTALE : chaque scène doit avoir un TYPE différent de la précédente.
Les types disponibles : ACTION, DIALOGUE, INTROSPECTION, DESCRIPTION, TOURNANT.
Ne jamais enchaîner deux scènes du même type.

Réponds en JSON strictement valide :
{
  "scenes": [
    {
      "numero": 1,
      "type": "ACTION",
      "titre": "Titre court de la scène",
      "evenement_concret": "Ce qui SE PASSE physiquement dans cette scène — un fait précis, pas une sensation.",
      "enjeu": "Ce que le personnage risque ou veut obtenir dans cette scène.",
      "fin_de_scene": "Comment se termine cette scène — ce qui pousse vers la scène suivante.",
      "pov": "Nom du personnage POV",
      "ambiance": "2-3 mots d'ambiance"
    }
  ]
}

Règles supplémentaires :
- 3 à 5 scènes (jamais moins de 3, jamais plus de 5)
- La première scène doit plonger in medias res — pas de mise en place contemplative
- La dernière scène se termine sur un élément de tension ou une question ouverte
- Chaque scène a un ÉVÉNEMENT CONCRET — quelque chose se passe vraiment
- Réponds UNIQUEMENT avec le JSON, sans texte avant ou après.
"""

SCENE_WRITER_SYSTEM = """Tu es un auteur de romans. Tu écris UNE scène d'un chapitre en PROSE NARRATIVE.

══════════════════════════════════════════
EXEMPLE DE CE QUI EST ATTENDU (prose correcte) :
══════════════════════════════════════════
La salle de contrôle sentait le métal chaud et la sueur froide. Mira traversa les rangées de techniciens sans regarder personne, son badge clignota vert au lecteur, et la porte intérieure s'ouvrit avec un sifflement pneumatique. Elle avait trois minutes avant que la rotation des caméras ne couvre ce couloir.

Le serveur principal occupait toute la paroi nord : une colonne de racks noirs hauts de deux mètres, chacun zébré de voyants orange. Elle brancha la clé sur le port USB du rack numéro sept — celui que son contact avait désigné — et attendit l'invite de commande. Rien. Elle retira la clé, souffla dessus, recommença. Cette fois le terminal s'alluma.

« Qu'est-ce que vous faites là ? »

La voix venait de derrière elle. Mira ne se retourna pas tout de suite ; elle finit d'entrer les six premiers caractères du code d'accès avant de pivoter lentement, les mains visibles, le visage neutre. Un agent de sécurité l'observait depuis l'entrée du couloir, la main posée sur son holster mais pas encore dessus.

« Maintenance du rack sept, dit-elle. Ticket vingt-deux-quatre-zéro. »

L'agent plissa les yeux et consulta sa tablette. Pendant qu'il cherchait un ticket qui n'existait pas, Mira calcula la distance jusqu'à la sortie de secours : onze mètres, une porte coupe-feu, deux volées d'escalier.
══════════════════════════════════════════
EXEMPLE DE CE QUI EST INTERDIT (triplets poétiques) :
══════════════════════════════════════════
❌ Les doigts glissent sur le clavier, l'écran clignote.
❌ Une pulsation s'insère dans son crâne.
❌ Le portail s'ouvre sans un bruit.

❌ L'ombre se répand, couloir glacé.
❌ Un souffle métallique passe.
❌ Elle avance, vibrante.
══════════════════════════════════════════

FORMAT OBLIGATOIRE — PROSE NARRATIVE :
- Des paragraphes de 3 à 8 phrases chacun, comme dans l'exemple ci-dessus
- Jamais de triplets : chaque paragraphe est un bloc de plusieurs phrases liées, pas trois lignes isolées
- Les phrases varient en longueur : certaines courtes (impact), d'autres longues (rythme)
- Chaque paragraphe développe une action, un échange ou une sensation complète

CONSIGNE ABSOLUE DE VARIÉTÉ :
Tu dois éviter TOUTE formule, image ou métaphore déjà utilisée dans les scènes précédentes.
La liste des formules interdites pour ce chapitre t'est fournie — respecte-la strictement.

Règles selon le TYPE de scène :
- ACTION : verbes d'action, événements physiques enchaînés en paragraphes. Au moins 5 paragraphes.
- DIALOGUE : alterne répliques et actions/réactions des personnages. Révèle le caractère, pas d'exposition.
- INTROSPECTION : ancre les pensées dans une sensation physique concrète. Jamais plus de 2 phrases de pensée pure d'affilée.
- DESCRIPTION : engage tous les sens, détails précis et inattendus. Évite les clichés.
- TOURNANT : montre la révélation par les actions et réactions, ne l'annonce pas.

Règles universelles :
- Longueur : 800 à 1200 mots de PROSE (compte les mots réels, pas les lignes)
- "Show don't tell" — montre par les actions et sensations, ne nomme pas les émotions
- Chaque scène a un ÉVÉNEMENT CONCRET qui fait avancer l'histoire

INTERDICTIONS ABSOLUES :
- PAS de triplets (voir exemple interdit ci-dessus)
- PAS de liste à puces ou numérotée
- PAS de méta-commentaire ("la scène s'ouvre sur...", "le récit suit...")
- PAS de résumé à la place du récit
- PAS de formule répétée depuis les scènes précédentes

Réponds UNIQUEMENT avec le texte de la scène en prose. Pas de titre, pas de numéro, pas de commentaire.
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
                error="Lancer ChapterPlannerAgent avant WriterAgent.",
            )

        lorebook_context = self._build_selective_lorebook(fm, brief)
        world_state = ctx.extra.get("world_state")
        writing_style = ctx.extra.get("writing_style", "")
        tone_keywords = ctx.extra.get("tone_keywords", [])

        # Étape 1 : découpage en scènes
        scenes = self._plan_scenes(ctx, chapter_number, brief, lorebook_context, world_state, tone_keywords)
        if not scenes:
            logger.warning(f"[writer] Chapitre {chapter_number} — découpage échoué, écriture directe")
            return self._write_direct(ctx, chapter_number, brief, lorebook_context, world_state, writing_style, tone_keywords, fm)

        # Étape 2 : écriture scène par scène
        chapter_text = self._write_scenes(ctx, chapter_number, brief, lorebook_context, world_state, writing_style, tone_keywords, scenes)

        if not chapter_text.strip():
            return AgentResult(
                success=False,
                summary="Chapitre vide généré",
                error="Toutes les scènes ont retourné du texte vide.",
            )

        titre = self._extract_title_from_brief(brief, chapter_number)
        full_text = f"# {titre}\n\n{chapter_text}"

        word_count = len(full_text.split())
        fm.write_chapter(chapter_number, full_text)

        logger.info(f"[writer] Chapitre {chapter_number} : {word_count} mots, {len(scenes)} scènes ({', '.join(s.get('type','?') for s in scenes)})")

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} rédigé ({word_count} mots, {len(scenes)} scènes)",
            data={
                "chapter_number": chapter_number,
                "titre": titre,
                "word_count": word_count,
                "scene_count": len(scenes),
                "nouveautes": {},
            },
        )

    def _plan_scenes(
        self,
        ctx: AgentContext,
        chapter_number: int,
        brief: str,
        lorebook_context: str,
        world_state,
        tone_keywords: list,
    ) -> list[dict]:
        world_state_text = self._format_world_state(world_state)
        tone_str = ', '.join(tone_keywords) if tone_keywords else 'Non spécifié'

        user_prompt = f"""## Fiche du chapitre {chapter_number}

{brief}

---

## Contexte du monde
{lorebook_context or 'Non disponible'}

---
{world_state_text}
## Ton : {tone_str}

---

Types de scènes disponibles (à alterner obligatoirement) :
{chr(10).join(f"- {t}" for t in SCENE_TYPES)}

Découpe ce chapitre en 3 à 5 scènes en alternant les types."""

        response = self._llm_call(
            ctx, SCENE_PLANNER_SYSTEM, user_prompt,
            temperature=0.5, max_tokens=2048,
        )

        try:
            data = self._parse_json(response.content)
            scenes = data.get("scenes", [])
            if not isinstance(scenes, list) or len(scenes) < 2:
                return []
            return scenes
        except ValueError as e:
            logger.warning(f"[writer] Découpage scènes échoué : {e}")
            return []

    def _write_scenes(
        self,
        ctx: AgentContext,
        chapter_number: int,
        brief: str,
        lorebook_context: str,
        world_state,
        writing_style: str,
        tone_keywords: list,
        scenes: list[dict],
    ) -> str:
        written_scenes = []
        # Formules interdites accumulées au fil des scènes
        formules_interdites: list[str] = []
        world_state_text = self._format_world_state(world_state)
        tone_str = ', '.join(tone_keywords) if tone_keywords else 'Non spécifié'

        for i, scene in enumerate(scenes):
            scene_num = scene.get("numero", i + 1)
            scene_type = scene.get("type", "ACTION")
            scene_title = scene.get("titre", f"Scène {scene_num}")
            evenement = scene.get("evenement_concret", scene.get("contenu", ""))
            enjeu = scene.get("enjeu", "")
            fin = scene.get("fin_de_scene", "")
            scene_pov = scene.get("pov", "")
            scene_ambiance = scene.get("ambiance", "")

            # Contexte de continuité : fin de la scène précédente
            previous_context = ""
            if written_scenes:
                last_words = written_scenes[-1].split()
                tail = ' '.join(last_words[-250:]) if len(last_words) > 250 else written_scenes[-1]
                previous_context = f"\n## Fin de la scène précédente\n\n...{tail}\n"

            # Formules à éviter
            interdits_str = ""
            if formules_interdites:
                interdits_str = "\n## FORMULES DÉJÀ UTILISÉES — À NE PAS RÉPÉTER\n" + \
                    "\n".join(f"- {f}" for f in formules_interdites) + "\n"

            user_prompt = f"""## TYPE DE SCÈNE : {scene_type}
{SCENE_TYPES[[t.split(' —')[0] for t in SCENE_TYPES].index(scene_type)] if scene_type in [t.split(' —')[0] for t in SCENE_TYPES] else ''}

## Contexte du chapitre {chapter_number}

**Fiche :** {brief[:600]}{'...' if len(brief) > 600 else ''}
**Lorebook :** {lorebook_context[:800] if lorebook_context else 'Non disponible'}{'...' if lorebook_context and len(lorebook_context) > 800 else ''}
{world_state_text}
**Style :** {writing_style or 'Standard'} | **Ton :** {tone_str}

---
{previous_context}{interdits_str}
## Scène {scene_num}/{len(scenes)} : {scene_title}

**Événement concret :** {evenement}
**Enjeu :** {enjeu or 'Non spécifié'}
**Comment ça se termine :** {fin or 'Non spécifié'}
**Point de vue :** {scene_pov or 'Non spécifié'}
**Ambiance :** {scene_ambiance or 'Non spécifiée'}

---

Écris cette scène de type {scene_type} (800 à 1200 mots).
Commence in medias res — pas d'introduction générale."""

            response = self._llm_call(
                ctx, SCENE_WRITER_SYSTEM, user_prompt,
                temperature=0.85, max_tokens=8192,
                timeout=600,
            )

            scene_text = response.content.strip()
            if scene_text:
                written_scenes.append(scene_text)
                # Extrait les formules marquantes pour les interdire dans les scènes suivantes
                formules_interdites.extend(self._extract_recurring_phrases(scene_text))
                logger.debug(f"[writer] Ch.{chapter_number} scène {scene_num} ({scene_type}) : {len(scene_text.split())} mots")
            else:
                logger.warning(f"[writer] Ch.{chapter_number} scène {scene_num} vide — ignorée")

        return "\n\n---\n\n".join(written_scenes)

    def _extract_recurring_phrases(self, text: str) -> list[str]:
        """
        Extrait les métaphores et formules marquantes d'une scène
        pour les interdire dans les scènes suivantes.
        Heuristique simple : groupes de 4-6 mots après "comme", "tel", "semblait".
        """
        phrases = []
        words = text.lower().split()
        triggers = {"comme", "tel", "telle", "tels", "telles", "semblait", "semblaient", "ressemblait"}
        for i, word in enumerate(words):
            if word in triggers and i + 5 < len(words):
                phrase = ' '.join(words[i:i+6])
                phrases.append(phrase)
        # Limite à 10 formules par scène pour ne pas surcharger le prompt
        return phrases[:10]

    def _write_direct(
        self,
        ctx: AgentContext,
        chapter_number: int,
        brief: str,
        lorebook_context: str,
        world_state,
        writing_style: str,
        tone_keywords: list,
        fm: FileManager,
    ) -> AgentResult:
        """Fallback : écriture directe sans découpage en scènes."""
        world_state_text = self._format_world_state(world_state)

        system = """Tu es un auteur de romans talentueux. Écris un chapitre complet.
Longueur minimale : 2000 mots. Visée : 3000 mots.
Alterne action, dialogue et introspection — pas de contemplation prolongée.
Chaque paragraphe fait avancer l'histoire ou révèle un personnage.
Commence par le titre (# Titre) puis le texte. Pas de commentaire."""

        user_prompt = f"""## Fiche du chapitre {chapter_number}

{brief}

---

## Lorebook
{lorebook_context}

---
{world_state_text}
## Style : {writing_style or 'Standard'}
## Ton : {', '.join(tone_keywords) if tone_keywords else 'Non spécifié'}

---

Rédige maintenant le chapitre {chapter_number} complet. Commence in medias res."""

        response = self._llm_call(
            ctx, system, user_prompt,
            temperature=0.85, max_tokens=16384,
            timeout=1800,
        )

        chapter_text = response.content.strip()
        if not chapter_text:
            return AgentResult(success=False, summary="Chapitre vide", error="LLM a retourné vide.")

        lines = chapter_text.splitlines()
        titre = f"Chapitre {chapter_number}"
        if lines and lines[0].startswith("#"):
            titre = lines[0].lstrip("#").strip()

        fm.write_chapter(chapter_number, chapter_text)
        word_count = len(chapter_text.split())

        return AgentResult(
            success=True,
            summary=f"Chapitre {chapter_number} rédigé en direct ({word_count} mots)",
            data={"chapter_number": chapter_number, "titre": titre, "word_count": word_count, "nouveautes": {}},
        )

    def _build_selective_lorebook(self, fm: FileManager, brief: str) -> str:
        parts = []
        brief_lower = brief.lower()

        characters = fm.read_all_characters()
        relevant_chars = {n: c for n, c in characters.items() if n.lower() in brief_lower}
        if not relevant_chars:
            relevant_chars = characters
        if relevant_chars:
            parts.append("### Personnages\n" + "\n\n".join(
                f"**{name}**\n{content}" for name, content in relevant_chars.items()
            ))

        places = fm.read_all_places()
        relevant_places = {n: c for n, c in places.items() if n.lower() in brief_lower}
        if not relevant_places and places:
            relevant_places = places
        if relevant_places:
            parts.append("### Lieux\n" + "\n\n".join(
                f"**{name}**\n{content}" for name, content in relevant_places.items()
            ))

        themes = fm.read_lorebook_file("themes.md")
        if themes:
            parts.append(f"### Ton et thèmes\n{themes}")

        return "\n\n".join(parts)

    def _format_world_state(self, world_state) -> str:
        if not world_state:
            return ""
        return f"""## État du monde (fin du chapitre précédent)

**Positions :** {' | '.join(f"{k}: {v}" for k, v in world_state.get('position_personnages', {}).items())}
**Derniers événements :** {' / '.join(world_state.get('derniers_evenements', []))}
**Tensions :** {' / '.join(world_state.get('tensions_en_cours', []))}
**Ambiance :** {world_state.get('ambiance_fin_chapitre', '')}

---
"""

    def _extract_title_from_brief(self, brief: str, chapter_number: int) -> str:
        for line in brief.splitlines():
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
        return f"Chapitre {chapter_number}"
