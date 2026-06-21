"""add embedding_input to template_articles

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default='' нужен только чтобы пройти NOT NULL на возможных легаси-строках;
    # на практике таблица пуста. После добавления дефолт снимаем.
    op.add_column(
        "template_articles",
        sa.Column("embedding_input", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("template_articles", "embedding_input", server_default=None)


def downgrade() -> None:
    op.drop_column("template_articles", "embedding_input")
