"""add api_keys table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-13
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id VARCHAR NOT NULL PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id),
            label VARCHAR NOT NULL,
            provider VARCHAR NOT NULL,
            key_encrypted VARCHAR NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_user_id ON api_keys (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_keys")
