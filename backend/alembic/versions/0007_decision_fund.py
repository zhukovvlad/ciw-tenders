"""decision fund table + estimates.is_reference

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimates",
        sa.Column("is_reference", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "decision_fund",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cache_key_hash", sa.String(64), nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("crumb_version", sa.SmallInteger(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),  # без FK — снимок переживает churn
        sa.Column("votes", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "origin", sa.String(16), nullable=False, server_default=sa.text("'human_review'")
        ),
        sa.Column("source_estimate_id", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "cache_key_hash", "crumb_version", "article_id",
            name="uq_decision_fund_key_version_article",
        ),
    )
    op.create_index("ix_decision_fund_lookup", "decision_fund", ["cache_key_hash", "crumb_version"])


def downgrade() -> None:
    op.drop_index("ix_decision_fund_lookup", table_name="decision_fund")
    op.drop_table("decision_fund")
    op.drop_column("estimates", "is_reference")
