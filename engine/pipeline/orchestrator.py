"""
Orchestrateur du moteur de rédaction.
Gère le flux complet : initialisation du projet → rédaction → validation de chaque chapitre.

Ordre d'exécution :
  Phase 1 (init) :
    Analyzer → ActPlanner → ChapterPlanner

  Phase 2 (par chapitre, séquentielle) :
    ContinuityReader → Writer → Critic → Validator
      → si VALIDATED : LoreExtractor → LorebookKeeper → chapitre suivant
      → si REVISION   : Revisor → Critic → Validator (boucle)

Contrainte clé : LoreExtractor + LorebookKeeper s'exécutent APRÈS validation,
jamais pendant la boucle de révision.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from engine.agents import (
    AnalyzerAgent, ActPlannerAgent, ChapterPlannerAgent,
    ContinuityReaderAgent, WriterAgent, LoreExtractorAgent,
    LorebookKeeperAgent, CriticAgent, ValidatorAgent, RevisorAgent,
    AgentContext, AgentResult,
)
from engine.events.bus import bus
from engine.events.types import Event, EventType
from engine.llm.client import LLMClient
from engine.pipeline.states import ChapterState, validate_transition, InvalidTransitionError
from engine.storage.file_manager import FileManager

logger = logging.getLogger(__name__)


@dataclass
class ChapterStatus:
    """État en mémoire d'un chapitre pendant l'orchestration."""
    number: int
    state: ChapterState = ChapterState.PENDING
    revision_count: int = 0
    last_score: Optional[float] = None
    last_comments: list[str] = field(default_factory=list)
    validated_forced: bool = False


@dataclass
class OrchestratorConfig:
    """Configuration complète d'un projet pour l'orchestrateur."""
    project_id: str
    llm: LLMClient
    source_text: str
    target_chapter_count: Optional[int] = None  # None = laisse le LLM décider
    tone_keywords: list[str] = field(default_factory=list)
    writing_style: str = ""
    min_validation_score: float = 7.0
    max_revision_attempts: int = 5
    critic_grid: Optional[str] = None  # Grille personnalisée, None = grille par défaut


class PipelineError(Exception):
    """Levée quand un agent bloquant échoue et qu'on ne peut pas continuer."""
    pass


