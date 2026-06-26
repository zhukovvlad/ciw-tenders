from __future__ import annotations

from app.domain.benchmark import (
    BenchmarkKind,
    norm_code,
    norm_name,
    parse_gold_cell,
    suggest_kind,
)


def test_norm_code_strips_parens_spaces_dots():
    assert norm_code("6.3.1") == "6.3.1"
    assert norm_code(" 6. 3 .1. ") == "6.3.1"


def test_norm_name_lowercases_and_collapses_ws():
    assert norm_name("  Отделка\xa0 кровли ") == "отделка кровли"


def test_parse_gold_cell_extracts_code_and_name():
    assert parse_gold_cell("(6.3.1) Устройство подсистемы фасада") == (
        "6.3.1",
        "Устройство подсистемы фасада",
    )


def test_parse_gold_cell_empty_and_garbage_return_none():
    assert parse_gold_cell(None) == (None, None)
    assert parse_gold_cell("   ") == (None, None)
    assert parse_gold_cell("без скобок") == (None, None)
    assert parse_gold_cell("(abc) Название") == (None, None)
    assert parse_gold_cell("(1a.2) Название") == (None, None)


def test_parse_gold_cell_collapses_nbsp_in_name():
    assert parse_gold_cell("(1.2) Устройство\xa0фасада") == ("1.2", "Устройство фасада")


def test_suggest_kind_matchable_when_cell_present():
    assert suggest_kind("(1.2) Мобилизация", "Мобилизация") is BenchmarkKind.MATCHABLE


def test_suggest_kind_structural_when_empty_and_org_token():
    assert suggest_kind(None, "1 Этап ЖК") is BenchmarkKind.STRUCTURAL
    assert suggest_kind(None, "Корпус № 2; 3; 4") is BenchmarkKind.STRUCTURAL


def test_suggest_kind_no_article_when_empty_work_head_no_org():
    assert suggest_kind(None, "Инженерные системы") is BenchmarkKind.NO_ARTICLE
