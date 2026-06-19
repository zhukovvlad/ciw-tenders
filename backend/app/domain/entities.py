"""Доменные сущности. Чистый Python без зависимостей от ORM/фреймворков."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MatchStatus(StrEnum):
    """Статус сопоставления строки сметы с эталонной статьёй."""

    CONFIDENT = "Уверенное совпадение"
    NEEDS_REVIEW = "Требует проверки"
    NO_MATCH = "Нет совпадений"


@dataclass(frozen=True, slots=True)
class TemplateArticle:
    """Эталонная статья справочника СМР."""

    article_code: str
    name: str
    section_name: str
    id: int | None = None
    embedding: list[float] | None = None


@dataclass(frozen=True, slots=True)
class EstimateRow:
    """Строка целевой сметы (после фильтрации по виду раздела 'СМР')."""

    row_number: int
    name: str
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArticleCandidate:
    """Кандидат из векторного поиска: статья + мера близости (cosine similarity 0..1)."""

    article: TemplateArticle
    score: float


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Итог сопоставления одной строки сметы."""

    source_row: EstimateRow
    matched_article: TemplateArticle | None
    status: MatchStatus
    score: float
    candidates: list[ArticleCandidate] = field(default_factory=list)
