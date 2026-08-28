"""Чистая логика tree-движка сопоставления (спека 2026-08-27 §3.3). Без I/O."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace

from app.domain.classification import resolve_ancestor_indices
from app.domain.entities import (
    AncestorContext,
    CatalogArticle,
    EstimateRowStatus,
    MatchCandidate,
    NodeMatch,
    NodeVerdict,
    TreeNode,
)

logger = logging.getLogger(__name__)

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
        if anc.status in UNCERTAIN_STATUSES and anc.review_status == "unreviewed":
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


# --- Валидация вердиктов LLM и маппинг в NodeMatch (спека §3.3) ---

F_MALFORMED = "malformed"
F_INCONSISTENT = "inconsistent"
F_UNKNOWN_CODE = "unknown_code"
F_OUTSIDE_PARENT = "outside_parent"
F_MISSING = "missing"
ERR_MISSING = "tree_missing_verdict"
_KINDS = ("article", "org", "none")
Validated = tuple[NodeVerdict | None, tuple[str, ...]]


def in_subtree(code: str, anc: str) -> bool:
    """`code` совпадает с `anc` или лежит внутри его поддерева (по префиксу с точкой)."""
    return code == anc or code.startswith(anc + ".")


def hint_for(node: TreeNode) -> tuple[str, bool] | None:
    """Подсказка промпта по строке: (код, trusted). Правила доверия = effective_ancestor_context."""
    if node.review_status in REVIEWED_STATUSES and node.final_code:
        return (node.final_code, True)
    if node.review_status != "unreviewed":
        return None  # rejected: старый AI-код не показываем
    if node.status in TRUSTED_STATUSES and node.matched_code:
        return (node.matched_code, True)
    if node.status in UNCERTAIN_STATUSES and node.matched_code:
        return (node.matched_code, False)
    return None


def build_hints(
    chunk_indices: Sequence[int], nodes: Sequence[TreeNode], targets: Collection[int]
) -> dict[int, tuple[str, bool]]:
    """Подсказки промпта по всем не-целевым узлам чанка (у целей подсказок нет)."""
    hints: dict[int, tuple[str, bool]] = {}
    for i in chunk_indices:
        n = nodes[i]
        if n.id in targets:
            continue
        h = hint_for(n)
        if h is not None:
            hints[n.id] = h
    return hints


def _coerce(item: object, node_id: int) -> tuple[NodeVerdict | None, tuple[str, ...]]:
    """dict из парсера или NodeVerdict → NodeVerdict; ошибки типов → malformed."""
    if isinstance(item, NodeVerdict):
        return item, ()
    if not isinstance(item, dict):
        return None, (F_MALFORMED,)
    code = item.get("code")
    sure = item.get("sure")
    alt = item.get("alt")
    kind = item.get("kind")
    if code in ("org", "none"):
        kind, code = code, None
    elif kind is None:
        kind = "article"
    if (
        kind not in _KINDS
        or not isinstance(sure, bool)
        or not (code is None or isinstance(code, str))
        or not (alt is None or isinstance(alt, str))
    ):
        return None, (F_MALFORMED,)
    return NodeVerdict(node_id=node_id, kind=kind, article_code=code, sure=sure, alt_code=alt), ()


def validate_one(
    item: object | None, node_id: int, catalog_codes: Collection[str], ctx: AncestorContext
) -> Validated:
    """Проверяет и нормализует один сырой вердикт под контекст доверенного предка."""
    if item is None:
        return None, (F_MISSING,)
    v, flags = _coerce(item, node_id)
    if v is None:
        return None, flags
    flags_l = list(flags)
    if (v.kind == "article") != (v.article_code is not None):
        flags_l.append(F_INCONSISTENT)
    elif v.article_code is not None and v.article_code not in catalog_codes:
        flags_l.append(F_UNKNOWN_CODE)
    elif (
        v.article_code is not None
        and ctx.trusted_code is not None
        and not in_subtree(v.article_code, ctx.trusted_code)
        and not in_subtree(ctx.trusted_code, v.article_code)
    ):
        flags_l.append(F_OUTSIDE_PARENT)
    alt = v.alt_code if v.alt_code in catalog_codes and v.alt_code != v.article_code else None
    if alt != v.alt_code:
        v = replace(v, alt_code=alt)
    return v, tuple(flags_l)


def validate_verdicts(
    raw: Sequence[object],
    targets: Collection[int],
    catalog_codes: Collection[str],
    ctx_of: Callable[[int], AncestorContext],
) -> dict[int, Validated]:
    """Валидирует пачку сырых вердиктов: чужие node_id отбрасывает, дубликаты — берёт первый."""
    first: dict[int, object] = {}
    for item in raw:
        nid = (
            item.node_id
            if isinstance(item, NodeVerdict)
            else (item.get("i") if isinstance(item, dict) else None)
        )
        if not isinstance(nid, int) or nid not in targets:
            continue
        if nid in first:
            logger.warning("tree: дубликат вердикта для узла %s — взят первый", nid)
            continue
        first[nid] = item
    return {t: validate_one(first.get(t), t, catalog_codes, ctx_of(t)) for t in targets}


def children_of(catalog: Mapping[str, CatalogArticle], code: str) -> list[CatalogArticle]:
    """Прямые дети статьи `code` в каталоге."""
    return [a for a in catalog.values() if a.parent_code == code]


def _cand(a: CatalogArticle) -> MatchCandidate:
    return MatchCandidate(id=a.id, code=a.code, name=a.name, score=None)


def neighbors(
    catalog: Mapping[str, CatalogArticle], code: str, alt_code: str | None, limit: int
) -> list[MatchCandidate]:
    """Структурные кандидаты вокруг выбранного кода: он сам, альтернатива, сёстры, родитель."""
    chosen = catalog[code]
    order: list[CatalogArticle] = [chosen]
    if alt_code and alt_code in catalog:
        order.append(catalog[alt_code])
    if chosen.parent_code:
        order += [s for s in children_of(catalog, chosen.parent_code) if s not in order]
        if chosen.parent_code in catalog:
            order.append(catalog[chosen.parent_code])
    seen: set[str] = set()
    out = []
    for a in order:
        if a.code not in seen:
            seen.add(a.code)
            out.append(_cand(a))
    return out[:limit]


def to_node_match(
    v: Validated,
    ctx: AncestorContext,
    catalog: Mapping[str, CatalogArticle],
    *,
    candidates_limit: int = 5,
) -> NodeMatch:
    """Маппинг валидированного вердикта в снимок NodeMatch (fail-closed на ошибках)."""
    verdict, flags = v
    if F_MISSING in flags:
        return NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_MISSING)
    bad = F_MALFORMED in flags or F_INCONSISTENT in flags or F_UNKNOWN_CODE in flags
    if verdict is None or bad:
        cands = []
        if ctx.trusted_code and ctx.trusted_code in catalog:
            cands = [_cand(catalog[ctx.trusted_code])] + [
                _cand(a) for a in children_of(catalog, ctx.trusted_code)
            ]
        return NodeMatch(EstimateRowStatus.NEEDS_REVIEW, candidates=cands[:candidates_limit])
    if verdict.kind == "org":
        return NodeMatch(EstimateRowStatus.EXCLUDED)
    if verdict.kind == "none":
        return NodeMatch(EstimateRowStatus.NO_MATCH)
    art = catalog[verdict.article_code]  # type: ignore[index]  # unknown_code отсечён выше
    cands = neighbors(catalog, art.code, verdict.alt_code, candidates_limit)
    status = (
        EstimateRowStatus.CONFIDENT
        if verdict.sure and not flags and not ctx.has_uncertain_barrier
        else EstimateRowStatus.NEEDS_REVIEW
    )
    return NodeMatch(
        status,
        matched_id=art.id,
        matched_code=art.code,
        matched_name=art.name,
        score=None,
        candidates=cands,
    )
