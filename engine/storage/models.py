"""
Modèles de données SQLAlchemy.
Représente tout ce qui est stocké en base (états, metadata, logs).
Le contenu narratif (lorebook, chapitres) reste en fichiers markdown.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text,
    ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import DeclarativeBase, relationship
from engine.storage.crypto import encrypt, decrypt


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Configuration LLM du projet
    llm_provider = Column(String, nullable=False)
    llm_model = Column(String, nullable=False)
    _llm_api_key_encrypted = Column("llm_api_key", String, nullable=True)
    llm_api_base = Column(String, nullable=True)
    llm_thinking = Column(String, nullable=True)  # "off", "low", "medium", "high"

    @property
    def llm_api_key(self) -> str | None:
        if not self._llm_api_key_encrypted:
            return None
        return decrypt(self._llm_api_key_encrypted)

    @llm_api_key.setter
    def llm_api_key(self, value: str | None) -> None:
        self._llm_api_key_encrypted = encrypt(value) if value else None

    # Texte source (pitch ou synopsis)
    source_text = Column(Text, nullable=True)

    # Configuration narrative
    target_chapter_count = Column(Integer, nullable=True)
    writing_style = Column(Text, nullable=True)       # Règles d'écriture
    tone_keywords = Column(JSON, default=list)         # ["sombre", "épique", ...]
    language = Column(String, default="fr")

    # Seuils de validation
    min_validation_score = Column(Float, default=7.0)
    max_revision_attempts = Column(Integer, default=5)

    # Chemin vers le dossier du projet (lorebook + chapitres)
    project_dir = Column(String, nullable=False)

    # Relations
    chapters = relationship("Chapter", back_populates="project", cascade="all, delete-orphan")
    agent_logs = relationship("AgentLog", back_populates="project", cascade="all, delete-orphan")


class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)

    number = Column(Integer, nullable=False)       # Ordre dans le livre
    title = Column(String, nullable=True)
    state = Column(String, nullable=False, default="pending")

    revision_count = Column(Integer, default=0)
    last_score = Column(Float, nullable=True)       # Dernière note du critique
    last_critic_comments = Column(JSON, default=list)

    # Chemins vers les fichiers markdown
    brief_path = Column(String, nullable=True)      # Fiche chapitre
    content_path = Column(String, nullable=True)    # Chapitre rédigé

    # Configuration narrative spécifique au chapitre (surcharge le projet)
    tone_override = Column(JSON, nullable=True)     # Tons spécifiques à ce chapitre

    # Contrôle utilisateur
    is_user_controlled = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    project = relationship("Project", back_populates="chapters")
    state_history = relationship("ChapterStateHistory", back_populates="chapter", cascade="all, delete-orphan")


class ChapterStateHistory(Base):
    """Historique complet des changements d'état d'un chapitre."""
    __tablename__ = "chapter_state_history"

    id = Column(String, primary_key=True, default=_uuid)
    chapter_id = Column(String, ForeignKey("chapters.id"), nullable=False)
    old_state = Column(String, nullable=False)
    new_state = Column(String, nullable=False)
    changed_by = Column(String, nullable=False)   # agent_name ou "user"
    note = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    chapter = relationship("Chapter", back_populates="state_history")


class AgentLog(Base):
    """Log de chaque appel agent avec sa consommation LLM."""
    __tablename__ = "agent_logs"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    chapter_id = Column(String, nullable=True)

    agent_name = Column(String, nullable=False)
    status = Column(String, nullable=False)       # "success", "error", "skipped"
    error_message = Column(Text, nullable=True)

    # Consommation LLM
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="agent_logs")


class LorebookEntry(Base):
    """
    Index des entrées du lorebook pour permettre la recherche et l'historique.
    Le contenu réel reste dans les fichiers markdown.
    """
    __tablename__ = "lorebook_entries"

    id = Column(String, primary_key=True, default=_uuid)
    project_id = Column(String, nullable=False)

    entity_type = Column(String, nullable=False)  # "character", "place", "lore", ...
    entity_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_modified_by = Column(String, nullable=True)   # agent_name ou "user"
