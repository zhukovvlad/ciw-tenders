from __future__ import annotations

from app.domain.classification import full_breadcrumbs


def test_nested_chain_full_names() -> None:
    items = [(1, "Раздел"), (2, "Подраздел"), (3, "Работа")]
    assert full_breadcrumbs(items) == [[], ["Раздел"], ["Раздел", "Подраздел"]]


def test_org_ancestors_not_filtered() -> None:
    # Полная цепочка — org-узлы ВКЛЮЧЕНЫ (крошка зеркалит документ, не вход эмбеддера)
    items = [(1, "1 Этап ЖК (орг)"), (2, "Работа")]
    assert full_breadcrumbs(items) == [[], ["1 Этап ЖК (орг)"]]


def test_duplicate_codes_resolved_positionally() -> None:
    # Два узла глубины 1 — ребёнок цепляется к БЛИЖАЙШЕМУ сверху
    items = [(1, "Первый"), (1, "Второй"), (2, "Дитя второго")]
    assert full_breadcrumbs(items)[2] == ["Второй"]


def test_skipped_level_drops_from_chain() -> None:
    items = [(1, "Корень"), (3, "Сразу глубина 3")]
    assert full_breadcrumbs(items)[1] == ["Корень"]
