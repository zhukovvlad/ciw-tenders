"""Тесты сущностей tree-движка (доменный слой)."""

from __future__ import annotations

from app.domain.entities import (
    AncestorContext,
    CatalogArticle,
    MatchCandidate,
    NodeVerdict,
    SectionMatchRequest,
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
