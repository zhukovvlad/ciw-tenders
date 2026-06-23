from __future__ import annotations

from app.domain.entities import (
    EstimateNode,
    EstimateRowStatus,
    MatchCandidate,
    NewEstimate,
    NodeMatch,
)
from tests.fakes import FakeEstimateRepository


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
