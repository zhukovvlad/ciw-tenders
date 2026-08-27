"""Чистая логика tree-движка сопоставления (спека 2026-08-27 §3.3). Без I/O."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.domain.classification import resolve_ancestor_indices
from app.domain.entities import AncestorContext, TreeNode

TRUSTED_STATUSES = ("confident", "matched_fund")
REVIEWED_STATUSES = ("confirmed", "overridden")
UNCERTAIN_STATUSES = ("needs_review",)

ROW_TOO_LARGE = "tree_row_too_large"


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


@dataclass(frozen=True, slots=True)
class Chunk:
    """Один запрос к LLM: корень поддерева + непрерывный список потомков (спека §3.3)."""

    root: int
    indices: list[int]
    oversized: list[int] = field(default_factory=list)  # узлы больше бюджета сами по себе → error


def _children(parents: Sequence[int | None], idx: int) -> list[int]:
    """Индексы прямых детей узла `idx` (позиционно, по `parents` из `resolve_parents`)."""
    return [i for i, p in enumerate(parents) if p == idx]


def _is_descendant(parents: Sequence[int | None], i: int, root: int) -> bool:
    """Является ли узел `i` потомком `root` (проверка по цепочке родителей)."""
    p = parents[i]
    while p is not None:
        if p == root:
            return True
        p = parents[p]
    return False


def _subtree(parents: Sequence[int | None], root: int, n: int) -> list[int]:
    """Индексы поддерева `root`: сам узел + непрерывный (по документу) диапазон потомков.

    Документ упорядочен обходом в глубину, поэтому поддерево — это всегда непрерывный
    диапазон индексов сразу после `root`; как только встретился первый узел вне поддерева,
    дальше потомков уже быть не может — можно останавливаться.
    """
    out = [root]
    for i in range(root + 1, n):
        if _is_descendant(parents, i, root):
            out.append(i)
        else:
            break
    return out


def split_sections(
    nodes: Sequence[TreeNode],
    parents: Sequence[int | None],
    *,
    max_rows: int,
    budget_tokens: int,
    row_tokens: Callable[[TreeNode], int],
) -> list[Chunk]:
    """Рекурсивное деление по разделам (спека §3.3): родительский чанк всегда раньше дочернего."""
    out: list[Chunk] = []
    n = len(nodes)

    def fits(idxs: list[int]) -> bool:
        return len(idxs) <= max_rows and sum(row_tokens(nodes[i]) for i in idxs) <= budget_tokens

    def split(root: int) -> None:
        sub = _subtree(parents, root, n)
        if fits(sub):
            out.append(Chunk(root=root, indices=sub))
            return
        head = [root]
        oversized = [root] if row_tokens(nodes[root]) > budget_tokens else []
        deferred: list[int] = []
        for child in _children(parents, root):
            child_sub = _subtree(parents, child, n)
            if not deferred and fits(head + child_sub):
                head = head + child_sub
            else:
                deferred.append(child)
        out.append(Chunk(root=root, indices=head, oversized=oversized))
        for child in deferred:
            split(child)

    for root in (i for i, p in enumerate(parents) if p is None):
        split(root)
    return out
