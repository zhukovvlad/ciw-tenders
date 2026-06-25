from __future__ import annotations

from app.domain.entities import StoredEstimateRow
from app.services.estimate_export_service import EstimateExportService


def _row(status: str) -> StoredEstimateRow:
    return StoredEstimateRow(
        id=1,
        code="1",
        name="1 Этап ЖК",
        parent_code=None,
        section_type=None,
        depth=1,
        embedding_input="1 Этап ЖК",
        source_index=0,
        status=status,
    )


def test_excluded_row_exports_empty_article() -> None:
    assert EstimateExportService._cell_value(_row("excluded")) == ""  # noqa: SLF001
