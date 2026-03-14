"""
Schémas Pydantic pour les requêtes et réponses de l'API.
Séparés des modèles SQLAlchemy pour ne pas exposer l'interne.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
#  Projets                                                             #
# ------------------------------------------------------------------ #

class LLMConfigSchema(BaseModel):
    provider: str = Field(examples=["ollama", "openai", "anthropic"])
    model: str = Field(examples=["gpt-oss:20b", "gpt-4o", "claude-haiku-4-5-20251001"])
    api_key: Optional[str] = None
    api_key_id: Optional[str] = None  # ID d'une clé stockée — résolu côté serveur
    api_base: Optional[str] = Field(default="http://localhost:11434", examples=["http://localhost:11434"])
    thinking: Optional[str] = Field(default=None, examples=["off", "low", "medium", "high"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_text: str = Field(min_length=10, description="Pitch ou synopsis de l'histoire")
    llm: LLMConfigSchema
    target_chapter_count: Optional[int] = Field(default=None, ge=1, le=100)
    writing_style: Optional[str] = None
    tone_keywords: list[str] = Field(default_factory=list)
    min_validation_score: float = Field(default=7.0, ge=0.0, le=10.0)
    max_revision_attempts: int = Field(default=5, ge=1, le=20)


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    status: str  # "idle", "running", "completed", "error"
    chapter_count: int
    chapters_done: int

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    source_text: str
    llm_provider: str
    llm_model: str
    llm_thinking: Optional[str]
    target_chapter_count: Optional[int]
    writing_style: Optional[str]
    tone_keywords: list[str]
    min_validation_score: float
    max_revision_attempts: int


# ------------------------------------------------------------------ #
#  Pipeline                                                            #
# ------------------------------------------------------------------ #

class PipelineStatus(BaseModel):
    project_id: str
    status: str  # "idle", "running", "completed", "error"
    current_agent: Optional[str] = None
    chapters: list[dict] = Field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ------------------------------------------------------------------ #
#  Contenu                                                             #
# ------------------------------------------------------------------ #

class ChapterResponse(BaseModel):
    number: int
    title: Optional[str]
    state: str
    content: Optional[str]
    score: Optional[float]
    revision_count: int
    brief: Optional[str] = None
    critic_comments: list[str] = Field(default_factory=list)


class LorebookResponse(BaseModel):
    characters: dict[str, str]  # nom -> contenu markdown
    places: dict[str, str]
    lore: dict[str, str]


# ------------------------------------------------------------------ #
#  Edition projet                                                      #
# ------------------------------------------------------------------ #

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    source_text: Optional[str] = Field(default=None, min_length=10)
    llm: Optional[LLMConfigSchema] = None
    target_chapter_count: Optional[int] = Field(default=None, ge=1, le=100)
    writing_style: Optional[str] = None
    tone_keywords: Optional[list[str]] = None
    min_validation_score: Optional[float] = Field(default=None, ge=0.0, le=10.0)
    max_revision_attempts: Optional[int] = Field(default=None, ge=1, le=20)


# ------------------------------------------------------------------ #
#  Edition chapitre                                                    #
# ------------------------------------------------------------------ #

class ChapterUpdateRequest(BaseModel):
    content: str = Field(min_length=1)
    title: Optional[str] = None


class ChapterVersionResponse(BaseModel):
    version: int
    content: str
    word_count: int


# ------------------------------------------------------------------ #
#  Révision ciblée                                                     #
# ------------------------------------------------------------------ #

class TargetedComment(BaseModel):
    selected_text: str
    comment: str


class ChapterRevisionRequest(BaseModel):
    comments: list[TargetedComment] = Field(min_length=1)
