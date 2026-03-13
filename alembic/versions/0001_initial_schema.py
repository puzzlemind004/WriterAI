"""initial schema complet

Revision ID: 0001
Revises:
Create Date: 2026-03-13

Crée toutes les tables from scratch — remplace les migrations fragmentées.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_email', 'users', ['email'])

    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )

    op.create_table(
        'projects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('llm_provider', sa.String(), nullable=False),
        sa.Column('llm_model', sa.String(), nullable=False),
        sa.Column('llm_api_key', sa.String(), nullable=True),
        sa.Column('llm_api_base', sa.String(), nullable=True),
        sa.Column('llm_thinking', sa.String(), nullable=True),
        sa.Column('source_text', sa.Text(), nullable=True),
        sa.Column('target_chapter_count', sa.Integer(), nullable=True),
        sa.Column('writing_style', sa.Text(), nullable=True),
        sa.Column('tone_keywords', sa.JSON(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('min_validation_score', sa.Float(), nullable=True),
        sa.Column('max_revision_attempts', sa.Integer(), nullable=True),
        sa.Column('project_dir', sa.String(), nullable=False),
        sa.Column('owner_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_projects_owner_id', 'projects', ['owner_id'])

    op.create_table(
        'chapters',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('revision_count', sa.Integer(), nullable=True),
        sa.Column('last_score', sa.Float(), nullable=True),
        sa.Column('last_critic_comments', sa.JSON(), nullable=True),
        sa.Column('brief_path', sa.String(), nullable=True),
        sa.Column('content_path', sa.String(), nullable=True),
        sa.Column('tone_override', sa.JSON(), nullable=True),
        sa.Column('is_user_controlled', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'chapter_state_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('chapter_id', sa.String(), nullable=False),
        sa.Column('old_state', sa.String(), nullable=False),
        sa.Column('new_state', sa.String(), nullable=False),
        sa.Column('changed_by', sa.String(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'agent_logs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('chapter_id', sa.String(), nullable=True),
        sa.Column('agent_name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'lorebook_entries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_name', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_modified_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('lorebook_entries')
    op.drop_table('agent_logs')
    op.drop_table('chapter_state_history')
    op.drop_table('chapters')
    op.drop_index('ix_projects_owner_id', 'projects')
    op.drop_table('projects')
    op.drop_table('refresh_tokens')
    op.drop_index('ix_users_email', 'users')
    op.drop_table('users')
