"""Порты (абстрактные интерфейсы) доменного слоя.

Слой приложения (services) зависит ТОЛЬКО от этих абстракций — это Dependency
Inversion Principle. Конкретные реализации живут в infrastructure/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.domain.decision_fund import AppliedFundHit, FundEntry, FundHit
from app.domain.entities import (
    ArticleCandidate,
    BenchmarkNodeSeed,
    ClassifiableNode,
    Estimate,
    EstimateNode,
    EstimateStatus,
    EstimateSummary,
    ExistingArticle,
    ImportPlan,
    MatchableNode,
    NewEstimate,
    NodeClassification,
    NodeMatch,
    NodeToClassify,
    PendingEmbedding,
    PendingNode,
    PromotableRow,
    TemplateArticle,
    TokenPayload,
    User,
    WorkClass,
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
    def get_by_id(self, article_id: int) -> TemplateArticle | None: ...

    @abstractmethod
    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        """Лексический поиск code ILIKE %q% OR name ILIKE %q% (НЕ фильтрует по embedding)."""
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
    def is_stale_running(self, estimate_id: int, max_age_seconds: int) -> bool:
        """True, если status='running' и updated_at старше max_age_seconds (мёртвый прогон)."""
        ...

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
    def save_review_decision(
        self,
        node_id: int,
        *,
        review_status: str,
        final_article_id: int | None,
        final_code: str | None,
        final_name: str | None,
    ) -> None:
        """Пишет ось ревью + reviewed_at=now(). Авторитетна — без условия на текущий
        review_status (оператор может передумать). AI-снимок не трогает."""
        ...

    @abstractmethod
    def count_node_errors(self, estimate_id: int) -> int:
        """Строго WHERE status='error'."""
        ...

    @abstractmethod
    def count_unfinished_nodes(self, estimate_id: int) -> int:
        """WHERE status='pending' (вектор не записался / не обработан)."""
        ...

    @abstractmethod
    def get_object_key(
        self, estimate_id: int, requester_id: int, *, is_admin: bool
    ) -> str | None:
        """original_object_key с проверкой владения (None — не найдена/чужая)."""
        ...

    @abstractmethod
    def fetch_all_nodes(self, estimate_id: int) -> list[ClassifiableNode]:
        """Все узлы сметы (id, code, name) по возрастанию source_index."""
        ...

    @abstractmethod
    def save_node_classifications(self, results: list[NodeClassification]) -> None:
        """Bulk, один commit. Охрана: пишет только строки в status IN ('pending','excluded');
        excluded=True→'excluded', False→'pending'. Терминальные матч-статусы/ревью не трогает."""
        ...

    @abstractmethod
    def set_reference(self, estimate_id: int, value: bool) -> None:
        """Помечает/снимает смету как эталонную (источник промоушена в золотой фонд)."""
        ...

    @abstractmethod
    def is_reference(self, estimate_id: int) -> bool:
        """Факт из БД: состоит ли смета в золотом фонде (is_reference)."""
        ...

    @abstractmethod
    def fetch_reference_estimate_ids(self) -> list[int]:
        """Все id смет с is_reference=True."""
        ...

    @abstractmethod
    def fetch_promotable_rows(self, estimate_id: int) -> list[PromotableRow]:
        """Все строки сметы с полями, нужными для отбора кандидатов на промоушен в фонд."""
        ...

    @abstractmethod
    def fetch_pending_nodes(self, estimate_id: int) -> list[PendingNode]:
        """Узлы status='pending' И review_status='unreviewed' (кандидаты на fund-look-up)."""
        ...

    @abstractmethod
    def save_fund_hits(self, hits: Sequence[AppliedFundHit]) -> None:
        """Пишет снимки «решено фондом» (matched_fund) в обход арбитра. CAS по
        review_status='unreviewed' на каждую строку — как save_node_match;
        candidates/score обнуляются (снимок без кандидатов). Один commit на батч
        (зеркало save_node_classifications)."""
        ...


class ObjectStorage(ABC):
    """Объектное хранилище (MinIO/S3) для исходных файлов."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Возвращает содержимое объекта. Кидает StorageError на сбой или отсутствие объекта."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None: ...


class WorkTypeClassifier(ABC):
    """Порт классификатора вид-работ/оргструктура (дешёвая LLM, отдельно от арбитра)."""

    @abstractmethod
    def classify(self, items: list[NodeToClassify]) -> list[WorkClass]:
        """Возврат выровнен по items. При сбое/неоднозначности → WorkClass.UNSURE."""
        ...


class DecisionFundRepository(ABC):
    """Золотой фонд решений: exact-match кэш подтверждённых человеком сопоставлений."""

    @abstractmethod
    def lookup(
        self, key_hashes: Sequence[str], crumb_version: int
    ) -> dict[str, list[FundHit]]:
        """Живые попадания (article_id жив в каталоге) по хешам ключей строго для версии."""
        ...

    @abstractmethod
    def upsert(self, entries: Sequence[FundEntry]) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...


class BenchmarkRepository(ABC):
    """Хранилище gold-разметки (бенчмарков) для оффлайн-метрики матчинга."""

    @abstractmethod
    def create(self, name: str, nodes: list[BenchmarkNodeSeed]) -> int:
        """Создаёт бенчмарк со всеми узлами, возвращает benchmark_id."""
        ...

    @abstractmethod
    def get_by_name(self, name: str) -> int | None: ...

    @abstractmethod
    def list_benchmarks(self) -> list[tuple[int, str]]: ...

    @abstractmethod
    def fetch_nodes(self, benchmark_id: int) -> list[BenchmarkNodeSeed]:
        """Все узлы бенчмарка по возрастанию source_index."""
        ...
