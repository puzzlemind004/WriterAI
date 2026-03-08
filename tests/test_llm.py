"""
Test rapide de la couche LLM avec Ollama.
Lancer avec : python -m pytest tests/test_llm.py -v -s
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.llm import make_ollama_client


def test_ollama_simple_call():
    client = make_ollama_client(model="qwen3:30b")
    response = client.call(
        system_prompt="Tu es un assistant de test. Réponds toujours très brièvement.",
        user_prompt="Dis juste 'OK' pour confirmer que tu fonctionnes.",
    )
    print(f"\nRéponse : {response.content}")
    print(f"Tokens : {response.input_tokens} in / {response.output_tokens} out")
    print(f"Durée  : {response.duration_seconds}s")
    assert len(response.content) > 0


if __name__ == "__main__":
    test_ollama_simple_call()
    print("Test OK !")
