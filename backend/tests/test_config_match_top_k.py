"""Дефолт настройки match_top_k (рычаг №5 в TECH_DEBT «Качество матчинга»)."""
from __future__ import annotations

from app.core.config import Settings


def test_match_top_k_default_is_5() -> None:
    # env обязательных полей задан в conftest до импорта приложения.
    assert Settings().match_top_k == 5
