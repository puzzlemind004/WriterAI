"""initial schema complet

Revision ID: 0001
Revises:
Create Date: 2026-03-13

Crée toutes les tables from scratch — idempotent grâce à IF NOT EXISTS.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR NOT NULL PRIMARY KEY,
            email VARCHAR NOT NULL UNIQUE,
            hashed_password VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id VARCHAR NOT NULL PRIMARY KEY,
            token_hash VARCHAR NOT NULL UNIQUE,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE,
            user_agent VARCHAR
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id VARCHAR NOT NULL PRIMARY KEY,
            name VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE,
            llm_provider VARCHAR NOT NULL,
            llm_model VARCHAR NOT NULL,
            llm_api_key VARCHAR,
            llm_api_base VARCHAR,
            llm_thinking VARCHAR,
            source_text TEXT,
            target_chapter_count INTEGER,
            writing_style TEXT,
            tone_keywords JSON,
            language VARCHAR DEFAULT 'fr',
            min_validation_score FLOAT DEFAULT 7.0,
            max_revision_attempts INTEGER DEFAULT 5,
            project_dir VARCHAR NOT NULL,
            owner_id VARCHAR NOT NULL REFERENCES users(id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_projects_owner_id ON projects (owner_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS chapters (
            id VARCHAR NOT NULL PRIMARY KEY,
            project_id VARCHAR NOT NULL REFERENCES projects(id),
            number INTEGER NOT NULL,
            title VARCHAR,
            state VARCHAR NOT NULL DEFAULT 'pending',
            revision_count INTEGER DEFAULT 0,
            last_score FLOAT,
            last_critic_comments JSON,
            brief_path VARCHAR,
            content_path VARCHAR,
            tone_override JSON,
            is_user_controlled BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS chapter_state_history (
            id VARCHAR NOT NULL PRIMARY KEY,
            chapter_id VARCHAR NOT NULL REFERENCES chapters(id),
            old_state VARCHAR NOT NULL,
            new_state VARCHAR NOT NULL,
            changed_by VARCHAR NOT NULL,
            note TEXT,
            timestamp TIMESTAMP WITH TIME ZONE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS agent_logs (
            id VARCHAR NOT NULL PRIMARY KEY,
            project_id VARCHAR NOT NULL REFERENCES projects(id),
            chapter_id VARCHAR,
            agent_name VARCHAR NOT NULL,
            status VARCHAR NOT NULL,
            error_message TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_usd FLOAT,
            duration_seconds FLOAT,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS lorebook_entries (
            id VARCHAR NOT NULL PRIMARY KEY,
            project_id VARCHAR NOT NULL,
            entity_type VARCHAR NOT NULL,
            entity_name VARCHAR NOT NULL,
            file_path VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE,
            last_modified_by VARCHAR
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lorebook_entries")
    op.execute("DROP TABLE IF EXISTS agent_logs")
    op.execute("DROP TABLE IF EXISTS chapter_state_history")
    op.execute("DROP TABLE IF EXISTS chapters")
    op.execute("DROP TABLE IF EXISTS projects")
    op.execute("DROP TABLE IF EXISTS refresh_tokens")
    op.execute("DROP TABLE IF EXISTS users")
