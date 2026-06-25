from __future__ import annotations

import pytest

from app.domain.classification import contains_org_token


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
