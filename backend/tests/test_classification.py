from __future__ import annotations

import pytest

from app.domain.classification import classify_lexical, contains_org_token, has_work_word
from app.domain.entities import WorkClass


@pytest.mark.parametrize(
    "name",
    [
        "I и 2 Этапы БЦ и ЖК",   # founding-пример: «Этапы» (мн.ч.) + литералы
        "Корпусов 5",
        "Очереди строительства",
        "1 Этап ЖК",
        "Корпус № 2; 3; 4",
    ],
)
def test_contains_org_token_true(name: str) -> None:
    assert contains_org_token(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "Устройство кровли",
        "работы на этаже 3",   # этаж ≠ этап
        "Этажность здания",    # этаж + здание (не оргтокены)
        "Гидроизоляция подземной части здания",
    ],
)
def test_contains_org_token_false(name: str) -> None:
    assert contains_org_token(name) is False


@pytest.mark.parametrize("name", ["МАФ", "ЗИП", "VRF", "КС", "Устройство кровли"])
def test_has_work_word_true(name: str) -> None:
    assert has_work_word(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "1 Этап ЖК",        # ЖК — литерал-оргтокен, не голова (до аббрев-правила!)
        "2 Этап БЦ",
        "Корпус № 2; 3; 4",
        "и в том числе",    # стоп-слова
        "прочее",
    ],
)
def test_has_work_word_false(name: str) -> None:
    assert has_work_word(name) is False


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Корпус № 2; 3; 4", WorkClass.ORG),          # чистый каркас → ORG без LLM
        ("1 Этап ЖК", WorkClass.ORG),                  # пересечение ЖК-литерал × аббрев
        ("Устройство кровли", WorkClass.WORK),         # нет оргтокена → WORK
        ("Наружное освещение 1 Этап ЖК", WorkClass.UNSURE),  # смесь → LLM
        ("МАФ Корпус 3", WorkClass.UNSURE),            # аббрев-работа + орг → НЕ ORG
        ("Объект озеленения", WorkClass.UNSURE),       # объект + голова → НЕ молчаливый ORG
    ],
)
def test_classify_lexical(name: str, expected: WorkClass) -> None:
    assert classify_lexical(name) is expected
