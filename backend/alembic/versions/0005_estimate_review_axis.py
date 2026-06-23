"""estimate review axis columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # review_status NOT NULL DEFAULT 'unreviewed' — metadata-only на Postgres (без переписи
    # таблицы); существующие SP1/SP2-строки бэкфиллятся дефолтом.
    op.execute(
        """
        ALTER TABLE estimate_rows
            ADD COLUMN review_status   VARCHAR(32) NOT NULL DEFAULT 'unreviewed',
            ADD COLUMN final_article_id INTEGER,
            ADD COLUMN final_code       VARCHAR(64),
            ADD COLUMN final_name       TEXT,
            ADD COLUMN reviewed_at      TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE estimate_rows
            DROP COLUMN IF EXISTS review_status,
            DROP COLUMN IF EXISTS final_article_id,
            DROP COLUMN IF EXISTS final_code,
            DROP COLUMN IF EXISTS final_name,
            DROP COLUMN IF EXISTS reviewed_at
        """
    )
