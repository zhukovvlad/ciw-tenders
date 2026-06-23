"""estimate match snapshot columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE estimate_rows
            ADD COLUMN matched_article_id INTEGER,
            ADD COLUMN matched_code        VARCHAR(64),
            ADD COLUMN matched_name        TEXT,
            ADD COLUMN score               DOUBLE PRECISION,
            ADD COLUMN candidates          JSONB,
            ADD COLUMN match_error         TEXT
        """
    )
    op.execute("ALTER TABLE estimates ADD COLUMN status_detail TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE estimates DROP COLUMN IF EXISTS status_detail")
    op.execute(
        """
        ALTER TABLE estimate_rows
            DROP COLUMN IF EXISTS matched_article_id,
            DROP COLUMN IF EXISTS matched_code,
            DROP COLUMN IF EXISTS matched_name,
            DROP COLUMN IF EXISTS score,
            DROP COLUMN IF EXISTS candidates,
            DROP COLUMN IF EXISTS match_error
        """
    )
