"""
Test end-to-end réel avec Ollama + qwen3:30b.
Lance le pipeline complet sur un pitch court (2 chapitres).
Permet d'évaluer la qualité du résultat avant de construire l'API.

Lancer avec : .venv/Scripts/python tests/test_e2e.py
"""
import sys
import os
import shutil
import time
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Active les logs pour voir ce qui se passe dans les agents
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

from engine.pipeline.orchestrator import Orchestrator, OrchestratorConfig
from engine.llm.client import make_ollama_client
from engine.events.bus import bus
from engine.events.types import EventType, Event
from engine.storage.file_manager import FileManager

# ------------------------------------------------------------------ #
#  Configuration du test                                               #
# ------------------------------------------------------------------ #

PROJECT_ID = "test_e2e_001"
PROJECTS_DIR = "./projects"

PITCH = """
Titre : Les Cendres de Valdor

Genre : Fantasy sombre

Pitch :
Kael est un ancien soldat de l'empire de Valdor, brisé par une guerre qu'il pensait juste.
Après avoir découvert que son commandant, le Général Maren, a massacré un village innocent
pour s'emparer d'une relique magique ancienne, Kael déserte et jure de faire éclater la vérité.

Mais la relique — un cristal noir capable d'absorber les âmes des morts — est maintenant
entre les mains de Maren qui cherche à l'utiliser pour ressusciter une armée de spectres.
Kael doit traverser les ruines de ce qu'il aimait, retrouver des anciens compagnons d'armes
devenus ennemis, et décider si la fin justifie les moyens.

Personnages principaux :
- Kael Dran : soldat déserteur, 34 ans, pragmatique et rongé par la culpabilité
- Général Maren : antagoniste charismatique, convaincu d'agir pour le bien de l'empire
- Lyra : espionne qui aide Kael, motivations floues, loyautés incertaines

Ton : sombre, tendu, quelques moments d'espoir fragile. Pas de happy end garanti.
"""

# ------------------------------------------------------------------ #
#  Listener d'événements pour suivre la progression                   #
# ------------------------------------------------------------------ #

def on_event(event: Event):
    t = time.strftime("%H:%M:%S")
    if event.type == EventType.AGENT_STARTED:
        print(f"  [{t}] >> {event.payload['agent']}", end="", flush=True)
    elif event.type == EventType.AGENT_COMPLETED:
        print(f" OK -- {event.payload['summary']}")
    elif event.type == EventType.AGENT_FAILED:
        print(f" FAIL -- {event.payload['error']}")
    elif event.type == EventType.CHAPTER_STATE_CHANGED:
        ch = event.payload.get('chapter_number', '?')
        print(f"  [{t}] Chapitre {ch} : {event.payload['old_state']} -> {event.payload['new_state']}")
    elif event.type == EventType.PIPELINE_STARTED:
        print(f"\n[{t}] === PIPELINE DEMARRE ===\n")
    elif event.type == EventType.PIPELINE_COMPLETED:
        print(f"\n[{t}] === PIPELINE TERMINE ===\n")
    elif event.type == EventType.PIPELINE_ERROR:
        print(f"\n[{t}] === ERREUR PIPELINE : {event.payload.get('error')} ===\n")
    elif event.type == EventType.VALIDATION_RESULT:
        payload = event.payload
        if payload.get("warning"):
            print(f"  [{t}] /!\\ {payload['warning']}")


# ------------------------------------------------------------------ #
#  Affichage des résultats                                             #
# ------------------------------------------------------------------ #

def print_results(project_id: str, report: dict):
    fm = FileManager(project_id)
    print("\n" + "="*60)
    print("RAPPORT FINAL")
    print("="*60)

    print(f"\nSuccès : {report['success']}")
    if report.get("error"):
        print(f"Erreur : {report['error']}")

    print(f"\n{'Chapitre':<12} {'État':<22} {'Score':<8} {'Révisions':<10} {'Forcé'}")
    print("-" * 65)
    for ch in report["chapters"]:
        score = f"{ch['last_score']:.1f}/10" if ch['last_score'] else "N/A"
        forced = "⚠ oui" if ch["validated_forced"] else "non"
        print(f"{ch['number']:<12} {ch['state']:<22} {score:<8} {ch['revision_count']:<10} {forced}")

    print("\n" + "="*60)
    print("LOREBOOK GÉNÉRÉ")
    print("="*60)

    characters = fm.list_lorebook_entities("personnages")
    places = fm.list_lorebook_entities("lieux")
    lore = fm.list_lorebook_entities("lore")
    print(f"\nPersonnages : {characters}")
    print(f"Lieux       : {places}")
    print(f"Lore        : {lore}")

    print("\n" + "="*60)
    print("APERÇU DES CHAPITRES")
    print("="*60)
    for ch in report["chapters"]:
        n = ch["number"]
        content = fm.read_chapter(n)
        if content:
            preview = content[:400].replace("\n", " ")
            print(f"\n--- Chapitre {n} (premiers 400 chars) ---")
            print(preview + "...")
        else:
            print(f"\n--- Chapitre {n} : non généré ---")


# ------------------------------------------------------------------ #
#  Main                                                                #
# ------------------------------------------------------------------ #

def main():
    # Nettoyage d'un éventuel test précédent
    project_path = os.path.join(PROJECTS_DIR, PROJECT_ID)
    if os.path.exists(project_path):
        shutil.rmtree(project_path)
        print(f"Projet précédent supprimé : {project_path}")

    # Abonnement aux événements
    bus.subscribe_all(on_event)

    config = OrchestratorConfig(
        project_id=PROJECT_ID,
        llm=make_ollama_client(model="gpt-oss:20b", thinking="high"),
        source_text=PITCH,
        tone_keywords=["sombre", "tendu", "fantasy"],
        writing_style=(
            "Écriture sobre et directe. Phrases courtes dans les scènes d'action. "
            "Dialogues révélateurs du caractère. Show don't tell."
        ),
        min_validation_score=6.0,   # Seuil bas pour le test
        max_revision_attempts=2,
    )

    start = time.time()
    report = Orchestrator(config).run()
    duration = time.time() - start

    print_results(PROJECT_ID, report)
    print(f"\nDurée totale : {duration:.0f}s ({duration/60:.1f} min)")


if __name__ == "__main__":
    main()
