from __future__ import annotations

from app.domain.entities import StoredEstimateRow
from app.services.estimate_export_service import EstimateExportService


def _row(
    status: str,
    *,
    review_status: str = "unreviewed",
    final_code: str | None = None,
    final_name: str | None = None,
    matched_code: str | None = None,
    matched_name: str | None = None,
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
        final_name=final_name,
        matched_code=matched_code,
        matched_name=matched_name,
    )


def test_excluded_row_exports_empty_article() -> None:
    assert EstimateExportService._cell_value(_row("excluded")) == ""  # noqa: SLF001


def test_reviewed_excluded_row_still_exports_empty_article() -> None:
    # Контракт «excluded всегда пусто» держится даже если строка помечена confirmed/overridden:
    # _cell_value короткозамыкает на status='excluded' ДО ветки review_status.
    row = _row("excluded", review_status="confirmed", final_code="1.2")
    assert EstimateExportService._cell_value(row) == ""  # noqa: SLF001


def test_matched_fund_row_exports_code_and_name() -> None:
    # Фонд-строка авто-подтверждена только на фронте (review_status в БД остаётся unreviewed) —
    # экспорт обязан отдать её статью, а не пустую ячейку.
    row = _row("matched_fund", matched_code="5.1", matched_name="Кладка стен")
    assert EstimateExportService._cell_value(row) == "(5.1) Кладка стен"  # noqa: SLF001


def test_confident_row_exports_code_and_name() -> None:
    row = _row("confident", matched_code="5.1", matched_name="Кладка стен")
    assert EstimateExportService._cell_value(row) == "(5.1) Кладка стен"  # noqa: SLF001


def test_confirmed_row_exports_final_code_and_name() -> None:
    row = _row(
        "needs_review", review_status="confirmed",
        final_code="7.2", final_name="Монтаж металлоконструкций",
    )
    assert (
        EstimateExportService._cell_value(row)  # noqa: SLF001
        == "(7.2) Монтаж металлоконструкций"
    )


def test_code_without_name_exports_bare_code() -> None:
    # имя потерялось (легаси-снимок) → отдаём хотя бы код без пустых скобок
    row = _row("confident", matched_code="5.1")
    assert EstimateExportService._cell_value(row) == "5.1"  # noqa: SLF001
