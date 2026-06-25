from __future__ import annotations

from app.domain.entities import StoredEstimateRow
from app.services.estimate_export_service import EstimateExportService


def _row(
    status: str,
    *,
    review_status: str = "unreviewed",
    final_code: str | None = None,
) -> StoredEstimateRow:
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
        review_status=review_status,
        final_code=final_code,
    )


def test_excluded_row_exports_empty_article() -> None:
    assert EstimateExportService._cell_value(_row("excluded")) == ""  # noqa: SLF001


def test_reviewed_excluded_row_still_exports_empty_article() -> None:
    # Контракт «excluded всегда пусто» держится даже если строка помечена confirmed/overridden:
    # _cell_value короткозамыкает на status='excluded' ДО ветки review_status.
    row = _row("excluded", review_status="confirmed", final_code="1.2")
    assert EstimateExportService._cell_value(row) == ""  # noqa: SLF001
