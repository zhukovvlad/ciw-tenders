from __future__ import annotations

import pytest

from app.domain.classification import (
    build_embedding_input,
    classify_lexical,
    contains_org_token,
    has_work_word,
)
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


def test_build_embedding_input_drops_org_ancestors() -> None:
    ancestors = [
        ("1 Этап ЖК", WorkClass.ORG),
        ("Фасадные работы", WorkClass.WORK),
    ]
    assert build_embedding_input("Устройство навесных фасадов", ancestors) == (
        "Фасадные работы. Устройство навесных фасадов"
    )


def test_build_embedding_input_normalizes_and_collapses() -> None:
    ancestors = [("Устройство  заполнения", WorkClass.WORK)]  # двойной пробел
    assert build_embedding_input("Устройство  заполнения", ancestors) == (
        "Устройство заполнения"  # повтор схлопнут, пробелы нормализованы
    )


def test_fake_classifier_aligns_output_to_input() -> None:
    from app.domain.entities import NodeToClassify
    from tests.fakes import FakeWorkTypeClassifier

    clf = FakeWorkTypeClassifier(verdicts={"Гостиница Заря": WorkClass.ORG})
    items = [
        NodeToClassify(name="Гостиница Заря", ancestors=("Фасадные работы",)),
        NodeToClassify(name="что-то ещё", ancestors=()),
    ]
    assert clf.classify(items) == [WorkClass.ORG, WorkClass.UNSURE]


def test_build_embedding_input_drops_self_when_org() -> None:
    crumb = build_embedding_input(
        "Корпус 8", [("Гидроизоляция фундаментной плиты", WorkClass.WORK)], self_class=WorkClass.ORG
    )
    assert crumb == "Гидроизоляция фундаментной плиты"  # своё org-имя выброшено


def test_build_embedding_input_keeps_self_by_default() -> None:
    crumb = build_embedding_input("Монтаж", [("Раздел", WorkClass.WORK)])
    assert crumb == "Раздел. Монтаж"  # дефолт self_class=WORK — поведение прежнее


def test_build_embedding_input_empty_when_all_org_including_self() -> None:
    crumb = build_embedding_input(
        "Корпус 8", [("1 Этап ЖК", WorkClass.ORG)], self_class=WorkClass.ORG
    )
    assert crumb == ""


def test_build_embedding_input_keeps_unsure_ancestor_and_self() -> None:
    crumb = build_embedding_input(
        "Лифты", [("Раздел", WorkClass.UNSURE)], self_class=WorkClass.WORK
    )
    assert crumb == "Раздел. Лифты"  # UNSURE-предок остаётся (фильтруется только ORG)


def test_is_excluded_org_leaf_with_non_org_ancestor_kept() -> None:
    from app.domain.classification import is_excluded

    assert is_excluded(WorkClass.ORG, is_leaf=True, has_non_org_ancestor=True) is False


def test_is_excluded_org_nonleaf_excluded() -> None:
    from app.domain.classification import is_excluded

    assert is_excluded(WorkClass.ORG, is_leaf=False, has_non_org_ancestor=True) is True


def test_is_excluded_org_leaf_without_non_org_ancestor_excluded() -> None:
    from app.domain.classification import is_excluded

    assert is_excluded(WorkClass.ORG, is_leaf=True, has_non_org_ancestor=False) is True


def test_is_excluded_work_and_unsure_kept() -> None:
    from app.domain.classification import is_excluded

    assert is_excluded(WorkClass.WORK, is_leaf=True, has_non_org_ancestor=False) is False
    assert is_excluded(WorkClass.UNSURE, is_leaf=False, has_non_org_ancestor=False) is False
