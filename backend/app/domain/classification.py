"""Лексическая классификация узлов сметы (WORK/ORG/UNSURE). Чистый домен, без I/O."""

from __future__ import annotations

import re

# Оргтокены — маленькое закрытое множество. Стемы заякорены на начало слова и
# матчат русские окончания (этап→этапы/этапов); «этап» НЕ ловит «этаж».
# ВАЖНО: «пусков» матчит «пусковой», но не «пусконаладочные» (это работа).
_ORG_STEMS = (
    "этап", "очеред", "пусков", "корпус", "литер", "секци", "объект",
)
# «блок-секция» ловится через «секци» (search по имени), отдельный стем не нужен;
# «блок» в стемы НЕ добавляем — это и работный термин («блок ФБС»). «блок-секция N»
# уйдёт в LLM как смесь (голова «блок») — безопасно по асимметрии.
# Литералы без окончаний — организационные аббревиатуры.
_ORG_LITERALS = ("жк", "бц")

_ORG_STEM_RE = re.compile(
    r"(?<![а-яё])(?:" + "|".join(_ORG_STEMS) + r")[а-яё]*",
    re.IGNORECASE,
)
_ORG_LITERAL_RE = re.compile(
    r"(?<![а-яёa-z])(?:" + "|".join(_ORG_LITERALS) + r")(?![а-яёa-z])",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яёЁ]+")


def _is_org_token(token: str) -> bool:
    low = token.lower()
    if low in _ORG_LITERALS:
        return True
    return _ORG_STEM_RE.fullmatch(low) is not None


def contains_org_token(name: str) -> bool:
    return (
        _ORG_STEM_RE.search(name) is not None
        or _ORG_LITERAL_RE.search(name) is not None
    )
