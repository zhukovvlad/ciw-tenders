from __future__ import annotations

import io
from pathlib import Path

import openpyxl
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


def _xlsx_with_outline(
    rows: list[tuple[object, object, object]],
    outline_levels: list[int],
) -> bytes:
    """Как _xlsx, но дополнительно проставляет outline_level строкам данных через openpyxl.

    outline_levels[i] — уровень группировки для i-й строки данных (0-based).
    Физическая строка данных = source_index + 2 (строка 1 — заголовок).
    Создаёт файл, где file_has_outline=True → _read_outline идёт по не-плоскому пути.
    """
    base = _xlsx(rows)
    wb = openpyxl.load_workbook(io.BytesIO(base))
    ws = wb.worksheets[0]
    for i, level in enumerate(outline_levels):
        physical_row = i + 2  # строка 1 — заголовок
        ws.row_dimensions[physical_row].outline_level = level
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
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


def test_duplicate_code_uses_nearest_preceding_parent() -> None:
    # Позиционный резолв: ребёнок берёт БЛИЖАЙШЕГО предшествующего предка, не первое вхождение.
    content = _xlsx(
        [
            ("1", "Первый", "СМР"),
            ("1.1", "Имя-А", None),
            ("1.1", "Имя-Б", None),       # дубль кода — ближайший предок для следующего
            ("1.1.1", "Дитя", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    child = next(n for n in parsed.nodes if n.code == "1.1.1")
    assert child.embedding_input == "Первый. Имя-Б. Дитя"   # было «Имя-А» (первое вхождение)
    assert any(a.kind == "duplicate_code" for a in parsed.anomalies)
    # оба дубля-узла с кодом «1.1» остаются в дереве (не дедуплицируются)
    assert sum(n.code == "1.1" for n in parsed.nodes) == 2


def test_parent_below_does_not_pull_context_from_below() -> None:
    # «родитель ниже»: ребёнок 10.2.1 встречается ВЫШЕ строки-родителя 10.2 →
    # позиционный стек НЕ тянет имя снизу (forward-ref невозможен).
    content = _xlsx(
        [
            ("10", "Инженерные системы", "СМР"),
            ("10.1", "Освещение ЖК", None),
            ("10.1.1", "Монтаж опор", None),     # предок в документе — «Освещение ЖК»
            ("10.2", "Освещение Офис", None),    # код-родитель 10.1.1? нет; здесь просто следом
        ]
    )
    parsed = EstimateParser().parse(content)
    node = next(n for n in parsed.nodes if n.code == "10.1.1")
    assert node.embedding_input == "Инженерные системы. Освещение ЖК. Монтаж опор"


def test_outline_overrides_zero_on_flat_file() -> None:
    # df.to_excel не создаёт группировку → file_has_outline False → overrides 0.
    content = _xlsx([("1", "Раздел", "СМР"), ("1.1", "Под", None)])
    parsed = EstimateParser().parse(content)
    assert parsed.outline_overrides == 0


def test_outline_round_trip_non_flat() -> None:
    # Покрывает НЕ-плоский путь (_read_outline): файл содержит реальную группировку строк,
    # поэтому file_has_outline=True и outline_overrides считается из фактических outline_level.
    # Две проверки вместе доказывают, что outline ЧИТАЕТСЯ и КОРРЕКТНО питает счётчик:
    #   1) выровненный файл (outline_level+1 == len(segments)) → overrides == 0;
    #   2) РАССОГЛАСОВАННЫЙ файл (один узел с outline_level+1 != len(segments)) → overrides == 1.
    # Без кейса (2) тест прошёл бы и при молчаливом сбое чтения outline (файл выглядел бы
    # плоским → file_has_outline guard → overrides=0), не доказывая фактического чтения.
    rows: list[tuple[object, object, object]] = [
        ("1", "Раздел", "СМР"),
        ("1.1", "Подраздел", None),
        ("1.1.1", "Работа", None),
    ]

    # (1) Выровнено: outline_level[i] = глубина-1 (0,1,2) → совпадает с len(segments) → overrides 0.
    aligned = _xlsx_with_outline(rows, [0, 1, 2])
    parsed_aligned = EstimateParser().parse(aligned)
    assert len(parsed_aligned.nodes) == 3
    assert not any("рассинхрон" in w for w in parsed_aligned.warnings)
    assert parsed_aligned.outline_overrides == 0

    # (2) Рассогласовано: у «1.1.1» (глубина 3) outline_level=1 → 1+1=2 != 3 → ровно ОДИН override.
    # Положительная (>0) проверка доказывает, что outline_level реально прочитан и учтён в счётчике.
    misaligned = _xlsx_with_outline(rows, [0, 1, 1])
    parsed_misaligned = EstimateParser().parse(misaligned)
    assert len(parsed_misaligned.nodes) == 3
    assert not any("рассинхрон" in w for w in parsed_misaligned.warnings)
    assert parsed_misaligned.outline_overrides == 1


def test_desync_warns_and_disables_outline_not_raises() -> None:
    # При рассинхроне pandas↔openpyxl: warning + outline_overrides отключён (==0/None),
    # но ingest НЕ падает, а крошка из кодов строится корректно. Сценарий рассинхрона
    # эмпирически недостижим через _xlsx() — pandas и openpyxl видят строки одинаково.
    # Тест фиксирует, что сверка СТОИТ и НЕ ложно-срабатывает на чистом файле:
    # outline_overrides не обнулён ложно, warning про рассинхрон отсутствует.
    # Примечание: outline_overrides==0 здесь проходит через ветку file_has_outline=False
    # (df.to_excel не создаёт группировку), а не через ветку desync — ветка desync
    # эмпирически недостижима через _xlsx() при корректном pandas↔openpyxl.
    content = _xlsx([("1", "Раздел", "СМР"), ("1.1", "Под", None)])
    parsed = EstimateParser().parse(content)
    # Нет ложного рассинхрона — предупреждение про outline-детекцию не должно быть
    assert not any("рассинхрон" in w for w in parsed.warnings)
    # outline_overrides корректен (не обнулён ложно)
    assert parsed.outline_overrides == 0
    # ingest не упал, крошка строится корректно
    assert len(parsed.nodes) == 2
    assert parsed.nodes[1].embedding_input == "Раздел. Под"


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
