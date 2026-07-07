"""estimates.status_code — машинный код статуса матчинга (этап 4, PR-1).

Nullable: старые сметы остаются с NULL → фронт показывает сырой status_detail (фолбэк).
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE estimates ADD COLUMN status_code TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE estimates DROP COLUMN IF EXISTS status_code")
