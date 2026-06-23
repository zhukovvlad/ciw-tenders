from __future__ import annotations

from app.domain.entities import (
    EstimateRowStatus,
    EstimateStatus,
    MatchCandidate,
    NodeMatch,
)
from app.domain.errors import DictionaryNotReadyError, TransientError


def test_status_slugs() -> None:
    assert EstimateRowStatus.NEEDS_REVIEW == "needs_review"
    assert EstimateStatus.PARTIAL_ERROR == "partial_error"


def test_node_match_defaults() -> None:
    nm = NodeMatch(EstimateRowStatus.NO_MATCH)
    assert nm.score is None and nm.candidates == [] and nm.matched_id is None


def test_node_match_confident() -> None:
    c = MatchCandidate(id=5, code="1.1", name="X", score=0.95)
    nm = NodeMatch(EstimateRowStatus.CONFIDENT, 5, "1.1", "X", 0.95, [c])
    assert nm.matched_code == "1.1" and nm.candidates[0].id == 5


def test_dictionary_not_ready_carries_counts() -> None:
    e = DictionaryNotReadyError(total=10, pending=3)
    assert e.total == 10 and e.pending == 3
    assert isinstance(TransientError("x"), Exception)
