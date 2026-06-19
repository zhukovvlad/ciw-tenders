"""Сервис парсинга Excel-смет (Pandas + openpyxl).

Single Responsibility: только чтение файла и фильтрация строк по виду раздела.
"""

from __future__ import annotations

import io

import pandas as pd

from app.domain.entities import EstimateRow

SECTION_COLUMN = "Вид раздела"
NAME_COLUMN = "Наименование"
SMR_VALUE = "СМР"


class ExcelEstimateParser:
    """Извлекает из сметы только строки видов работ (Вид раздела == 'СМР')."""

    def __init__(
        self,
        section_column: str = SECTION_COLUMN,
        name_column: str = NAME_COLUMN,
        smr_value: str = SMR_VALUE,
    ) -> None:
        self._section_column = section_column
        self._name_column = name_column
        self._smr_value = smr_value

    def parse(self, content: bytes) -> list[EstimateRow]:
        """Парсит содержимое .xlsx и возвращает отфильтрованные строки СМР."""
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl")

        missing = {self._section_column, self._name_column} - set(df.columns)
        if missing:
            raise ValueError(f"В файле отсутствуют обязательные колонки: {sorted(missing)}")

        smr = df[df[self._section_column].astype(str).str.strip() == self._smr_value]

        rows: list[EstimateRow] = []
        for idx, record in smr.iterrows():
            name = str(record[self._name_column]).strip()
            if not name or name.lower() == "nan":
                continue
            rows.append(
                EstimateRow(
                    row_number=int(idx) + 2,  # +2: строка заголовка + 0-based индекс
                    name=name,
                    raw=record.to_dict(),
                )
            )
        return rows
