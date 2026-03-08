import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.agents import (
    AnalyzerAgent, ActPlannerAgent, ChapterPlannerAgent,
    ContinuityReaderAgent, WriterAgent, LoreExtractorAgent,
    LorebookKeeperAgent, CriticAgent, ValidatorAgent, RevisorAgent
)
from engine.agents.base import BaseAgent, AgentContext, AgentResult
from engine.storage.file_manager import FileManager
from engine.llm.client import make_ollama_client


class _TestAgent(BaseAgent):
    name = "test"
    def _run(self, ctx): pass

agent = _TestAgent()


def test_parse_json_brut():
    assert agent._parse_json('{"a": 1}') == {"a": 1}
    print("OK - JSON brut")

def test_parse_json_markdown():
    assert agent._parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert agent._parse_json('```\n{"a": 1}\n```') == {"a": 1}
    print("OK - JSON dans bloc markdown")

def test_parse_json_recovery():
    # Texte parasite autour du JSON
    assert agent._parse_json('Voici le JSON : {"a": 1} voilà') == {"a": 1}
    print("OK - Récupération JSON avec texte parasite")

def test_parse_json_invalid():
    try:
        agent._parse_json("pas du json du tout")
        assert False, "aurait dû lever ValueError"
    except ValueError:
        pass
    print("OK - ValueError sur JSON invalide")

def test_slugify():
    assert FileManager._slugify("Elara Nightwood") == "elara_nightwood"
    assert FileManager._slugify("Chateau/Foret") == "chateau_foret"
    assert FileManager._slugify("Nom\x00Null") == "nomnull"
    assert len(FileManager._slugify("a" * 200)) == 100
    try:
        FileManager._slugify("")
        assert False, "slug vide devrait lever ValueError"
    except ValueError:
        pass
    print("OK - _slugify")

def test_safe_path():
    fm = FileManager("test_project")
    # Traversal classique
    try:
        fm._safe_path(fm.root / "notes", "../../../etc/passwd")
        assert False, "traversal devrait être bloqué"
    except ValueError:
        pass
    # Chemin vide
    try:
        fm._safe_path(fm.root / "notes", "")
        assert False, "chemin vide devrait être bloqué"
    except ValueError:
        pass
    # Chemin valide
    p = fm._safe_path(fm.root / "notes", "personnages/test.md")
    assert "personnages" in str(p)
    print("OK - _safe_path")

def test_validator_invalid_note():
    v = ValidatorAgent()
    ctx = AgentContext(project_id="p1", llm=make_ollama_client(), extra={"note_globale": 15.0})
    r = v._run(ctx)
    assert not r.success
    print("OK - ValidatorAgent rejette note > 10")

def test_validator_invalid_chapter():
    v = ValidatorAgent()
    ctx = AgentContext(
        project_id="p1", llm=make_ollama_client(),
        chapter_number=0,
        extra={"note_globale": 7.0}
    )
    r = v._run(ctx)
    assert not r.success
    print("OK - ValidatorAgent rejette chapter_number=0")


if __name__ == "__main__":
    test_parse_json_brut()
    test_parse_json_markdown()
    test_parse_json_recovery()
    test_parse_json_invalid()
    test_slugify()
    test_safe_path()
    test_validator_invalid_note()
    test_validator_invalid_chapter()
    print("\nTout OK.")
