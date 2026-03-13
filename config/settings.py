from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator

# Répertoire racine du projet (là où se trouve ce fichier config/)
_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./writerai.db"

    # Storage — chemin absolu pour éviter les problèmes de CWD selon d'où uvicorn est lancé
    projects_dir: str = str(_ROOT / "projects")

    # LLM defaults (can be overridden per project)
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-4o"

    # Validation thresholds
    min_validation_score: float = Field(default=7.0, ge=0.0, le=10.0)
    max_revision_attempts: int = Field(default=5, ge=1, le=50)

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:4200"]

    # Redis (for Celery task queue)
    redis_url: str = "redis://localhost:6379/0"

    # Chiffrement des clés API (Fernet)
    writerai_secret_key: Optional[str] = None

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    cookie_secure: bool = False  # True en prod (HTTPS)

    # Logging
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if v == "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING":
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY utilise la valeur par défaut — définissez JWT_SECRET_KEY dans .env",
                stacklevel=2,
            )
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY doit faire au moins 32 caractères")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        supported = ("sqlite+aiosqlite", "postgresql+asyncpg", "mysql+aiomysql")
        if not any(v.startswith(prefix) for prefix in supported):
            raise ValueError(
                f"database_url non supportée. Préfixes acceptés : {supported}"
            )
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
