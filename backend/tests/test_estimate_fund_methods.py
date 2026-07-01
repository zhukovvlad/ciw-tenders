"""Task 4: методы EstimateRepository для золотого фонда — тесты на FakeEstimateRepository.

Фейк = зеркало SQL-контракта (см. tests/test_estimate_repo_cas.py): CAS по review_status
проверяется через фейк ровно как для save_node_match. Реальный SQL (estimate_repository.py)
дословно из брифа, отдельным интеграционным тестом не покрывается (см. task-4-brief.md).
"""

from __future__ import annotations

from tests.fakes import FakeEstimateRepository, Row, seed_estimate_with_rows


def test_save_fund_hit_writes_snapshot() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo, [Row(embedding_input="к. лист", status="pending", review_status="unreviewed")]
    )
    rid = next(n["id"] for n in repo.nodes.values() if n["estimate_id"] == eid)

    repo.save_fund_hit(rid, article_id=5, code="1.4", name="Мокап")

    node = repo.nodes[rid]
    assert node["status"] == "matched_fund"
    assert node["matched_article_id"] == 5
    assert node["matched_code"] == "1.4"
    assert node["matched_name"] == "Мокап"
    assert node["candidates"] == []
    assert node["score"] is None


def test_save_fund_hit_cas_skips_reviewed() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo, [Row(embedding_input="x", status="pending", review_status="confirmed")]
    )
    rid = next(n["id"] for n in repo.nodes.values() if n["estimate_id"] == eid)

    repo.save_fund_hit(rid, article_id=5, code="1.4", name="Мокап")

    assert repo.nodes[rid]["status"] != "matched_fund"  # CAS по unreviewed не дал перезаписать


def test_fetch_pending_nodes_only_pending_unreviewed() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo,
        [
            Row(embedding_input="a", status="pending", review_status="unreviewed"),
            Row(embedding_input="b", status="confident", review_status="unreviewed"),
            Row(embedding_input="c", status="pending", review_status="confirmed"),
        ],
    )

    pending = repo.fetch_pending_nodes(eid)

    assert [p.embedding_input for p in pending] == ["a"]


def test_set_reference_and_fetch_ids() -> None:
    repo = FakeEstimateRepository()
    e1 = seed_estimate_with_rows(repo, [Row("a", "pending", "unreviewed")])
    e2 = seed_estimate_with_rows(repo, [Row("b", "pending", "unreviewed")])

    repo.set_reference(e1, True)
    repo.set_reference(e2, False)

    assert repo.fetch_reference_estimate_ids() == [e1]
    assert repo.is_reference(e1) is True
    assert repo.is_reference(e2) is False


def test_fetch_promotable_rows_returns_all_with_fields() -> None:
    repo = FakeEstimateRepository()
    eid = seed_estimate_with_rows(
        repo,
        [
            Row("a", "needs_review", "confirmed", final_article_id=5),
            Row("b", "pending", "unreviewed"),
        ],
    )

    rows = repo.fetch_promotable_rows(eid)

    assert len(rows) == 2
    by_input = {r.embedding_input: r for r in rows}
    assert by_input["a"].status == "needs_review"
    assert by_input["a"].review_status == "confirmed"
    assert by_input["a"].final_article_id == 5
    assert by_input["b"].final_article_id is None
