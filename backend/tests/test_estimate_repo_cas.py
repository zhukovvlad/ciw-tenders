from __future__ import annotations

import itertools

from app.domain.entities import (
    EstimateNode,
    EstimateRowStatus,
    MatchCandidate,
    NewEstimate,
    NodeMatch,
)
from tests.fakes import FakeEstimateRepository

# Счётчик source_index через тест-файл: fetch_tree/tree-движок зависят от truthful
# позиции узла, а не только от порядка в списке nodes — _node должен воспроизводить это.
_source_index_seq = itertools.count()


def _node(code: str) -> EstimateNode:
    """Узел для tree-тестов: depth = число сегментов кода, source_index — по порядку."""
    return EstimateNode(
        code=code, name=f"Узел {code}", parent_code=None, section_type="СМР",
        embedding_input=code, source_index=next(_source_index_seq), depth=code.count(".") + 1,
    )


def _seed_one_matchable() -> tuple[FakeEstimateRepository, int]:
    repo = FakeEstimateRepository()
    node = EstimateNode(
        code="1", name="Узел", parent_code=None, section_type="СМР",
        embedding_input="узел", source_index=0, depth=0,
    )
    est = repo.create(NewEstimate(1, "f.xlsx", "key"), [node])
    nid = est.rows[0].id
    repo.nodes[nid]["embedding"] = [0.1]
    repo.nodes[nid]["status"] = "no_match"
    return repo, nid


def test_save_node_match_skips_reviewed_row() -> None:
    repo, nid = _seed_one_matchable()
    repo.nodes[nid]["review_status"] = "overridden"  # человек уже тронул
    result = NodeMatch(
        EstimateRowStatus.CONFIDENT, matched_id=7, matched_code="2.1",
        matched_name="Статья", score=0.95,
        candidates=[MatchCandidate(7, "2.1", "Статья", 0.95)],
    )
    repo.save_node_match(nid, result)
    assert repo.nodes[nid]["status"] == "no_match"  # не затёрто
    assert repo.nodes[nid]["matched_code"] is None


def test_fetch_matchable_excludes_reviewed() -> None:
    repo, nid = _seed_one_matchable()
    assert [n.id for n in repo.fetch_matchable_nodes(1)] == [nid]
    repo.nodes[nid]["review_status"] = "rejected"
    assert repo.fetch_matchable_nodes(1) == []


def test_save_node_match_cas_requires_expected_status_and_unreviewed() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    n1, n2 = (r.id for r in est.rows)
    res = NodeMatch(EstimateRowStatus.CONFIDENT, matched_id=1, matched_code="1", matched_name="x")
    assert repo.save_node_match_cas(n1, res, ("pending",)) is True
    assert repo.save_node_match_cas(n1, res, ("pending",)) is False       # уже confident
    assert repo.save_node_match_cas(n1, res, ("pending", "confident")) is True
    repo.save_review_decision(
        n2, review_status="confirmed", final_article_id=1, final_code="1", final_name="x"
    )
    assert repo.save_node_match_cas(n2, res, ("pending",)) is False       # ревью


def test_fetch_tree_and_refresh() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    tree = repo.fetch_tree(est.id)
    assert [t.code for t in tree] == ["1", "1.1"] and tree[0].depth == 1 and tree[1].depth == 2
    repo.save_review_decision(
        tree[1].id, review_status="overridden", final_article_id=7, final_code="7", final_name="z"
    )
    fresh = repo.refresh_tree_node(tree[1].id)
    assert fresh.final_code == "7" and fresh.final_article_id == 7
    assert fresh.review_status == "overridden"
