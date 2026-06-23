"""Порты (абстрактные интерфейсы) доменного слоя.

Слой приложения (services) зависит ТОЛЬКО от этих абстракций — это Dependency
Inversion Principle. Конкретные реализации живут в infrastructure/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import (
    ArticleCandidate,
    Estimate,
    EstimateNode,
    EstimateStatus,
    EstimateSummary,
    ExistingArticle,
    ImportPlan,
    MatchableNode,
    NewEstimate,
    NodeMatch,
    PendingEmbedding,
    TemplateArticle,
    TokenPayload,
    User,
)


class ArticleRepository(ABC):
    """Хранилище эталонных статей: CRUD + векторный поиск."""

    @abstractmethod
    def add(self, article: TemplateArticle) -> TemplateArticle: ...

    @abstractmethod
    def get_by_code(self, code: str) -> TemplateArticle | None: ...

    @abstractmethod
    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]: ...

    @abstractmethod
    def delete(self, article_id: int) -> None: ...

    @abstractmethod
    def delete_all(self) -> int: ...

    @abstractmethod
    def has_descendant_codes(self, code: str) -> bool:
        """Есть ли строки с article_code LIKE code || '.%'."""
        ...

    @abstractmethod
    def search_similar(
        self, embedding: list[float], top_k: int = 3
    ) -> list[ArticleCandidate]:
        """Топ-K ближайших статей по эмбеддингу (cosine similarity)."""
        ...

    @abstractmethod
    def matching_readiness(self) -> tuple[int, int]:
        """(total, pending): всего статей и сколько с embedding IS NULL. Для gate матчинга."""
        ...


class Embedder(ABC):
    """Порт векторизации текста (RAG: retrieval)."""

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class LLMMatcher(ABC):
    """Порт LLM-арбитра: выбирает лучший кандидат из топ-K (RAG: generation)."""

    @abstractmethod
    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None: ...


class UserRepository(ABC):
    """Хранилище пользователей."""

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def add(self, user: User) -> User: ...


class PasswordHasher(ABC):
    """Хеширование и проверка паролей."""

    @abstractmethod
    def hash(self, plain: str) -> str: ...

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool: ...


class TokenService(ABC):
    """Выпуск и разбор JWT."""

    @abstractmethod
    def issue(self, user: User) -> str: ...

    @abstractmethod
    def decode(self, token: str) -> TokenPayload: ...


class ArticleImportRepository(ABC):
    """Снимок справочника и атомарное применение плана импорта."""

    @abstractmethod
    def load_existing(self) -> list[ExistingArticle]: ...

    @abstractmethod
    def apply_plan(self, plan: ImportPlan) -> None: ...


class EmbeddingQueueRepository(ABC):
    """Очередь векторизации = строки template_articles с embedding IS NULL."""

    @abstractmethod
    def fetch_pending(self, limit: int) -> list[PendingEmbedding]: ...

    @abstractmethod
    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        """Compare-and-swap: пишет вектор только если embedding_input не изменился."""
        ...

    @abstractmethod
    def try_embed_lock(self) -> bool:
        """Неблокирующий singleton-лок эмбеддинга справочника (константный ключ). False → занят."""
        ...

    @abstractmethod
    def release_embed_lock(self) -> None: ...


class TaskQueue(ABC):
    """Постановка фоновых задач (Celery). Методы → None (без task-id — абстракция не течёт)."""

    @abstractmethod
    def enqueue_match(self, estimate_id: int) -> None: ...

    @abstractmethod
    def enqueue_articles_embed(self) -> None: ...


class EstimateRepository(ABC):
    """Хранилище смет: создание (смета + узлы), список/чтение/удаление с владением."""

    @abstractmethod
    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate: ...

    @abstractmethod
    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]: ...

    @abstractmethod
    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None: ...

    @abstractmethod
    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        """Удаляет смету (каскад строк). Возвращает original_object_key или None
        (не найдена/чужая)."""
        ...

    @abstractmethod
    def try_matching_lock(self, estimate_id: int) -> bool:
        """Неблокирующий session-level advisory-lock. False → занят (no-op)."""
        ...

    @abstractmethod
    def release_matching_lock(self, estimate_id: int) -> None: ...

    @abstractmethod
    def set_status(
        self, estimate_id: int, status: EstimateStatus, detail: str | None = None
    ) -> None:
        """Пишет статус + status_detail, бампает updated_at."""
        ...

    @abstractmethod
    def touch(self, estimate_id: int) -> None:
        """Heartbeat: бамп updated_at без смены статуса."""
        ...

    @abstractmethod
    def get_status(self, estimate_id: int) -> str | None: ...

    @abstractmethod
    def fetch_unembedded_nodes(
        self, estimate_id: int, after_id: int, limit: int
    ) -> list[PendingEmbedding]:
        """Узлы estimate с embedding IS NULL, id > after_id (keyset-курсор), по возрастанию id."""
        ...

    @abstractmethod
    def save_node_embedding(
        self, node_id: int, embedding_input: str, vector: list[float]
    ) -> bool:
        """CAS по embedding_input. True — записан."""
        ...

    @abstractmethod
    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        """status ∈ {pending, error, no_match} И embedding IS NOT NULL
        И review_status = 'unreviewed' (ручные правки SP3 не перематчиваются)."""
        ...

    @abstractmethod
    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        """Перезаписывает весь AI-снимок узла (status/matched_*/score/candidates),
        НО только WHERE review_status='unreviewed' (CAS). На успехе match_error→NULL."""
        ...

    @abstractmethod
    def count_node_errors(self, estimate_id: int) -> int:
        """Строго WHERE status='error'."""
        ...

    @abstractmethod
    def count_unfinished_nodes(self, estimate_id: int) -> int:
        """WHERE status='pending' (вектор не записался / не обработан)."""
        ...


class ObjectStorage(ABC):
    """Объектное хранилище (MinIO/S3) для исходных файлов."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
