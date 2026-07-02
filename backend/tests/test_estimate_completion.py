"""Тесты жизненного цикла завершения сметы (этап 1 UX-роадмапа)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import EstimateDetailOut, EstimateSummaryOut
from app.domain.entities import Estimate, EstimateSummary

_TS = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def test_detail_out_carries_completed_at() -> None:
    est = Estimate(
        id=1, user_id=1, filename="a.xlsx", status="ready",
        created_at=_TS, completed_at=_TS,
    )
    out = EstimateDetailOut.from_entity(est)
    assert out.completed_at == _TS


def test_detail_out_completed_at_defaults_none() -> None:
    est = Estimate(id=1, user_id=1, filename="a.xlsx", status="ready", created_at=_TS)
    assert EstimateDetailOut.from_entity(est).completed_at is None


def test_summary_out_carries_completed_at() -> None:
    s = EstimateSummary(
        id=1, filename="a.xlsx", status="ready", nodes_count=3,
        created_at=_TS, completed_at=_TS,
    )
    assert EstimateSummaryOut.from_entity(s).completed_at == _TS
