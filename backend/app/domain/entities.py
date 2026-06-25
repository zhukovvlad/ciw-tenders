"""Доменные сущности. Чистый Python без зависимостей от ORM/фреймворков."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    """Роль пользователя."""

    USER = "user"
    ADMIN = "admin"


class WorkClass(StrEnum):
    """Класс узла сметы по смыслу имени (для фильтрации оргзаголовков). В БД НЕ хранится."""

    WORK = "work"      # вид работ — матчится
    ORG = "org"        # организационный заголовок — исключается (status='excluded')
    UNSURE = "unsure"  # неоднозначно — трактуем как WORK (асимметрия ошибок)


@dataclass(frozen=True, slots=True)
class TemplateArticle:
    """Эталонная статья справочника СМР (узел дерева через parent_id)."""

    article_code: str
    name: str
    embedding_input: str
    parent_id: int | None = None
    id: int | None = None
    embedding: list[float] | None = None


@dataclass(frozen=True, slots=True)
class ArticleCandidate:
    """Кандидат из векторного поиска: статья + мера близости (cosine similarity 0..1)."""

    article: TemplateArticle
    score: float


@dataclass(frozen=True, slots=True)
class User:
    """Учётная запись пользователя."""

    email: str
    password_hash: str
    role: Role = Role.USER
    is_active: bool = True
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Полезная нагрузка JWT (без роли — роль читается из БД)."""

    user_id: int


@dataclass(frozen=True, slots=True)
class ExistingArticle:
    """Снимок существующей строки справочника (для дельты импорта)."""

    id: int
    article_code: str
    embedding_input: str


@dataclass(frozen=True, slots=True)
class PlannedInsert:
    article_code: str
    name: str
    parent_code: str | None
    embedding_input: str


@dataclass(frozen=True, slots=True)
class PlannedUpdate:
    id: int
    article_code: str
    name: str
    parent_code: str | None
    embedding_input: str
    invalidate_embedding: bool


@dataclass(frozen=True, slots=True)
class ImportPlan:
    inserts: list[PlannedInsert]
    updates: list[PlannedUpdate]
    delete_ids: list[int]
    delete_codes: list[str]
    unchanged: int


@dataclass(frozen=True, slots=True)
class ImportReport:
    created: int
    updated: int
    deleted: int
    unchanged: int
    skipped: list[str]
    pending_embeddings: int
    dry_run: bool
    force_required: bool


@dataclass(frozen=True, slots=True)
class PendingEmbedding:
    """Строка справочника, ожидающая векторизации."""

    id: int
    embedding_input: str


class EstimateRowStatus(StrEnum):
    """Статус узла сметы при матчинге (слаг — для хранения; рус.подписи в API-DTO)."""

    PENDING = "pending"
    CONFIDENT = "confident"
    NEEDS_REVIEW = "needs_review"
    NO_MATCH = "no_match"
    ERROR = "error"


class ReviewStatus(StrEnum):
    """Ось ревью поверх иммутабельного AI-снимка (status). Независима от EstimateRowStatus."""

    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"   # согласие с рекомендацией AI (matched_*)
    OVERRIDDEN = "overridden"  # выбран другой кандидат или ручной подбор
    REJECTED = "rejected"      # явно «статьи нет»


class EstimateStatus(StrEnum):
    """Статус сметы в пайплайне матчинга."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    PARTIAL_ERROR = "partial_error"
    BLOCKED = "blocked"


class EstimateRowKind(StrEnum):
    """Тип строки сметы при разборе."""

    NODE = "node"          # нумерованная строка (раздел/подраздел) — матчится
    POSITION = "position"  # строка с №=NaN (листовая позиция) — контекст


@dataclass(frozen=True, slots=True)
class EstimateNode:
    """Нумерованный узел сметы (раздел/подраздел) — единица матчинга."""

    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    embedding_input: str
    source_index: int
    depth: int


@dataclass(frozen=True, slots=True)
class EstimatePosition:
    """Листовая позиция (№=NaN), привязана к ближайшему узлу сверху."""

    name: str
    parent_code: str | None
    source_index: int


@dataclass(frozen=True, slots=True)
class ParsedEstimate:
    nodes: list[EstimateNode]
    positions: list[EstimatePosition]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class NewEstimate:
    """Данные для создания сметы (до записи)."""

    user_id: int
    filename: str
    original_object_key: str


@dataclass(frozen=True, slots=True)
class StoredEstimateRow:
    """Сохранённый узел сметы."""

    id: int
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    embedding_input: str
    source_index: int
    status: str
    has_embedding: bool = False
    matched_article_id: int | None = None
    matched_code: str | None = None
    matched_name: str | None = None
    score: float | None = None
    candidates: list[MatchCandidate] = field(default_factory=list)
    review_status: str = "unreviewed"
    final_article_id: int | None = None
    final_code: str | None = None
    final_name: str | None = None
    reviewed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Estimate:
    """Агрегат сохранённой сметы (без original_object_key — наружу не отдаём)."""

    id: int
    user_id: int
    filename: str
    status: str
    created_at: datetime
    rows: list[StoredEstimateRow] = field(default_factory=list)
    status_detail: str | None = None


@dataclass(frozen=True, slots=True)
class EstimateSummary:
    id: int
    filename: str
    status: str
    nodes_count: int
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """Замороженный кандидат в снимке (для ревью в SP3). id — для перелинковки."""

    id: int | None
    code: str
    name: str
    score: float


@dataclass(frozen=True, slots=True)
class NodeMatch:
    """Результат матчинга одного узла (пишется в снимок estimate_rows)."""

    status: EstimateRowStatus
    matched_id: int | None = None
    matched_code: str | None = None
    matched_name: str | None = None
    score: float | None = None
    candidates: list[MatchCandidate] = field(default_factory=list)
    match_error: str | None = None


@dataclass(frozen=True, slots=True)
class MatchableNode:
    """Узел, готовый к матчингу: id + сохранённый вектор + текст для арбитра."""

    id: int
    embedding: list[float]
    embedding_input: str


@dataclass(frozen=True, slots=True)
class NodeToClassify:
    """Узел на вход LLM-классификатору: имя + цепочка предков (root→parent) как контекст."""

    name: str
    ancestors: tuple[str, ...]
