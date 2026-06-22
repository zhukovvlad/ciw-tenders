"""estimates + estimate_rows

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE estimates (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            filename            TEXT NOT NULL,
            original_object_key TEXT NOT NULL,
            status              VARCHAR(32) NOT NULL DEFAULT 'pending',
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX idx_estimates_user_id ON estimates (user_id)")
    op.execute(
        """
        CREATE TABLE estimate_rows (
            id              SERIAL PRIMARY KEY,
            estimate_id     INTEGER NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
            source_index    INTEGER NOT NULL,
            code            VARCHAR(64) NOT NULL,
            name            TEXT NOT NULL,
            parent_code     VARCHAR(64),
            section_type    VARCHAR(32),
            depth           INTEGER NOT NULL,
            embedding_input TEXT NOT NULL,
            embedding       VECTOR(768),
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            CONSTRAINT uq_estimate_rows_estimate_source UNIQUE (estimate_id, source_index)
        )
        """
    )
    op.execute("CREATE INDEX idx_estimate_rows_estimate_id ON estimate_rows (estimate_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS estimate_rows")
    op.execute("DROP TABLE IF EXISTS estimates")
