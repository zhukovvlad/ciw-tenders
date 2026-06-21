"""Парсер файла-шаблона справочника СМР.

Формат: один столбец, строки '(КОД) Наименование'. Иерархия закодирована в коде
('1' -> '1.4' -> '1.4.1'). Санитайзинг кода: убрать внутренние пробелы и хвостовую точку
(восстанавливает грязь вида '(6.6 .)'); сегменты обязаны быть числовыми. embedding_input —
имена всех предков от корня + собственное, через '. '.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd

from app.domain.errors import TemplateValidationError

_LINE = re.compile(r"^\((.*?)\)\s*(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ParsedTemplateRow:
    article_code: str
    name: str
    parent_code: str | None
    embedding_input: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[ParsedTemplateRow]
    skipped: list[str]


class TemplateParser:
    def parse(self, content: bytes) -> ParseResult:
        df = pd.read_excel(io.BytesIO(content), header=None, engine="openpyxl")
        series = df.iloc[:, 0].dropna().astype(str) if not df.empty else []

        skipped: list[str] = []
        name_by_code: dict[str, str] = {}
        order: list[str] = []

        for raw in series:
            cell = raw.strip()
            match = _LINE.match(cell)
            if match is None:
                skipped.append(cell)
                continue
            code = re.sub(r"\s+", "", match.group(1)).strip(".")
            name = re.sub(r"\s+", " ", match.group(2)).strip()
            if not name or not code:
                skipped.append(cell)
                continue
            if not all(seg.isdigit() for seg in code.split(".")):
                skipped.append(cell)
                continue
            if code in name_by_code:
                raise TemplateValidationError(f"Дубликат кода в файле: {code}")
            name_by_code[code] = name
            order.append(code)

        rows = [self._build_row(code, name_by_code) for code in order]
        return ParseResult(rows=rows, skipped=skipped)

    @staticmethod
    def _build_row(code: str, name_by_code: dict[str, str]) -> ParsedTemplateRow:
        segments = code.split(".")
        parent_code = ".".join(segments[:-1]) or None
        if parent_code is not None and parent_code not in name_by_code:
            raise TemplateValidationError(f"Сирота: у кода {code} нет родителя {parent_code}")
        ancestors = [".".join(segments[:i]) for i in range(1, len(segments) + 1)]
        embedding_input = ". ".join(name_by_code[a] for a in ancestors)
        return ParsedTemplateRow(
            article_code=code,
            name=name_by_code[code],
            parent_code=parent_code,
            embedding_input=embedding_input,
        )
