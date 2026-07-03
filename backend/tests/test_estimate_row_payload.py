from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas import EstimateDetailOut, EstimateRowOut
from app.domain.entities import Estimate, MatchCandidate, StoredEstimateRow


def _row(**overrides: object) -> StoredEstimateRow:
    fields: dict = {
        "id": 7, "code": "2.4.2", "name": "Устройство приямков",
        "parent_code": "2.4", "section_type": None, "depth": 3,
        "embedding_input": "Конструктив. Подземная часть. Устройство приямков",
        "source_index": 12, "status": "error",
    }
    fields.update(overrides)
    return StoredEstimateRow(**fields)


def _estimate(rows: list[StoredEstimateRow]) -> Estimate:
    return Estimate(
        id=1, user_id=1, filename="t.xlsx", status="ready",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), rows=rows,
    )


def test_row_out_carries_source_index_and_match_error() -> None:
    out = EstimateRowOut.from_entity(_row(match_error="таймаут LLM-арбитра"))
    assert out.source_index == 12
    assert out.match_error == "таймаут LLM-арбитра"


def test_match_error_defaults_to_none() -> None:
    assert EstimateRowOut.from_entity(_row()).match_error is None


def test_detail_rows_get_full_breadcrumb() -> None:
    rows = [
        _row(id=1, code="2", name="Конструктив", depth=1, source_index=0,
             status="excluded"),
        _row(id=2, code="2.4", name="Подземная часть", depth=2, source_index=1,
             status="confident"),
        _row(id=3, code="2.4.2", name="Приямки", depth=3, source_index=2,
             status="needs_review"),
    ]
    out = EstimateDetailOut.from_entity(_estimate(rows))
    by_id = {r.id: r for r in out.rows}
    # ПОЛНАЯ цепочка: excluded-предок «Конструктив» ВКЛЮЧЁН (UI-крошка ≠ вход эмбеддера)
    assert by_id[3].breadcrumb == ["Конструктив", "Подземная часть"]
    assert by_id[1].breadcrumb == []


def test_candidate_matched_and_final_breadcrumbs_from_article_crumbs() -> None:
    row = _row(
        id=5, code="1.1", name="Работа", depth=2, source_index=1,
        status="needs_review", matched_article_id=3,
        final_article_id=9,  # выбор оператора ЧЕРЕЗ ПОИСК — статьи нет в кандидатах
        candidates=[MatchCandidate(id=3, code="03.04", name="Фунд. под обор.", score=0.7)],
    )
    root = _row(id=4, code="1", name="Раздел", depth=1, source_index=0,
                status="confident")
    crumbs = {3: ["03 Фундаменты и основания"], 9: ["08 Отделочные работы"]}
    out = EstimateDetailOut.from_entity(_estimate([root, row]), article_crumbs=crumbs)
    target = next(r for r in out.rows if r.id == 5)
    assert target.matched_breadcrumb == ["03 Фундаменты и основания"]
    assert target.candidates[0].breadcrumb == ["03 Фундаменты и основания"]
    assert target.final_breadcrumb == ["08 Отделочные работы"]


def test_row_out_without_maps_defaults_to_empty() -> None:
    out = EstimateRowOut.from_entity(_row())
    assert out.breadcrumb == [] and out.matched_breadcrumb == []


def test_candidate_without_id_gets_no_breadcrumb() -> None:
    # спека §4: «крошка кандидата без id» — id=None не должен уходить в
    # crumbs.get(None, ...) (случайное совпадение по ключу None), только [].
    row = _row(
        id=6, code="1.2", name="Работа", depth=2, source_index=1,
        status="needs_review",
        candidates=[MatchCandidate(id=None, code="X", name="Y", score=0.5)],
    )
    crumbs = {3: ["03 Фундаменты и основания"]}
    out = EstimateRowOut.from_entity(row, article_crumbs=crumbs)
    assert out.candidates[0].breadcrumb == []
