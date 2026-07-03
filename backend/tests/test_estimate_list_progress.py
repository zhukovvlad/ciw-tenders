"""Пагинация GET /estimates и счётчики прогресса (этап 1 UX-роадмапа)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import EstimateSummaryOut
from app.domain.entities import EstimateSummary

_TS = datetime(2026, 7, 2, tzinfo=UTC)


def test_summary_out_carries_progress() -> None:
    s = EstimateSummary(
        id=1, filename="a.xlsx", status="ready", nodes_count=10,
        created_at=_TS, reviewed_count=4, total_reviewable=7,
    )
    out = EstimateSummaryOut.from_entity(s)
    assert (out.reviewed_count, out.total_reviewable) == (4, 7)


def test_list_route_paginates(client_with_three_estimates) -> None:
    client = client_with_three_estimates
    resp = client.get("/api/estimates", params={"limit": 2, "offset": 0})
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_list_route_default_shape(client_with_three_estimates) -> None:
    body = client_with_three_estimates.get("/api/estimates").json()
    assert set(body.keys()) == {"items", "total"}


def test_reviewable_partition_covers_all_statuses() -> None:
    """Ломается громко при добавлении статуса строки: новый статус обязан быть
    явно отнесён к «требует решения» / «решено без оператора» / «вне ревью» —
    и синхронизирован с фронтовым requiresDecision (reviewState.ts)."""
    from app.domain.entities import EstimateRowStatus
    from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository

    reviewable = set(SqlAlchemyEstimateRepository._REVIEWABLE)
    auto_decided = {"confident", "matched_fund"}
    out_of_review = {"pending", "excluded"}
    assert {s.value for s in EstimateRowStatus} == reviewable | auto_decided | out_of_review
