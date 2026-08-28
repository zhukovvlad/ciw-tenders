"""Тесты промпта tree-движка и разбора JSON-вердиктов (Task 7, спека §5.1)."""

from __future__ import annotations

from app.domain.entities import CatalogArticle, SectionMatchRequest
from app.infrastructure.ai.tree_prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    parse_verdicts,
    render_catalog,
)
from tests.fakes import make_tree_node as _tn


def test_render_catalog_indents_by_depth() -> None:
    cat = [CatalogArticle(1, "4", "Конструктив", None), CatalogArticle(2, "4.2", "Надземная", "4")]
    assert render_catalog(cat) == "(4) Конструктив\n  (4.2) Надземная"


def test_user_prompt_has_sections_hints_and_explicit_targets() -> None:
    nodes = [
        _tn(1, 1, "6", name="Фасады"), _tn(2, 2, "6.1", name="1 Этап"),
        _tn(3, 3, "6.1.1", name="Прочее"),
        _tn(4, 3, "6.1.2", name="Каркас", status="excluded"),
        _tn(5, 3, "6.1.3", name="Снято", status="confident", matched_code="6",
            review_status="rejected"),
    ]
    req = SectionMatchRequest(
        nodes=nodes, ancestors=[], hints={2: ("6", True), 3: ("6.99", False)},
        targets=frozenset({1}), catalog=[CatalogArticle(1, "6", "Фасады", None)],
        precedents=[],
    )
    p = build_user_prompt(req)
    assert "СПРАВОЧНИК:" in p and "ФРАГМЕНТ" in p and "ПРЕЦЕДЕНТЫ" not in p and "КОНТЕКСТ" not in p
    assert "[цель] 1 | 6 | Фасады" in p and "  2 | 6.1 | 1 Этап  [уже: 6]" in p
    assert "[предположительно: 6.99]" in p
    # не-цели без кода (excluded, rejected) помечены как контекст — модель по ним не отвечает
    assert "[контекст] 4 | 6.1.2 | Каркас" in p and "[контекст] 5 | 6.1.3 | Снято" in p
    assert "ЦЕЛИ (ответить только по ним): 1" in p
    assert "СПРАВОЧНИК" not in build_user_prompt(req, include_catalog=False)


def test_render_ancestors_shows_trust() -> None:
    from app.infrastructure.ai.tree_prompt import render_ancestors
    a = _tn(1, 1, "4", name="Конструктив")
    b = _tn(2, 2, "4.1", name="Этап")
    c = _tn(3, 3, "4.1.1", name="Плиты")
    out = render_ancestors([(a, ("4", True)), (b, None), (c, ("4.2", False))])
    assert "4 | Конструктив -> 4" in out
    assert "4.1 | Этап -> ?" in out
    assert "4.1.1 | Плиты -> 4.2 (предположительно)" in out


def test_system_prompt_pins_format_rules() -> None:
    for token in ('"sure"', '"alt"', "org", "none", "X.99", "[уже:", "[цель]", "[контекст]"):
        assert token in SYSTEM_PROMPT


def test_parse_verdicts() -> None:
    assert parse_verdicts('```json\n[{"i": 1, "code": "4.2", "sure": true, "alt": null}]\n```') == [
        {"i": 1, "code": "4.2", "sure": True, "alt": None}]
    assert parse_verdicts("нет массива") is None
    assert parse_verdicts('[{"i": 1, "code": "4.2", "sure": true') is None   # обрезан
    assert parse_verdicts('{"a": 1}') is None                                # не массив
    # две пары скобок в тексте: берётся первый ДЕКОДИРУЕМЫЙ массив, а не жадный срез
    text = 'Список [см. раздел 4] ниже: [{"i": 1, "code": "4", "sure": false, "alt": null}] конец'
    assert parse_verdicts(text) == [{"i": 1, "code": "4", "sure": False, "alt": None}]
