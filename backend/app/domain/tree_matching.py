"""Чистая логика tree-движка сопоставления (спека 2026-08-27 §3.3). Без I/O."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.classification import resolve_ancestor_indices
from app.domain.entities import AncestorContext, TreeNode

TRUSTED_STATUSES = ("confident", "matched_fund")
REVIEWED_STATUSES = ("confirmed", "overridden")
UNCERTAIN_STATUSES = ("needs_review",)


def resolve_parents(nodes: Sequence[TreeNode]) -> list[int | None]:
    """Индекс родителя для каждого узла — позиционно по depth (коды повторяются между этапами)."""
    chains = resolve_ancestor_indices([n.depth for n in nodes])
    return [chain[-1] if chain else None for chain in chains]


def effective_ancestor_context(
    idx: int, nodes: Sequence[TreeNode], parents: Sequence[int | None]
) -> AncestorContext:
    """Ближайший ДОВЕРЕННЫЙ предок и наличие барьера needs_review на пути к нему."""
    barrier = False
    p = parents[idx]
    while p is not None:
        anc = nodes[p]
        if anc.review_status in REVIEWED_STATUSES and anc.final_code:
            return AncestorContext(anc.final_code, barrier)
        if (
            anc.status in TRUSTED_STATUSES
            and anc.review_status == "unreviewed"
            and anc.matched_code
        ):
            return AncestorContext(anc.matched_code, barrier)
        if anc.status in UNCERTAIN_STATUSES:
            barrier = True
        p = parents[p]
    return AncestorContext(None, barrier)


def estimate_tokens(text: str) -> int:
    """Консервативная оценка токенов для кириллицы (замер спайка: 6.0k оценка vs 5.6k факт)."""
    return math.ceil(len(text) / 3)
