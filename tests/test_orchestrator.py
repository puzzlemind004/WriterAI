"""
Test de l'orchestrateur avec des agents mockés (pas d'appels LLM réels).
Vérifie que le flux, les transitions d'état et la logique de validation fonctionnent.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch, MagicMock
from engine.pipeline.orchestrator import Orchestrator, OrchestratorConfig
from engine.pipeline.states import ChapterState
from engine.agents.base import AgentResult
from engine.llm.client import make_ollama_client


def _make_config(target_chapters=2) -> OrchestratorConfig:
    return OrchestratorConfig(
        project_id="test_orch",
        llm=make_ollama_client(),
        source_text="Un héros part à l'aventure.",
        target_chapter_count=target_chapters,
        min_validation_score=7.0,
        max_revision_attempts=2,
    )


def _success(data=None) -> AgentResult:
    return AgentResult(success=True, summary="OK", data=data or {})


def _failure(error="KO") -> AgentResult:
    return AgentResult(success=False, summary="Échec", error=error)


def test_pipeline_nominal():
    """Cas nominal : tout se passe bien du premier coup."""
    config = _make_config(target_chapters=2)
    orch = Orchestrator(config)

    # Mock de tous les agents
    orch._analyzer.run = lambda ctx: _success()
    orch._act_planner.run = lambda ctx: _success({"total_chapitres_suggere": 2, "actes": []})
    orch._chapter_planner.run = lambda ctx: _success({"nb_chapitres": 2, "chapitres": []})
    orch._continuity_reader.run = lambda ctx: _success({"world_state": None})
    orch._writer.run = lambda ctx: _success({"nouveautes": {}, "titre": "Ch", "char_count": 1000})
    orch._critic.run = lambda ctx: _success({
        "note_globale": 8.0,
        "commentaires_constructifs": [],
        "points_faibles": [],
        "verdict": "Bon chapitre",
    })
    orch._validator.run = lambda ctx: _success({"decision": "VALIDATED", "note": 8.0})
    orch._lore_extractor.run = lambda ctx: _success({"nouveautes": {}, "evolutions": []})
    orch._lore_keeper.run = lambda ctx: _success({"created": [], "evolved": [], "rejected": []})

    # Mock FileManager.init_project_structure
    with patch("engine.pipeline.orchestrator.FileManager") as MockFM:
        MockFM.return_value.init_project_structure = MagicMock()
        report = orch.run()

    assert report["success"] is True
    assert len(report["chapters"]) == 2
    for ch in report["chapters"]:
        assert ch["state"] == ChapterState.VALIDATED.value
        assert ch["revision_count"] == 0
    print("OK - pipeline nominal (2 chapitres validés au premier essai)")


def test_pipeline_avec_revision():
    """Un chapitre nécessite une révision avant d'être validé."""
    config = _make_config(target_chapters=1)
    orch = Orchestrator(config)

    call_count = {"critic": 0, "validator": 0}

    def mock_critic(ctx):
        call_count["critic"] += 1
        # Première critique : note basse. Deuxième : note haute.
        score = 5.0 if call_count["critic"] == 1 else 8.0
        return _success({
            "note_globale": score,
            "commentaires_constructifs": ["Améliorer le rythme"],
            "points_faibles": ["Rythme lent"],
            "verdict": "À améliorer" if score < 7 else "Bon",
        })

    def mock_validator(ctx):
        call_count["validator"] += 1
        note = ctx.extra.get("note_globale", 0)
        if note >= 7.0:
            return _success({"decision": "VALIDATED", "note": note})
        return _success({"decision": "REVISION_REQUESTED", "note": note})

    orch._analyzer.run = lambda ctx: _success()
    orch._act_planner.run = lambda ctx: _success({"total_chapitres_suggere": 1, "actes": []})
    orch._chapter_planner.run = lambda ctx: _success({"nb_chapitres": 1, "chapitres": []})
    orch._continuity_reader.run = lambda ctx: _success({"world_state": None})
    orch._writer.run = lambda ctx: _success({"nouveautes": {}, "titre": "Ch", "char_count": 1000})
    orch._critic.run = mock_critic
    orch._validator.run = mock_validator
    orch._revisor.run = lambda ctx: _success({"nouveautes": {}, "modifications": [], "char_count": 1000})
    orch._lore_extractor.run = lambda ctx: _success({"nouveautes": {}, "evolutions": []})
    orch._lore_keeper.run = lambda ctx: _success({"created": [], "evolved": [], "rejected": []})

    with patch("engine.pipeline.orchestrator.FileManager") as MockFM:
        MockFM.return_value.init_project_structure = MagicMock()
        report = orch.run()

    assert report["success"] is True
    ch = report["chapters"][0]
    assert ch["state"] == ChapterState.VALIDATED.value
    assert ch["revision_count"] == 1
    assert call_count["critic"] == 2
    assert call_count["validator"] == 2
    print(f"OK - pipeline avec révision (critique appelée {call_count['critic']}x, révision=1)")


