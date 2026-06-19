"""Тест парсера Excel (Шаг 3.1): фильтрация строк по 'Вид раздела' == 'СМР'."""

from __future__ import annotations

import io

import pandas as pd

from app.services.excel_parser import ExcelEstimateParser


def _make_xlsx() -> bytes:
    df = pd.DataFrame(
        {
            "Вид раздела": ["СМР", "Материалы", "СМР", "Оборудование"],
            "Наименование": [
                "Устройство фундамента",
                "Цемент М500",
                "Кладка стен",
                "Насос",
            ],
        }
    )
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


def test_parser_keeps_only_smr_rows() -> None:
    rows = ExcelEstimateParser().parse(_make_xlsx())

    names = [r.name for r in rows]
    assert names == ["Устройство фундамента", "Кладка стен"]


def test_parser_raises_on_missing_columns() -> None:
    df = pd.DataFrame({"Колонка": [1, 2]})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")

    try:
        ExcelEstimateParser().parse(buffer.getvalue())
        raise AssertionError("Ожидалась ошибка о недостающих колонках")
    except ValueError as exc:
        assert "Вид раздела" in str(exc)
