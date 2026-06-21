from __future__ import annotations

import io

import pandas as pd
import pytest

from app.domain.errors import TemplateValidationError
from app.services.template_parser import TemplateParser


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _by_code(result) -> dict:
    return {r.article_code: r for r in result.rows}


def test_parses_codes_names_parents_and_enriched_text() -> None:
    result = TemplateParser().parse(
        _xlsx(
            [
                "(1.) Подготовительные работы",
                "(1.4.) Мокап",
                "(1.4.1.) Мокап фасада",
            ]
        )
    )
    rows = _by_code(result)

    assert set(rows) == {"1", "1.4", "1.4.1"}
    assert rows["1"].parent_code is None
    assert rows["1.4"].parent_code == "1"
    assert rows["1.4.1"].parent_code == "1.4"
    assert rows["1.4.1"].name == "Мокап фасада"
    assert (
        rows["1.4.1"].embedding_input == "Подготовительные работы. Мокап. Мокап фасада"
    )
    assert result.skipped == []


def test_recovers_code_with_inner_space() -> None:
    # (6.6 .) -> 6.6, не отбрасывается
    result = TemplateParser().parse(_xlsx(["(6.) Фасады", "(6.6 .) Система обслуживания фасадов"]))
    rows = _by_code(result)
    assert "6.6" in rows
    assert rows["6.6"].parent_code == "6"
    assert result.skipped == []


def test_sanitizes_name_whitespace() -> None:
    result = TemplateParser().parse(_xlsx(["(2.)   Котлован   работы тут "]))
    assert result.rows[0].name == "Котлован работы тут"


def test_skips_unparseable_and_empty_name_rows() -> None:
    result = TemplateParser().parse(
        _xlsx(["(1.) Раздел", "просто текст без кода", "(1.1.)   "])
    )
    assert [r.article_code for r in result.rows] == ["1"]
    assert len(result.skipped) == 2


def test_skips_non_numeric_code_segment() -> None:
    result = TemplateParser().parse(_xlsx(["(1.) Раздел", "(1.x.) Кривой код"]))
    assert [r.article_code for r in result.rows] == ["1"]
    assert result.skipped == ["(1.x.) Кривой код"]


def test_duplicate_code_raises() -> None:
    with pytest.raises(TemplateValidationError):
        TemplateParser().parse(_xlsx(["(1.) Раздел", "(1.) Дубль"]))


def test_orphan_parent_raises() -> None:
    with pytest.raises(TemplateValidationError):
        TemplateParser().parse(_xlsx(["(1.) Раздел", "(2.5.) Без родителя 2"]))
