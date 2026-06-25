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


# Единственный вручную поддерживаемый словарь, кроме оргтокенов.
# NB: «работы»/«работ» НЕ в стоп-листе — это слабый РАБОТНЫЙ сигнал; их стоп-листинг
# опрокинул бы «работы корпуса 5» в молчаливый ORG (нарушение асимметрии).
_STOPWORDS = frozenset(
    {
        "прочее", "прочие", "и", "в", "с", "по", "на",
        "для", "том", "числе", "включая", "т.п", "тп", "т.ч", "тч",
    }
)


def _is_abbrev(token: str) -> bool:
    return 2 <= len(token) <= 4 and token.isupper()


def has_work_word(name: str) -> bool:
    """True, если есть содержательный (не орг, не стоп) токен.

    Ошибается В СТОРОНУ «голова есть»: аббревиатура 2–4 заглавные считается головой.
    Оргтокены (вкл. ЖК/БЦ) отсекаются ПЕРВЫМИ — иначе они сами 2 заглавные и
    ложно сочлись бы головой.
    """
    for token in _TOKEN_RE.findall(name):
        if _is_org_token(token):
            continue
        if token.lower() in _STOPWORDS:
            continue
        if len(token) >= 3 or _is_abbrev(token):
            return True
    return False
