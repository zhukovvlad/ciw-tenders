"""Чистый домен бенчмарка: нормализация gold-кода/имени и подсказка класса узла."""

from __future__ import annotations

import re
from enum import StrEnum

from app.domain.classification import contains_org_token, has_work_word

_CODE_LINE = re.compile(r"^\((.*?)\)\s*(.*)$", re.DOTALL)


class BenchmarkKind(StrEnum):
    MATCHABLE = "matchable"      # есть эталонная статья — меряем top-1/top-3
    STRUCTURAL = "structural"    # оргкаркас — пайплайн должен исключить
    NO_ARTICLE = "no_article"    # работа без статьи в справочнике — оставить, не сматчить


def norm_code(raw: str) -> str:
    return re.sub(r"\s+", "", raw).strip(".")


def norm_name(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.replace("\xa0", " ")).strip().lower()


def parse_gold_cell(cell: str | None) -> tuple[str | None, str | None]:
    """`(6.3.1) Name` → ('6.3.1', 'Name'); пусто/мусор → (None, None)."""
    if cell is None:
        return (None, None)
    match = _CODE_LINE.match(str(cell).strip())
    if match is None:
        return (None, None)
    code = norm_code(match.group(1))
    # Снимок имени — регистр СОХРАНЯЕМ (читаемость + UI Спеки B), НЕ зовём norm_name.
    # \s покрывает \xa0, так что отличие от norm_name только в .lower(); лоуэркейс
    # применяется к обеим сторонам лишь при сравнении article_renamed.
    name = re.sub(r"\s+", " ", match.group(2)).strip()
    if not code or not all(seg.isdigit() for seg in code.split(".")):
        return (None, None)
    return (code, name or None)


def suggest_kind(cell: str | None, node_name: str) -> BenchmarkKind:
    """Гейт-подсказка: статья задана → matchable; пусто+(орг|нет головы) → structural;
    пусто+голова без орг → no_article (требует подтверждения человеком)."""
    code, _ = parse_gold_cell(cell)
    if code is not None:
        return BenchmarkKind.MATCHABLE
    if contains_org_token(node_name) or not has_work_word(node_name):
        return BenchmarkKind.STRUCTURAL
    return BenchmarkKind.NO_ARTICLE
