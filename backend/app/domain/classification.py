"""Лексическая классификация узлов сметы (WORK/ORG/UNSURE). Чистый домен, без I/O."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from app.domain.entities import StructuralAnomaly, WorkClass

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


def classify_lexical(name: str) -> WorkClass:
    """Каскад: нет оргтокена → WORK; орг + нет головы → ORG; орг + голова → UNSURE."""
    if not contains_org_token(name):
        return WorkClass.WORK
    if has_work_word(name):
        return WorkClass.UNSURE
    return WorkClass.ORG


def is_excluded(own_class: WorkClass, *, is_leaf: bool, has_non_org_ancestor: bool) -> bool:
    """Решение exclude/keep с учётом структуры дерева. ORG исключаем, КРОМЕ листа с non-org
    предком (работа, разбитая по корпусам/этапам, чьё имя совпало с оргтокеном)."""
    if own_class is not WorkClass.ORG:
        return False
    return not (is_leaf and has_non_org_ancestor)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _collapse_consecutive(parts: list[str]) -> list[str]:
    out: list[str] = []
    for part in parts:
        if not out or out[-1] != part:
            out.append(part)
    return out


# --- Позиционный резолв иерархии (стек по глубине-кода) ----------------------
# Резолв строится по ГЛУБИНЕ (число сегментов кода), а не усечением кода: стек смотрит
# только вверх → forward-ref (контекст снизу) невозможен, коллизии дублей разводятся,
# пропущенный уровень даёт ближайшего открытого предка. См. дизайн (ревью v2).


def resolve_ancestor_indices(depths: Sequence[int]) -> list[list[int]]:
    """depths — глубина каждого узла В ПОРЯДКЕ документа (1-based, ≥1).

    Для позиции i возвращает индексы предков root→parent: ближайший открытый узел на
    каждом уровне d < depths[i] (последний с глубиной d, не закрытый более мелким между ним
    и i). Пропущенный уровень выпадает из цепочки. Индексы строго возрастают и все < i.
    """
    stack: list[tuple[int, int]] = []  # (depth, index) открытых предков
    result: list[list[int]] = []
    for i, d in enumerate(depths):
        while stack and stack[-1][0] >= d:  # закрыть сёстер и более глубокие ветки
            stack.pop()
        result.append([idx for _, idx in stack])
        stack.append((d, i))
    return result


def leaf_flags(depths: Sequence[int]) -> list[bool]:
    """Лист ⟺ следующий узел НЕ глубже текущего (никто не открывается под ним).

    Узлы — только coded-строки (позиции в depths не входят), поэтому узел, под которым
    лишь позиции, остаётся листом."""
    n = len(depths)
    return [i == n - 1 or depths[i + 1] <= depths[i] for i in range(n)]


def canonical_codes(depths: Sequence[int]) -> list[str]:
    """Канонические коды (1, 1.1, 1.1.1 …) из ВОССТАНОВЛЕННОГО позиционного дерева.

    Глубина кода = длина реальной цепочки предков + 1 (пропущенные уровни схлопываются),
    поэтому устойчиво к битым исходным кодам. Потребитель — экспорт-ремонт (отдельный патч)."""
    chains = resolve_ancestor_indices(depths)
    child_count: dict[int | None, int] = {}
    codes: list[str] = []
    for chain in chains:
        parent = chain[-1] if chain else None
        child_count[parent] = child_count.get(parent, 0) + 1
        prefix = codes[parent] + "." if parent is not None else ""
        codes.append(prefix + str(child_count[parent]))
    return codes


def _parent_code(code: str) -> str | None:
    head, _, _ = code.rpartition(".")
    return head or None


def detect_structural_anomalies(
    rows: Sequence[tuple[int, str, str, int]],
) -> tuple[list[StructuralAnomaly], int]:
    """rows — (source_index, code, name, outline_level) coded-узлов В ПОРЯДКЕ документа.

    Возвращает построчные аномалии (duplicate_code / parent_below / parent_missing /
    depth_jump) и АГРЕГАТНЫЙ счётчик outline_overrides (outline_level+1 ≠ число сегментов).
    """
    counts = Counter(code for _, code, _, _ in rows)
    first_si_by_code: dict[str, int] = {}
    for si, code, _, _ in rows:
        first_si_by_code.setdefault(code, si)

    anomalies: list[StructuralAnomaly] = []
    overrides = 0
    prev_depth: int | None = None
    for si, code, name, outline in rows:
        depth = len(code.split("."))
        if outline + 1 != depth:
            overrides += 1
        if counts[code] >= 2:
            detail = f"код встречается {counts[code]} раз"
            anomalies.append(StructuralAnomaly("duplicate_code", si, code, name, detail))
        parent = _parent_code(code)
        if parent is not None:
            if parent not in counts:
                detail = f"родитель '{parent}' отсутствует в смете"
                anomalies.append(StructuralAnomaly("parent_missing", si, code, name, detail))
            elif first_si_by_code[parent] > si:
                detail = f"родитель '{parent}' встречается НИЖЕ (si={first_si_by_code[parent]})"
                anomalies.append(StructuralAnomaly("parent_below", si, code, name, detail))
        if prev_depth is not None and depth > prev_depth + 1:
            detail = f"скачок глубины {prev_depth}→{depth}"
            anomalies.append(StructuralAnomaly("depth_jump", si, code, name, detail))
        prev_depth = depth
    return anomalies, overrides


def build_embedding_input(
    self_name: str,
    ancestors: list[tuple[str, WorkClass]],
    *,
    self_class: WorkClass = WorkClass.WORK,
    separator: str = ". ",
    collapse_repeats: bool = True,
) -> str:
    """Крошка root→узел; ORG-предки выброшены (справочник org-free, не загрязняем вектор).
    Если узел сам ORG (self_class=ORG) — его собственное имя тоже выброшено (спасённый org-лист
    эмбедится по чистому work-контексту предков)."""
    parts = [_normalize_ws(name) for name, cls in ancestors if cls is not WorkClass.ORG]
    if self_class is not WorkClass.ORG:
        parts.append(_normalize_ws(self_name))
    if collapse_repeats:
        parts = _collapse_consecutive(parts)
    return separator.join(parts)