class Orchestrator:
    """
    Orchestre l'ensemble du pipeline de rédaction.
    S'exécute de façon synchrone et séquentielle.
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.chapters: list[ChapterStatus] = []

        # Instanciation des agents (stateless — réutilisables)
        self._analyzer = AnalyzerAgent()
        self._act_planner = ActPlannerAgent()
        self._chapter_planner = ChapterPlannerAgent()
        self._continuity_reader = ContinuityReaderAgent()
        self._writer = WriterAgent()
        self._lore_extractor = LoreExtractorAgent()
        self._lore_keeper = LorebookKeeperAgent()
        self._critic = CriticAgent()
        self._validator = ValidatorAgent()
        self._revisor = RevisorAgent()

    # ------------------------------------------------------------------ #
    #  Point d'entrée principal                                            #
    # ------------------------------------------------------------------ #

    def run(self) -> dict:
        """
        Lance le pipeline complet.
        Retourne un rapport final avec l'état de chaque chapitre.
        """
        self._emit(EventType.PIPELINE_STARTED, {"project_id": self.config.project_id})
        logger.info(f"[orchestrator] Démarrage du pipeline — project={self.config.project_id}")

        try:
            # Phase 1 : initialisation
            self._run_init_phase()

            # Phase 2 : rédaction chapitre par chapitre
            for chapter in self.chapters:
                self._run_chapter_pipeline(chapter)

        except PipelineError as e:
            logger.error(f"[orchestrator] Pipeline interrompu : {e}")
            self._emit(EventType.PIPELINE_ERROR, {"error": str(e)})
            return self._build_report(success=False, error=str(e))

        report = self._build_report(success=True)
        self._emit(EventType.PIPELINE_COMPLETED, report)
        logger.info(f"[orchestrator] Pipeline terminé — {len(self.chapters)} chapitre(s) traités")
        return report

    # ------------------------------------------------------------------ #
    #  Phase 1 : Initialisation                                            #
    # ------------------------------------------------------------------ #

    def _run_init_phase(self) -> None:
        """Analyzer → ActPlanner → ChapterPlanner."""
        fm = FileManager(self.config.project_id)
        fm.init_project_structure()

        # 1. Analyzer
        ctx = self._make_ctx(extra={"source_text": self.config.source_text})
        result = self._analyzer.run(ctx)
        self._require_success(result, "Analyzer")

        # 2. ActPlanner — définit le nombre de chapitres et leur répartition par acte
        ctx = self._make_ctx(extra=self._narrative_extra())
        result = self._act_planner.run(ctx)
        self._require_success(result, "ActPlanner")

        # L'ActPlanner est la source de vérité sur le nombre de chapitres
        total_chapters = result.data.get("total_chapitres", self.config.target_chapter_count)
        logger.info(f"[orchestrator] ActPlanner : {result.data.get('nb_actes')} acte(s), {total_chapters} chapitre(s)")

        # 3. ChapterPlanner — reçoit le total et les données des actes
        actes_data = result.data.get("actes", [])
        chapter_extra = {
            **self._narrative_extra(),
            "total_chapitres_from_acts": total_chapters,
            "actes_data": actes_data,
        }
        ctx = self._make_ctx(extra=chapter_extra)
        result = self._chapter_planner.run(ctx)
        self._require_success(result, "ChapterPlanner")

        nb_chapitres = result.data.get("nb_chapitres", total_chapters)
        if nb_chapitres != total_chapters:
            logger.warning(
                f"[orchestrator] ChapterPlanner a produit {nb_chapitres} fiches "
                f"au lieu de {total_chapters} — utilisation des {nb_chapitres} fiches produites"
            )
        self.chapters = [ChapterStatus(number=i + 1) for i in range(nb_chapitres)]
        logger.info(f"[orchestrator] {nb_chapitres} chapitre(s) planifié(s)")

    # ------------------------------------------------------------------ #
    #  Phase 2 : Pipeline par chapitre                                     #
    # ------------------------------------------------------------------ #

    def _run_chapter_pipeline(self, chapter: ChapterStatus) -> None:
        """
        Pipeline complet pour un chapitre :
        ContinuityReader → Writer → boucle(Critic → Validator) → LoreExtractor → LorebookKeeper
        """
        n = chapter.number
        logger.info(f"[orchestrator] Chapitre {n} — démarrage")

        # Lecture de la continuité depuis le chapitre précédent
        world_state = self._read_continuity(n)

        # Première rédaction
        self._transition(chapter, ChapterState.WRITING)
        writer_result = self._write_chapter(n, world_state)
        if not writer_result.success:
            self._transition(chapter, ChapterState.ERROR)
            logger.error(f"[orchestrator] Chapitre {n} — rédaction échouée, passage en ERROR")
            return

        # Boucle critique / validation
        validated = False
        while not validated:
            self._transition(chapter, ChapterState.IN_REVIEW)
            critic_result = self._critique_chapter(n)

            if not critic_result.success:
                self._transition(chapter, ChapterState.ERROR)
                logger.error(f"[orchestrator] Chapitre {n} — critique échouée, passage en ERROR")
                return

            score = critic_result.data.get("note_globale", 0.0)
            comments = critic_result.data.get("commentaires_constructifs", [])
            chapter.last_score = score
            chapter.last_comments = comments

            validator_result = self._validate_chapter(n, score, comments, chapter.revision_count)

            decision = validator_result.data.get("decision")

            if decision in ("VALIDATED", "VALIDATED_FORCED"):
                chapter.validated_forced = decision == "VALIDATED_FORCED"
                validated = True

            elif decision == "REVISION_REQUESTED":
                self._transition(chapter, ChapterState.REVISION_REQUESTED)
                chapter.revision_count += 1

                revisor_result = self._revise_chapter(n, comments, critic_result.data)
                if not revisor_result.success:
                    # Révision échouée : on valide de force plutôt que de bloquer
                    logger.warning(f"[orchestrator] Chapitre {n} — révision échouée, validation forcée")
                    chapter.validated_forced = True
                    validated = True
                else:
                    # Les nouveautés du reviseur seront traitées si le chapitre est validé
                    writer_result = revisor_result  # Pour récupérer les nouveautés en fin de boucle
                    self._transition(chapter, ChapterState.WRITING)

            else:
                # Décision inconnue — on sort de la boucle par sécurité
                logger.error(f"[orchestrator] Chapitre {n} — décision inconnue : {decision}")
                validated = True

        # Chapitre validé — mise à jour du lorebook sur la version finale
        self._update_lorebook(n, writer_result)
        self._transition(chapter, ChapterState.VALIDATED)
        logger.info(f"[orchestrator] Chapitre {n} — validé (score={chapter.last_score}, révisions={chapter.revision_count})")

    # ------------------------------------------------------------------ #
    #  Appels aux agents individuels                                       #
    # ------------------------------------------------------------------ #

    def _read_continuity(self, chapter_number: int) -> Optional[dict]:
        ctx = self._make_ctx(chapter_number=chapter_number)
        result = self._continuity_reader.run(ctx)
        return result.data.get("world_state") if result.success else None

    def _write_chapter(self, chapter_number: int, world_state: Optional[dict]) -> AgentResult:
        extra = {**self._narrative_extra(), "world_state": world_state}
        ctx = self._make_ctx(chapter_number=chapter_number, extra=extra)
        return self._writer.run(ctx)

    def _critique_chapter(self, chapter_number: int) -> AgentResult:
        extra = self._narrative_extra()
        if self.config.critic_grid:
            extra["critic_grid"] = self.config.critic_grid
        ctx = self._make_ctx(chapter_number=chapter_number, extra=extra)
        return self._critic.run(ctx)

    def _validate_chapter(
        self,
        chapter_number: int,
        score: float,
        comments: list[str],
        revision_count: int,
    ) -> AgentResult:
        extra = {
            "note_globale": score,
            "commentaires_constructifs": comments,
            "revision_count": revision_count,
            "min_validation_score": self.config.min_validation_score,
            "max_revision_attempts": self.config.max_revision_attempts,
        }
        ctx = self._make_ctx(chapter_number=chapter_number, extra=extra)
        return self._validator.run(ctx)

    def _revise_chapter(
        self,
        chapter_number: int,
        comments: list[str],
        critic_data: dict,
    ) -> AgentResult:
        extra = {
            **self._narrative_extra(),
            "commentaires_constructifs": comments,
            "points_faibles": critic_data.get("points_faibles", []),
            "note_globale": critic_data.get("note_globale"),
        }
        ctx = self._make_ctx(chapter_number=chapter_number, extra=extra)
        return self._revisor.run(ctx)

    def _update_lorebook(self, chapter_number: int, writer_result: AgentResult) -> None:
        """LoreExtractor puis LorebookKeeper — uniquement après validation."""
        nouveautes = writer_result.data.get("nouveautes", {})

        # LoreExtractor
        extractor_ctx = self._make_ctx(
            chapter_number=chapter_number,
            extra={"nouveautes": nouveautes},
        )
        extractor_result = self._lore_extractor.run(extractor_ctx)

        if extractor_result.success:
            keeper_ctx = self._make_ctx(
                chapter_number=chapter_number,
                extra={
                    "nouveautes": extractor_result.data.get("nouveautes", {}),
                    "evolutions": extractor_result.data.get("evolutions", []),
                },
            )
            self._lore_keeper.run(keeper_ctx)
        else:
            logger.warning(f"[orchestrator] Chapitre {chapter_number} — LoreExtractor échoué, lorebook non mis à jour")

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _make_ctx(
        self,
        chapter_number: Optional[int] = None,
        extra: Optional[dict] = None,
    ) -> AgentContext:
        return AgentContext(
            project_id=self.config.project_id,
            llm=self.config.llm,
            chapter_number=chapter_number,
            extra=extra or {},
        )

    def _narrative_extra(self) -> dict:
        """Contexte narratif commun à plusieurs agents."""
        return {
            "target_chapter_count": self.config.target_chapter_count,
            "tone_keywords": self.config.tone_keywords,
            "writing_style": self.config.writing_style,
        }

    def _require_success(self, result: AgentResult, agent_name: str) -> None:
        """Lève PipelineError si un agent bloquant a échoué."""
        if not result.success:
            raise PipelineError(
                f"Agent {agent_name} a échoué (bloquant) : {result.error}"
            )

    def _transition(self, chapter: ChapterStatus, new_state: ChapterState) -> None:
        """Effectue une transition d'état avec validation et émission d'événement."""
        try:
            validate_transition(chapter.state, new_state)
        except InvalidTransitionError as e:
            logger.warning(f"[orchestrator] {e} — transition ignorée")
            return

        old_state = chapter.state
        chapter.state = new_state

        self._emit(EventType.CHAPTER_STATE_CHANGED, {
            "chapter_number": chapter.number,
            "old_state": old_state.value,
            "new_state": new_state.value,
        })

    def _emit(self, event_type: EventType, payload: dict) -> None:
        bus.emit(Event(
            type=event_type,
            project_id=self.config.project_id,
            payload=payload,
        ))

    def _build_report(self, success: bool, error: Optional[str] = None) -> dict:
        return {
            "success": success,
            "project_id": self.config.project_id,
            "error": error,
            "chapters": [
                {
                    "number": ch.number,
                    "state": ch.state.value,
                    "revision_count": ch.revision_count,
                    "last_score": ch.last_score,
                    "validated_forced": ch.validated_forced,
                }
                for ch in self.chapters
            ],
        }
