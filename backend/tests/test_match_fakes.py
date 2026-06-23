from __future__ import annotations

from app.domain.entities import EstimateNode, EstimateRowStatus, NewEstimate, NodeMatch
from tests.fakes import FakeEstimateRepository, FakeTaskQueue


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, 1)


def test_lock_is_exclusive_and_releasable() -> None:
    repo = FakeEstimateRepository()
    assert repo.try_matching_lock(1) is True
    assert repo.try_matching_lock(1) is False
    repo.release_matching_lock(1)
    assert repo.try_matching_lock(1) is True


def test_embed_keyset_and_cas_and_matchable_filter() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    ids = sorted(n["id"] for n in repo.nodes.values())
    first = repo.fetch_unembedded_nodes(est.id, after_id=0, limit=1)
    assert len(first) == 1 and first[0].id == ids[0]
    # keyset вперёд — тот же id не вернётся
    assert repo.fetch_unembedded_nodes(est.id, after_id=ids[0], limit=10)[0].id == ids[1]
    # CAS-False на чужой embedding_input
    assert repo.save_node_embedding(ids[0], "не тот", [0.1]) is False
    assert repo.save_node_embedding(ids[0], "ei 1", [0.1]) is True
    # matchable требует embedding IS NOT NULL
    assert [m.id for m in repo.fetch_matchable_nodes(est.id)] == [ids[0]]


def test_save_match_and_counts_clear_error() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    nid = next(iter(repo.nodes))
    repo.save_node_match(nid, NodeMatch(EstimateRowStatus.ERROR, match_error="boom"))
    assert repo.count_node_errors(est.id) == 1
    repo.save_node_match(nid, NodeMatch(EstimateRowStatus.CONFIDENT, 1, "1", "x", 0.95))
    assert repo.count_node_errors(est.id) == 0 and repo.nodes[nid]["match_error"] is None


def test_set_status_and_touch_bump_heartbeat() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    before = repo.touch_count[est.id]
    repo.touch(est.id)
    repo.set_status(est.id, "running")
    assert repo.touch_count[est.id] == before + 2 and repo.get_status(est.id) == "running"


def test_task_queue_records() -> None:
    q = FakeTaskQueue()
    q.enqueue_match(7)
    q.enqueue_articles_embed()
    assert q.match_calls == [7] and q.articles_embed_calls == 1
