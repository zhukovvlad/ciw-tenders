from __future__ import annotations

from app.api.schemas import EstimateRowOut
from app.domain.entities import StoredEstimateRow


def _row(**overrides: object) -> StoredEstimateRow:
    fields: dict = {
        "id": 7, "code": "2.4.2", "name": "Устройство приямков",
        "parent_code": "2.4", "section_type": None, "depth": 3,
        "embedding_input": "Конструктив. Подземная часть. Устройство приямков",
        "source_index": 12, "status": "error",
    }
    fields.update(overrides)
    return StoredEstimateRow(**fields)


def test_row_out_carries_source_index_and_match_error() -> None:
    out = EstimateRowOut.from_entity(_row(match_error="таймаут LLM-арбитра"))
    assert out.source_index == 12
    assert out.match_error == "таймаут LLM-арбитра"


def test_match_error_defaults_to_none() -> None:
    assert EstimateRowOut.from_entity(_row()).match_error is None
