"""Чтение размеченной сметы (xlsx) в seed-узлы бенчмарка. Только для CLI-сида."""

from __future__ import annotations

import re

import openpyxl

from app.domain.benchmark import BenchmarkKind, parse_gold_cell, suggest_kind
from app.domain.entities import BenchmarkNodeSeed

_SECTION_NO_COL = 0   # «№ раздела»
_ARTICLE_COL = 1      # «Статья СМР»
_NAME_COL = 2         # «Наименование раздела / позиции»


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _is_node_code(raw: object) -> str | None:
    if raw is None:
        return None
    code = re.sub(r"\s+", "", str(raw)).strip(".")
    if not code or not all(seg.isdigit() for seg in code.split(".")):
        return None
    return code


def read_benchmark_nodes(path: str) -> list[BenchmarkNodeSeed]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    nodes: list[BenchmarkNodeSeed] = []
    for source_index, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        cells = list(row) + [None] * 3
        code = _is_node_code(cells[_SECTION_NO_COL])
        if code is None:
            continue
        name = _clean(cells[_NAME_COL])
        if not name or name.lower() == "nan":
            continue
        cell = cells[_ARTICLE_COL]
        kind = suggest_kind(cell, name)
        art_code, art_name = parse_gold_cell(cell)
        nodes.append(
            BenchmarkNodeSeed(
                code=code,
                name=name,
                source_index=source_index,
                expected_kind=kind.value,
                expected_article_code=art_code if kind is BenchmarkKind.MATCHABLE else None,
                expected_article_name=art_name if kind is BenchmarkKind.MATCHABLE else None,
            )
        )
    return nodes
