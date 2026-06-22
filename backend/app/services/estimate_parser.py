"""Иерархический парсер сметы. Чистая логика: bytes → ParsedEstimate. Без БД/AI."""

from __future__ import annotations

import io
import re

import pandas as pd

from app.domain.entities import EstimateNode, EstimatePosition, ParsedEstimate

SECTION_NO_COLUMN = "№ раздела"
NAME_COLUMN = "Наименование раздела / позиции"
SECTION_TYPE_COLUMN = "Вид раздела"


def _clean_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


class EstimateParser:
    """Строит дерево узлов из «№ раздела»; листья (№=NaN) — контекст."""

    def parse(self, content: bytes) -> ParsedEstimate:
        # № раздела — принудительно строкой: иначе number-formatted ячейка
        # коэрсится во float (1 → 1.0 → два сегмента), 1.10 схлопывается в 1.1.
        df = pd.read_excel(
            io.BytesIO(content), engine="openpyxl", dtype={SECTION_NO_COLUMN: str}
        )
        missing = {SECTION_NO_COLUMN, NAME_COLUMN} - set(df.columns)
        if missing:
            raise ValueError(f"В файле отсутствуют обязательные колонки: {sorted(missing)}")

        nodes: list[EstimateNode] = []
        positions: list[EstimatePosition] = []
        warnings: list[str] = []
        name_by_code: dict[str, str] = {}            # первое вхождение
        top_type_by_segment: dict[str, str | None] = {}
        last_node_code: str | None = None

        # source_index = ИСХОДНАЯ 0-based позиция (df.iterrows сохраняет RangeIndex);
        # НЕ enumerate по выжившим, НЕ reset_index — иначе после skip уедет на -1.
        for raw_idx, record in df.iterrows():
            source_index = int(raw_idx)  # type: ignore[arg-type]
            no = record[SECTION_NO_COLUMN]
            name = _clean_name(record[NAME_COLUMN])
            if not name or name.lower() == "nan":
                warnings.append(f"строка {source_index}: пустое имя — пропущена")
                continue

            if pd.isna(no):  # POSITION
                if last_node_code is None:
                    warnings.append(f"строка {source_index}: позиция до первого узла")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue

            code = re.sub(r"\s+", "", str(no)).strip(".")
            segments = code.split(".")
            if not code or not all(seg.isdigit() for seg in segments):
                warnings.append(f"строка {source_index}: нечисловой код '{no}' → позиция")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue

            # NODE
            depth = len(segments)
            parent_code = ".".join(segments[:-1]) or None
            if code in name_by_code:
                warnings.append(f"строка {source_index}: дубль кода '{code}'")
            else:
                name_by_code[code] = name
            if depth == 1:
                vid = record[SECTION_TYPE_COLUMN] if SECTION_TYPE_COLUMN in df.columns else None
                top_type_by_segment[code] = None if pd.isna(vid) else str(vid).strip()
            section_type = top_type_by_segment.get(segments[0])

            parts: list[str] = []
            for i in range(1, depth):  # предки усечением сегментов
                ancestor = ".".join(segments[:i])
                if ancestor in name_by_code:
                    parts.append(name_by_code[ancestor])
                else:
                    warnings.append(f"строка {source_index}: нет предка '{ancestor}'")
            parts.append(name)
            embedding_input = ". ".join(parts)  # байт-в-байт как template_parser

            nodes.append(
                EstimateNode(
                    code=code,
                    name=name,
                    parent_code=parent_code,
                    section_type=section_type,
                    embedding_input=embedding_input,
                    source_index=source_index,
                    depth=depth,
                )
            )
            last_node_code = code

        return ParsedEstimate(nodes=nodes, positions=positions, warnings=warnings)