def test_pipeline_validation_forcee():
    """Max révisions atteint → validation forcée."""
    config = _make_config(target_chapters=1)
    config.max_revision_attempts = 2
    orch = Orchestrator(config)

    orch._analyzer.run = lambda ctx: _success()
    orch._act_planner.run = lambda ctx: _success({"total_chapitres_suggere": 1, "actes": []})
    orch._chapter_planner.run = lambda ctx: _success({"nb_chapitres": 1, "chapitres": []})
    orch._continuity_reader.run = lambda ctx: _success({"world_state": None})
    orch._writer.run = lambda ctx: _success({"nouveautes": {}, "titre": "Ch", "char_count": 1000})
    orch._revisor.run = lambda ctx: _success({"nouveautes": {}, "modifications": [], "char_count": 1000})
    orch._lore_extractor.run = lambda ctx: _success({"nouveautes": {}, "evolutions": []})
    orch._lore_keeper.run = lambda ctx: _success({"created": [], "evolved": [], "rejected": []})

    call_count = {"validator": 0}

    def mock_critic(ctx):
        return _success({
            "note_globale": 4.0,
            "commentaires_constructifs": ["Tout à revoir"],
            "points_faibles": ["Tout"],
            "verdict": "Insuffisant",
        })

    def mock_validator(ctx):
        call_count["validator"] += 1
        note = ctx.extra.get("note_globale", 0)
        rev = ctx.extra.get("revision_count", 0)
        max_rev = ctx.extra.get("max_revision_attempts", 5)
        if rev >= max_rev:
            return _success({"decision": "VALIDATED_FORCED", "note": note})
        return _success({"decision": "REVISION_REQUESTED", "note": note})

    orch._critic.run = mock_critic
    orch._validator.run = mock_validator

    with patch("engine.pipeline.orchestrator.FileManager") as MockFM:
        MockFM.return_value.init_project_structure = MagicMock()
        report = orch.run()

    ch = report["chapters"][0]
    assert ch["state"] == ChapterState.VALIDATED.value
    assert ch["validated_forced"] is True
    assert ch["revision_count"] == config.max_revision_attempts
    print(f"OK - validation forcée après {ch['revision_count']} révisions")


def test_pipeline_echec_bloquant():
    """L'Analyzer échoue → PipelineError → rapport d'échec."""
    config = _make_config(target_chapters=1)
    orch = Orchestrator(config)

    orch._analyzer.run = lambda ctx: _failure("Document illisible")

    with patch("engine.pipeline.orchestrator.FileManager") as MockFM:
        MockFM.return_value.init_project_structure = MagicMock()
        report = orch.run()

    assert report["success"] is False
    assert "Analyzer" in report["error"]
    print("OK - échec bloquant détecté et rapporté")


if __name__ == "__main__":
    test_pipeline_nominal()
    test_pipeline_avec_revision()
    test_pipeline_validation_forcee()
    test_pipeline_echec_bloquant()
    print("\nTous les tests orchestrateur OK.")
