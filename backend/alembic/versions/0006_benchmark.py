"""benchmark + benchmark_node

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE benchmark (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE benchmark_node (
            id                     SERIAL PRIMARY KEY,
            benchmark_id           INTEGER NOT NULL REFERENCES benchmark (id) ON DELETE CASCADE,
            source_index           INTEGER NOT NULL,
            code                   VARCHAR(64) NOT NULL,
            name                   TEXT NOT NULL,
            expected_kind          VARCHAR(16) NOT NULL,
            expected_article_code  VARCHAR(64),
            expected_article_name  TEXT,
            CONSTRAINT benchmark_node_kind_check
                CHECK (expected_kind IN ('matchable', 'structural', 'no_article')),
            CONSTRAINT uq_benchmark_node_source
                UNIQUE (benchmark_id, source_index)
        )
        """
    )
    op.execute("CREATE INDEX idx_benchmark_node_benchmark_id ON benchmark_node (benchmark_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_node")
    op.execute("DROP TABLE IF EXISTS benchmark")
