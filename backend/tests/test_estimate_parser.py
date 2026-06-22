from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

from app.services.estimate_parser import EstimateParser

_NO = "№ раздела"
_NAME = "Наименование раздела / позиции"
_TYPE = "Вид раздела"


def _xlsx(rows: list[tuple[object, object, object]]) -> bytes:
    """rows: (№ раздела, наименование, вид раздела). None → пустая ячейка."""
    df = pd.DataFrame(rows, columns=[_NO, _NAME, _TYPE])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def test_classifies_nodes_and_positions() -> None:
    content = _xlsx(
        [
            ("1", "Подготовительные работы", "СМР"),
            ("1.1", "Этапы", None),
            (None, "Позиция А", None),
            (None, "Позиция Б", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1", "1.1"]
    assert [p.name for p in parsed.positions] == ["Позиция А", "Позиция Б"]
    assert parsed.positions[0].parent_code == "1.1"


def test_embedding_input_is_ancestors_plus_name_no_descendants() -> None:
    content = _xlsx(
        [
            ("1", "Подготовительные работы", "СМР"),
            ("1.1", "Этапы", None),
            ("1.1.5", "МОКАП", None),
            ("1.1.5.1", "МОКАП фасада", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    by_code = {n.code: n for n in parsed.nodes}
    assert by_code["1.1.5"].embedding_input == "Подготовительные работы. Этапы. МОКАП"
    assert by_code["1.1.5"].parent_code == "1.1"
    assert by_code["1.1.5"].section_type == "СМР"
    assert by_code["1.1.5"].depth == 3


def test_ancestors_by_segment_not_string_prefix() -> None:
    # 1.10 и 1.2 не должны путаться; предки 1.10 — это [1], не [1, 1.1]
    content = _xlsx(
        [
            ("1", "Раздел", "СМР"),
            ("1.2", "Второй", None),
            ("1.10", "Десятый", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    by_code = {n.code: n for n in parsed.nodes}
    assert by_code["1.10"].embedding_input == "Раздел. Десятый"
    assert by_code["1.10"].parent_code == "1"


def test_dtype_numeric_code_read_as_string() -> None:
    # числовые ячейки кода: без dtype=str pandas инферит float (1 → 1.0 → два сегмента)
    content = _xlsx([(1, "Раздел", "СМР"), (1.5, "Подраздел", None)])
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1", "1.5"]
    assert parsed.nodes[0].depth == 1


def test_source_index_integrity_with_skip_above() -> None:
    # пустое имя ВЫШЕ узла: позиционный индекс и счётчик выживших расходятся
    content = _xlsx(
        [
            ("1", "Раздел", "СМР"),   # df idx 0
            ("1.1", None, None),       # df idx 1 — пустое имя, пропускается
            ("1.2", "Живой узел", None),  # df idx 2 → source_index ДОЛЖЕН быть 2
        ]
    )
    parsed = EstimateParser().parse(content)
    live = next(n for n in parsed.nodes if n.code == "1.2")
    assert live.source_index == 2  # на enumerate-по-выжившим было бы 1


def test_duplicate_code_keeps_first_name_and_warns() -> None:
    content = _xlsx(
        [
            ("1", "Первый", "СМР"),
            ("1.1", "Имя-А", None),
            ("1.1", "Имя-Б", None),       # дубль кода
            ("1.1.1", "Дитя", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    assert sum(n.code == "1.1" for n in parsed.nodes) == 2          # оба сохранены
    child = next(n for n in parsed.nodes if n.code == "1.1.1")
    assert child.embedding_input == "Первый. Имя-А. Дитя"           # имя предка — первое
    assert any("1.1" in w for w in parsed.warnings)


def test_non_numeric_code_becomes_position_with_warning() -> None:
    content = _xlsx([("1", "Раздел", "СМР"), ("прим", "Примечание", None)])
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1"]
    assert any(p.name == "Примечание" for p in parsed.positions)
    assert parsed.warnings


def test_missing_required_column_raises() -> None:
    df = pd.DataFrame({"X": [1], "Y": [2]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")

    with pytest.raises(ValueError):
        EstimateParser().parse(buf.getvalue())


_GOLDEN = Path(__file__).resolve().parents[2] / "temp" / "Смета — копия.xlsx"


@pytest.mark.skipif(not _GOLDEN.exists(), reason="реальная смета не коммитится (приватность)")
def test_golden_real_estimate_structure() -> None:
    parsed = EstimateParser().parse(_GOLDEN.read_bytes())
    assert len(parsed.nodes) == 809
    assert len(parsed.positions) == 1953
    top = [n for n in parsed.nodes if n.depth == 1]
    assert len(top) == 18
    assert sum(n.section_type == "СМР" for n in top) == 15
    # source_index → физ.ячейка: узел 1.1.5 «МОКАП» на df idx 33 (физ.строка 35)
    mokap = next(n for n in parsed.nodes if n.code == "1.1.5")
    assert mokap.source_index == 33
