"""
Couche d'abstraction LLM via LiteLLM.
Tous les agents passent uniquement par cette interface.
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
import litellm

logger = logging.getLogger(__name__)

# Désactive les logs verbeux de litellm
litellm.suppress_debug_info = True


@dataclass
class LLMConfig:
    """Configuration LLM pour un projet ou un appel spécifique."""
    provider: str                    # "openai", "anthropic", "mistral", "ollama", ...
    model: str                       # "gpt-4o", "claude-opus-4-6", "qwen3:30b", ...
    api_key: Optional[str] = None    # Pas nécessaire pour Ollama
    temperature: float = 0.7
    max_tokens: int = 4096
    api_base: Optional[str] = None   # Obligatoire pour Ollama : "http://localhost:11434"


@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    duration_seconds: float
    model: str
    cost_usd: Optional[float] = None


class LLMClient:
    """
    Interface unique vers n'importe quel LLM via LiteLLM.
    Gère les erreurs, retries, et logging automatiquement.
    """

    def __init__(self, config: LLMConfig):
        self.config = config

    # Timeout par défaut en secondes (couvre les gros chapitres sur Ollama)
    DEFAULT_TIMEOUT = 600

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
    ) -> LLMResponse:
        """
        Appel synchrone au LLM. Retourne une LLMResponse structurée.
        Lève une exception en cas d'échec.
        """
        effective_temp = temperature if temperature is not None else self.config.temperature
        effective_max_tokens = max_tokens if max_tokens is not None else self.config.max_tokens

        if not 0.0 <= effective_temp <= 2.0:
            raise ValueError(f"temperature doit être entre 0.0 et 2.0, reçu : {effective_temp}")
        if not 1 <= effective_max_tokens <= 128000:
            raise ValueError(f"max_tokens doit être entre 1 et 128000, reçu : {effective_max_tokens}")

        model_string = self._build_model_string()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = {
            "model": model_string,
            "messages": messages,
            "temperature": effective_temp,
            "max_tokens": effective_max_tokens,
            "timeout": timeout if timeout is not None else self.DEFAULT_TIMEOUT,
        }
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key
        if self.config.api_base:
            kwargs["api_base"] = self.config.api_base

        start = time.time()
        try:
            response = litellm.completion(**kwargs)
        except litellm.RateLimitError as e:
            logger.error(f"Rate limit atteint sur {model_string}: {e}")
            raise
        except litellm.ContextWindowExceededError as e:
            logger.error(f"Contexte trop long pour {model_string}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Erreur LLM inattendue sur {model_string}: "
                f"[{type(e).__name__}] {e}"
            )
            raise RuntimeError(
                f"Appel LLM échoué sur {model_string} : [{type(e).__name__}] {e}"
            ) from e

        duration = time.time() - start

        if not response.choices:
            raise RuntimeError(f"Réponse LLM vide (aucun choix retourné) par {model_string}")
        content = response.choices[0].message.content or ""
        usage = response.usage

        cost = None
        try:
            cost = litellm.completion_cost(completion_response=response)
        except Exception:
            pass  # Coût non disponible pour ce modèle

        result = LLMResponse(
            content=content,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            duration_seconds=round(duration, 2),
            model=model_string,
            cost_usd=cost,
        )

        logger.info(
            f"LLM [{model_string}] "
            f"in={result.input_tokens} out={result.output_tokens} "
            f"t={result.duration_seconds}s"
            + (f" cost=${result.cost_usd:.4f}" if result.cost_usd else "")
        )

        return result

    def _build_model_string(self) -> str:
        """
        LiteLLM attend un format "provider/model" pour certains providers.
        OpenAI est l'exception (pas de préfixe nécessaire).
        """
        if self.config.provider == "openai":
            return self.config.model
        return f"{self.config.provider}/{self.config.model}"


def make_ollama_client(
    model: str = "qwen3:30b",
    api_base: str = "http://localhost:11434",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMClient:
    """Factory rapide pour Ollama (pas de clé API nécessaire)."""
    return LLMClient(LLMConfig(
        provider="ollama",
        model=model,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
    ))


def make_client(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> LLMClient:
    """Factory rapide pour créer un LLMClient."""
    config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return LLMClient(config)
