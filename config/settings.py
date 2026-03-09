from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./writerai.db"

    # Storage
    projects_dir: str = "./projects"

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

    # Logging
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

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
