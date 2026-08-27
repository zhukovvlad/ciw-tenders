"""Тесты сущностей tree-движка (доменный слой)."""

from __future__ import annotations

from app.domain.decision_fund import FUND_KEY_VERSION, fund_key_v3
from app.domain.entities import (
    AncestorContext,
    CatalogArticle,
    MatchCandidate,
    NodeVerdict,
    SectionMatchRequest,
)
from app.domain.tree_matching import (
    effective_ancestor_context,
    estimate_tokens,
    resolve_parents,
)
from tests.fakes import make_tree_node as _tn


def test_tree_entities_construct() -> None:
    n = _tn(1, 1, "1")
    ctx = AncestorContext(trusted_code=None, has_uncertain_barrier=False)
    v = NodeVerdict(node_id=1, kind="article", article_code="1", sure=True, alt_code=None)
    req = SectionMatchRequest(
        nodes=[n], ancestors=[], hints={}, targets=frozenset({1}),
        catalog=[CatalogArticle(1, "1", "Раздел", None)], precedents=[])
    assert req.targets == {1} and v.kind == "article" and ctx.trusted_code is None


def test_match_candidate_score_nullable() -> None:
    assert MatchCandidate(id=1, code="1", name="x", score=None).score is None


def test_resolve_parents_positional_not_by_code() -> None:
    # коды повторяются между этапами: второй «6.2» — ребёнок второго «6», не первого
    nodes = [
        _tn(1, 1, "6"), _tn(2, 2, "6.2"), _tn(3, 1, "6"), _tn(4, 2, "6.2"), _tn(5, 4, "6.2.1.1"),
    ]
    assert resolve_parents(nodes) == [None, 0, None, 2, 3]  # скачок глубины 2→4: ближайший открытый


def test_context_trusted_stops_at_reviewed_or_confident() -> None:
    nodes = [
        _tn(1, 1, "4", status="confident", matched_code="4"),
        _tn(2, 2, "4.1", status="needs_review", matched_code="4.9"),
        _tn(3, 3, "4.1.1"),
    ]
    p = resolve_parents(nodes)
    # A→B(needs_review)→C
    assert effective_ancestor_context(2, nodes, p) == AncestorContext("4", True)
    nodes2 = [_tn(1, 1, "4", status="needs_review", matched_code="4",
                  review_status="overridden", final_code="5"), _tn(2, 2, "4.1")]
    ctx2 = effective_ancestor_context(1, nodes2, resolve_parents(nodes2))
    assert ctx2 == AncestorContext("5", False)


def test_context_transparent_statuses_and_root() -> None:
    nodes = [
        _tn(1, 1, "1", status="excluded"), _tn(2, 2, "1.1", status="no_match"), _tn(3, 3, "1.1.1"),
    ]
    p = resolve_parents(nodes)
    # корень — доверенная база
    assert effective_ancestor_context(2, nodes, p) == AncestorContext(None, False)
    assert effective_ancestor_context(0, nodes, p) == AncestorContext(None, False)


def test_fund_key_v3_uses_trusted_code_and_none_on_barrier() -> None:
    n = _tn(1, 2, "1.1", name="  Прочее ")
    assert fund_key_v3(n, AncestorContext("4.2", False)) == "прочее\x1f4.2"
    assert fund_key_v3(n, AncestorContext(None, False)) == "прочее\x1f"
    assert fund_key_v3(n, AncestorContext("4.2", True)) is None
    assert FUND_KEY_VERSION == 3


def test_estimate_tokens_ceil_div_3() -> None:
    assert estimate_tokens("") == 0 and estimate_tokens("ab") == 1 and estimate_tokens("abcd") == 2
