# SP2: асинхронный матчинг смет (Celery) + честный score — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Асинхронно эмбеддить узлы сметы и сопоставлять их со справочником (порог→LLM-арбитр) через Celery+Redis, сохраняя иммутабельный снимок статьи + честный `score`, ведя статусы строк и сметы; единый воркер на матчинг и эмбеддинг справочника.

**Architecture:** Clean Architecture. Порт `TaskQueue` над Celery; Celery-приложение/задачи в `infrastructure/`; чистые сервисы (`MatchingService.match_one`, `EstimateMatchingService.match_estimate`) зависят от портов. Источник правды — Postgres (без Celery result backend). Транзиент гасится инлайн в адаптерах; gate-неготовность справочника — bounded retry в тонкой обёртке через доменный `DictionaryNotReadyError`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic, pgvector, Celery + Redis (managed Timeweb), pytest.

**Спека:** [docs/superpowers/specs/2026-06-23-estimate-matching-sp2-design.md](../specs/2026-06-23-estimate-matching-sp2-design.md)

## Global Constraints

- **Clean Architecture:** `api → services → domain ← infrastructure`. Домен без импортов FastAPI/SQLAlchemy/SDK/Celery. Порт в `domain/ports.py` → реализация в `infrastructure/`.
- **ruff:** line-length 100, `target py311`, `from __future__ import annotations` в каждом модуле, type hints обязательны. `cd backend && uv run ruff check .` перед коммитом.
- **Тесты не ходят в реальную БД/AI/Redis/MinIO** — фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)) + `app.dependency_overrides`; Celery-обёртки — `task_always_eager` либо прямой вызов сервиса.
- **Зависимости — только через `uv add`** (не править `pyproject.toml` руками).
- **Кириллица в stdout:** при ручном прогоне Python ставить `PYTHONIOENCODING=utf-8`.
- **Команды из `backend/`:** `cd backend && uv run pytest ...`.
- **Миграцию `0004` на боевую БД применяет человек** вручную (`just migrate`) — НЕ субагент. В тестах БД не поднимается (тест проверяет лишь метаданные ORM).
- **`score` — это similarity** (`1 - cosine_distance`, выше = лучше); порог `confidence_threshold=0.90`.
- **Снимок матчинга иммутабелен** после записи; ре-матч трогает только `{pending, error, no_match}`.
- **Без result backend Celery**; `TaskQueue`-методы возвращают `None` (не task-id).

## File Structure

- `backend/pyproject.toml` (modify, через `uv add`) — зависимость `celery[redis]`.
- `backend/app/core/config.py` (modify) — `celery_broker_url`, тайм-лимиты, транзиент-бюджет, gate-retry.
- `backend/alembic/versions/0004_estimate_match_snapshot.py` (create) — миграция.
- `backend/app/infrastructure/db/models.py` (modify) — снимок на `EstimateRowModel`, `status_detail` на `EstimateModel`.
- `backend/app/domain/entities.py` (modify) — `EstimateRowStatus`, `EstimateStatus`, `MatchCandidate`, `NodeMatch`, `MatchableNode`.
- `backend/app/domain/errors.py` (modify) — `TransientError`, `DictionaryNotReadyError`.
- `backend/app/domain/ports.py` (modify) — `TaskQueue`; расширения `EstimateRepository`, `ArticleRepository`.
- `backend/app/services/matching_service.py` (modify) — ядро `match_one`, удаление `match_row/match_rows`.
- `backend/app/services/estimate_matching_service.py` (create) — оркестрация `match_estimate` + `mark_blocked`.
- `backend/app/services/article_embedding_service.py` (create) — `drain_articles` (drain-to-zero).
- `backend/app/infrastructure/retry.py` (create) — `retry_transient` (бюджет + классификация транзиента).
- `backend/app/infrastructure/ai/openrouter_embedder.py`, `anthropic_matcher.py` (modify) — таймауты + бюджет + `TransientError`/структурный→`None`.
- `backend/app/infrastructure/db/estimate_repository.py` (modify) — методы SP2 (lock/status/embed/match/счётчики/touch/mark_blocked).
- `backend/app/infrastructure/db/article_repository.py` (modify) — `matching_readiness`.
- `backend/app/infrastructure/tasks/__init__.py`, `celery_app.py`, `tasks.py`, `task_queue.py` (create) — Celery-приложение, задачи, `CeleryTaskQueue`.
- `backend/app/api/deps.py` (modify) — DI для `TaskQueue`/`EstimateMatchingService`; проводка `TaskQueue` в `EstimateService`.
- `backend/app/services/estimate_service.py` (modify) — `enqueue_match` после коммита.
- `backend/app/api/routes/estimates.py` (modify) — `POST /{id}/match`, снятие `POST /estimates/match`.
- `backend/app/api/routes/articles.py` (modify) — `POST /articles/embed` + enqueue в импорте/создании.
- `backend/app/api/schemas.py` (modify) — `matched_*`/`score`/`status_detail` в DTO.
- `backend/tests/fakes.py` (modify) — `FakeTaskQueue`, методы SP2 в `FakeEstimateRepository`/`FakeRepository`, бюджет в `FakeEmbedder`/`FakeLLMMatcher`.
- `backend/tests/test_*` (create/modify) — по задачам.
- `backend/app/services/excel_parser.py`, `backend/app/scripts/embed_worker.py` (delete, Task 12) — снятие старого пути.
- `justfile` (modify) — рецепт `match-worker`/`celery-worker`; снятие `embed-worker`.

---

## Task 1: Конфиг Celery/Redis + тайм-лимиты + gate-retry + зависимость celery

**Files:**
- Modify: `backend/pyproject.toml` (через `uv add`)
- Modify: `backend/app/core/config.py:39-44`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.celery_broker_url`, `.task_soft_time_limit_s`, `.task_time_limit_s`, `.ai_call_timeout_s`, `.transient_retry_budget`, `.gate_retry_max`, `.gate_retry_backoff_s`.

- [ ] **Step 1: Добавить зависимость celery[redis]**

Run: `cd backend && uv add "celery[redis]"`
Expected: `celery` + `redis` в `pyproject.toml [project.dependencies]`, `uv.lock` обновлён.

- [ ] **Step 2: Failing-тест на новые поля конфига**

Дописать в `backend/tests/test_config.py`:

```python
def test_settings_have_celery_and_matching_knobs() -> None:
    from app.core.config import Settings

    s = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert s.celery_broker_url  # непустой дефолт
    assert s.task_time_limit_s > s.task_soft_time_limit_s
    assert s.ai_call_timeout_s > 0
    assert s.transient_retry_budget >= 1
    assert s.gate_retry_max >= 1
    assert s.gate_retry_backoff_s > 0
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend && uv run pytest tests/test_config.py::test_settings_have_celery_and_matching_knobs -v`
Expected: FAIL (`AttributeError`/`ValidationError`).

- [ ] **Step 4: Добавить поля в Settings**

В `backend/app/core/config.py` после `estimate_max_upload_mb` добавить:

```python
    # Celery / Redis (брокер на Timeweb). Result backend НЕ используется — БД источник правды.
    celery_broker_url: str = "redis://localhost:6379/0"

    # Тайм-лимиты задачи матчинга (от них зависит истинность семантики running):
    # зависший воркер → SIGKILL/исключение → коннект рвётся → PG отпускает advisory-lock.
    task_soft_time_limit_s: int = 600
    task_time_limit_s: int = 660

    # Инлайн-обработка транзиента в адаптерах эмбеддера/LLM:
    ai_call_timeout_s: float = 30.0       # hard per-call timeout
    transient_retry_budget: int = 3       # попыток на один вызов до TransientError

    # Bounded gate-retry: ожидание готовности справочника (DictionaryNotReadyError → self.retry).
    gate_retry_max: int = 30
    gate_retry_backoff_s: float = 20.0
```

- [ ] **Step 5: Прокинуть дефолт брокера в тестовое окружение**

В `backend/tests/conftest.py` дописать (Celery импортируется при старте, реальный Redis не дёргается):

```python
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
```

- [ ] **Step 6: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_config.py -v && uv run ruff check app/core/config.py`
Expected: PASS, ruff чисто.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/conftest.py backend/tests/test_config.py
git commit -m "feat(matching): конфиг Celery/Redis + тайм-лимиты + gate-retry, зависимость celery[redis]"
```

---

## Task 2: Миграция 0004 + ORM-снимок матчинга

**Files:**
- Create: `backend/alembic/versions/0004_estimate_match_snapshot.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Test: `backend/tests/test_estimate_models.py`

**Interfaces:**
- Produces: колонки `estimate_rows.{matched_article_id, matched_code, matched_name, score, candidates, match_error}`, `estimates.status_detail`.

- [ ] **Step 1: Написать миграцию 0004 (raw SQL, как 0003)**

Create `backend/alembic/versions/0004_estimate_match_snapshot.py`:

```python
"""estimate match snapshot columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE estimate_rows
            ADD COLUMN matched_article_id INTEGER,
            ADD COLUMN matched_code        VARCHAR(64),
            ADD COLUMN matched_name        TEXT,
            ADD COLUMN score               DOUBLE PRECISION,
            ADD COLUMN candidates          JSONB,
            ADD COLUMN match_error         TEXT
        """
    )
    op.execute("ALTER TABLE estimates ADD COLUMN status_detail TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE estimates DROP COLUMN IF EXISTS status_detail")
    op.execute(
        """
        ALTER TABLE estimate_rows
            DROP COLUMN IF EXISTS matched_article_id,
            DROP COLUMN IF EXISTS matched_code,
            DROP COLUMN IF EXISTS matched_name,
            DROP COLUMN IF EXISTS score,
            DROP COLUMN IF EXISTS candidates,
            DROP COLUMN IF EXISTS match_error
        """
    )
```

> **Заметка:** `matched_article_id` — plain `INTEGER` **без FK** (иммутабельность снимка; SERIAL не переиспользуется; каскад/RESTRICT противопоказаны). Паритет миграция↔ORM нигде не ассертится (тест проверяет лишь метаданные ORM) — как в `0001`/`0003`.

- [ ] **Step 2: Добавить колонки в ORM**

В `backend/app/infrastructure/db/models.py` в шапку импортов sqlalchemy добавить `Double` (если нет) и `from sqlalchemy.dialects.postgresql import JSONB`. В `EstimateRowModel` после `status` добавить:

```python
    matched_article_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Double, nullable=True)
    candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    match_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

В `EstimateModel` после `status` добавить:

```python
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 3: Failing-тест на ORM-метаданные**

Дописать в `backend/tests/test_estimate_models.py`:

```python
def test_estimate_match_snapshot_columns() -> None:
    from app.infrastructure.db.models import EstimateModel, EstimateRowModel

    rcols = set(EstimateRowModel.__table__.columns.keys())
    assert {"matched_article_id", "matched_code", "matched_name",
            "score", "candidates", "match_error"} <= rcols
    assert "status_detail" in EstimateModel.__table__.columns.keys()
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_estimate_models.py -v`
Expected: PASS.

- [ ] **Step 5: ruff**

Run: `cd backend && uv run ruff check app/infrastructure/db/models.py backend/alembic/versions/0004_estimate_match_snapshot.py tests/test_estimate_models.py`
Expected: чисто.

- [ ] **Step 6: Commit** (миграцию на боевой БД применяет `just migrate` вручную)

```bash
git add backend/alembic/versions/0004_estimate_match_snapshot.py backend/app/infrastructure/db/models.py backend/tests/test_estimate_models.py
git commit -m "feat(matching): миграция 0004 — снимок матчинга на estimate_rows + status_detail"
```

---

## Task 3: Доменные сущности статусов/снимка + ошибки

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/domain/errors.py`
- Test: `backend/tests/test_match_entities.py`

**Interfaces:**
- Produces: `EstimateRowStatus`, `EstimateStatus` (StrEnum-слаги); `MatchCandidate(id, code, name, score)`; `NodeMatch(status, matched_id, matched_code, matched_name, score, candidates, match_error)`; `MatchableNode(id, embedding, embedding_input)`; ошибки `TransientError`, `DictionaryNotReadyError(total, pending)`.

- [ ] **Step 1: Добавить сущности**

В `backend/app/domain/entities.py` добавить (рядом с существующими `StrEnum`/dataclass-импортами):

```python
class EstimateRowStatus(StrEnum):
    """Статус узла сметы при матчинге (слаг — для хранения; рус.подписи в API-DTO)."""

    PENDING = "pending"
    CONFIDENT = "confident"
    NEEDS_REVIEW = "needs_review"
    NO_MATCH = "no_match"
    ERROR = "error"


class EstimateStatus(StrEnum):
    """Статус сметы в пайплайне матчинга."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    PARTIAL_ERROR = "partial_error"
    BLOCKED = "blocked"


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
```

- [ ] **Step 2: Добавить доменные ошибки**

В `backend/app/domain/errors.py` добавить:

```python
class TransientError(Exception):
    """Транзиентный сбой внешнего вызова (сеть/429/таймаут) — исчерпан инлайн-бюджет ретраев."""


class DictionaryNotReadyError(Exception):
    """Справочник не полностью заэмбежен — матчинг производить нельзя (gate)."""

    def __init__(self, total: int, pending: int) -> None:
        self.total = total
        self.pending = pending
        super().__init__(f"справочник не готов: total={total} pending={pending}")
```

- [ ] **Step 3: Failing-тест**

Create `backend/tests/test_match_entities.py`:

```python
from __future__ import annotations

from app.domain.entities import (
    EstimateRowStatus,
    EstimateStatus,
    MatchCandidate,
    NodeMatch,
)
from app.domain.errors import DictionaryNotReadyError, TransientError


def test_status_slugs() -> None:
    assert EstimateRowStatus.NEEDS_REVIEW == "needs_review"
    assert EstimateStatus.PARTIAL_ERROR == "partial_error"


def test_node_match_defaults() -> None:
    nm = NodeMatch(EstimateRowStatus.NO_MATCH)
    assert nm.score is None and nm.candidates == [] and nm.matched_id is None


def test_node_match_confident() -> None:
    c = MatchCandidate(id=5, code="1.1", name="X", score=0.95)
    nm = NodeMatch(EstimateRowStatus.CONFIDENT, 5, "1.1", "X", 0.95, [c])
    assert nm.matched_code == "1.1" and nm.candidates[0].id == 5


def test_dictionary_not_ready_carries_counts() -> None:
    e = DictionaryNotReadyError(total=10, pending=3)
    assert e.total == 10 and e.pending == 3
    assert isinstance(TransientError("x"), Exception)
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_match_entities.py -v && uv run ruff check app/domain/entities.py app/domain/errors.py tests/test_match_entities.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/errors.py backend/tests/test_match_entities.py
git commit -m "feat(matching): доменные статусы/снимок (NodeMatch) + ошибки TransientError/DictionaryNotReadyError"
```

---

## Task 4: Рефактор `MatchingService` → ядро `match_one`

**Files:**
- Modify: `backend/app/services/matching_service.py`
- Modify: `backend/tests/test_matching_service.py`

**Interfaces:**
- Consumes: `ArticleRepository.search_similar`, `LLMMatcher.choose_best`, `ArticleCandidate`, `NodeMatch`, `MatchCandidate`, `EstimateRowStatus`.
- Produces: `MatchingService.match_one(embedding: list[float], query_text: str) -> NodeMatch`.
- Removes: `MatchingService.match_row`, `MatchingService.match_rows`.

- [ ] **Step 1: Failing-тесты ядра**

Заменить содержимое `backend/tests/test_matching_service.py` на:

```python
from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateRowStatus,
    TemplateArticle,
)
from app.services.matching_service import MatchingService
from tests.fakes import FakeLLMMatcher, FakeRepository


def _article(aid: int, code: str) -> TemplateArticle:
    return TemplateArticle(id=aid, article_code=code, name=f"имя {code}", embedding_input=f"ei {code}")


def _svc(candidates, llm=None, threshold=0.90):
    repo = FakeRepository(candidates=candidates)
    return MatchingService(repo, embedder=None, llm_matcher=llm or FakeLLMMatcher(), confidence_threshold=threshold)


def test_no_candidates_is_no_match() -> None:
    nm = _svc([]).match_one([0.1, 0.2], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH and nm.score is None and nm.candidates == []


def test_high_score_is_confident_top1() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.97), ArticleCandidate(_article(2, "1.2"), 0.5)]
    nm = _svc(cands).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.CONFIDENT
    assert nm.matched_id == 1 and nm.matched_code == "1.1" and nm.score == 0.97
    assert [c.id for c in nm.candidates] == [1, 2]  # снимок топ-K с id


def test_low_score_llm_pick_is_needs_review_with_chosen_score() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80), ArticleCandidate(_article(2, "1.2"), 0.70)]
    nm = _svc(cands, llm=FakeLLMMatcher(pick_index=1)).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NEEDS_REVIEW
    assert nm.matched_id == 2 and nm.score == 0.70  # косинус ВЫБРАННОГО, не top-1


def test_llm_declines_is_no_match_keeps_candidates() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80)]

    class _Decline(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            return None

    nm = _svc(cands, llm=_Decline()).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH and nm.score is None
    assert len(nm.candidates) == 1  # кандидаты сохранены для SP3


def test_llm_hallucinated_article_treated_as_decline() -> None:
    cands = [ArticleCandidate(_article(1, "1.1"), 0.80)]

    class _Halluc(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            return TemplateArticle(id=999, article_code="9.9", name="фейк", embedding_input="x")

    nm = _svc(cands, llm=_Halluc()).match_one([0.1], "запрос")
    assert nm.status is EstimateRowStatus.NO_MATCH  # не из кандидатов → как отказ
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_matching_service.py -v`
Expected: FAIL (`match_one` нет / старый API).

- [ ] **Step 3: Реализовать ядро**

Заменить тело `backend/app/services/matching_service.py` на:

```python
"""Ядро сопоставления узла со справочником (RAG: retrieval + LLM-арбитраж).

Принимает ГОТОВЫЙ вектор узла (не ре-эмбеддит). query_text (= embedding_input узла) идёт
только в LLM-арбитр. Возвращает NodeMatch со слаг-статусом и снимком кандидатов.
"""

from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateRowStatus,
    MatchCandidate,
    NodeMatch,
    TemplateArticle,
)
from app.domain.ports import ArticleRepository, Embedder, LLMMatcher


def _snapshot(candidates: list[ArticleCandidate]) -> list[MatchCandidate]:
    return [
        MatchCandidate(id=c.article.id, code=c.article.article_code, name=c.article.name, score=c.score)
        for c in candidates
    ]


class MatchingService:
    def __init__(
        self,
        repository: ArticleRepository,
        embedder: Embedder | None = None,  # больше не используется ядром (сметы хранят вектор)
        llm_matcher: LLMMatcher | None = None,
        confidence_threshold: float = 0.90,
        top_k: int = 3,
    ) -> None:
        self._repository = repository
        self._llm_matcher = llm_matcher
        self._threshold = confidence_threshold
        self._top_k = top_k

    def match_one(self, embedding: list[float], query_text: str) -> NodeMatch:
        candidates = self._repository.search_similar(embedding, top_k=self._top_k)
        if not candidates:
            return NodeMatch(EstimateRowStatus.NO_MATCH)
        snap = _snapshot(candidates)
        best = candidates[0]
        if best.score > self._threshold:
            return NodeMatch(
                EstimateRowStatus.CONFIDENT, best.article.id, best.article.article_code,
                best.article.name, best.score, snap,
            )
        chosen = self._llm_matcher.choose_best(query_text, candidates) if self._llm_matcher else None
        chosen_score = self._score_of(chosen, candidates)
        if chosen is None or chosen_score is None:   # отказ / галлюцинация вне кандидатов
            return NodeMatch(EstimateRowStatus.NO_MATCH, candidates=snap)
        return NodeMatch(
            EstimateRowStatus.NEEDS_REVIEW, chosen.id, chosen.article_code,
            chosen.name, chosen_score, snap,
        )

    @staticmethod
    def _score_of(chosen: TemplateArticle | None, candidates: list[ArticleCandidate]) -> float | None:
        if chosen is None:
            return None
        for c in candidates:                          # валидация: chosen ДОЛЖЕН быть из кандидатов
            if c.article.id == chosen.id and c.article.article_code == chosen.article_code:
                return c.score
        return None                                   # «придуманная» статья → трактуем как отказ
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_matching_service.py -v && uv run ruff check app/services/matching_service.py tests/test_matching_service.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/matching_service.py backend/tests/test_matching_service.py
git commit -m "refactor(matching): ядро match_one(embedding, query_text) без ре-эмбеддинга + валидация арбитра"
```

---

## Task 5: Порты SP2 (`TaskQueue`, расширения репозиториев) + фейки

**Files:**
- Modify: `backend/app/domain/ports.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_match_fakes.py`

**Interfaces:**
- Produces (ports): `TaskQueue.enqueue_match(estimate_id) -> None`, `.enqueue_articles_embed() -> None`; `ArticleRepository.matching_readiness() -> tuple[int, int]`; `EstimateRepository` методы: `try_matching_lock(id) -> bool`, `release_matching_lock(id) -> None`, `set_status(id, status, detail=None) -> None`, `touch(id) -> None`, `get_status(id) -> str | None`, `fetch_unembedded_nodes(id, after_id, limit) -> list[PendingEmbedding]`, `save_node_embedding(node_id, embedding_input, vector) -> bool`, `fetch_matchable_nodes(id) -> list[MatchableNode]`, `save_node_match(node_id, NodeMatch) -> None`, `count_node_errors(id) -> int`, `count_unfinished_nodes(id) -> int`.
- Produces (fakes): `FakeTaskQueue`, расширенный `FakeEstimateRepository`, `FakeRepository.matching_readiness`.

- [ ] **Step 1: Расширить порты**

В `backend/app/domain/ports.py` добавить импорты `EstimateRowStatus, EstimateStatus, MatchableNode, NodeMatch, PendingEmbedding` к существующим из `entities`, и классы/методы:

```python
class TaskQueue(ABC):
    """Постановка фоновых задач (Celery). Методы → None (без task-id — абстракция не течёт)."""

    @abstractmethod
    def enqueue_match(self, estimate_id: int) -> None: ...

    @abstractmethod
    def enqueue_articles_embed(self) -> None: ...
```

В `ArticleRepository` добавить абстрактный метод:

```python
    @abstractmethod
    def matching_readiness(self) -> tuple[int, int]:
        """(total, pending): всего статей и сколько с embedding IS NULL. Для gate матчинга."""
        ...
```

В `EstimateRepository` добавить абстрактные методы:

```python
    @abstractmethod
    def try_matching_lock(self, estimate_id: int) -> bool:
        """Неблокирующий session-level advisory-lock. False → занят (no-op)."""
        ...

    @abstractmethod
    def release_matching_lock(self, estimate_id: int) -> None: ...

    @abstractmethod
    def set_status(self, estimate_id: int, status: EstimateStatus, detail: str | None = None) -> None:
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
    def save_node_embedding(self, node_id: int, embedding_input: str, vector: list[float]) -> bool:
        """CAS по embedding_input. True — записан."""
        ...

    @abstractmethod
    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        """status ∈ {pending, error, no_match} И embedding IS NOT NULL."""
        ...

    @abstractmethod
    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        """Перезаписывает весь снимок узла (status/matched_*/score/candidates); на успехе match_error→NULL."""
        ...

    @abstractmethod
    def count_node_errors(self, estimate_id: int) -> int:
        """Строго WHERE status='error'."""
        ...

    @abstractmethod
    def count_unfinished_nodes(self, estimate_id: int) -> int:
        """WHERE status='pending' (вектор не записался / не обработан)."""
        ...
```

- [ ] **Step 2: Реализовать фейки**

В `backend/tests/fakes.py`:

(а) добавить импорты `EstimateRowStatus, EstimateStatus, MatchableNode, NodeMatch, PendingEmbedding` и `TaskQueue` к существующим.

(б) добавить `FakeTaskQueue`:

```python
class FakeTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self.match_calls: list[int] = []
        self.articles_embed_calls = 0

    def enqueue_match(self, estimate_id: int) -> None:
        self.match_calls.append(estimate_id)

    def enqueue_articles_embed(self) -> None:
        self.articles_embed_calls += 1
```

(в) `matching_readiness` в `FakeRepository` (после `search_similar`):

```python
    def matching_readiness(self) -> tuple[int, int]:
        total = len(self._store)
        pending = sum(1 for a in self._store if a.embedding is None)
        return total, pending
```

(г) расширить `FakeEstimateRepository` — заменить класс на потоковую in-memory модель с узлами-словарями (полнее, чем SP1-версия). В `__init__` добавить структуры и lock/heartbeat-учёт; добавить методы SP2. Полный новый класс:

```python
class FakeEstimateRepository(EstimateRepository):
    def __init__(self) -> None:
        self.estimates: dict[int, Estimate] = {}
        self._keys: dict[int, str] = {}
        self._next = 1
        self.create_calls = 0
        # SP2: узлы как изменяемые словари + статус/детали/лок/таймстамп
        self.nodes: dict[int, dict] = {}              # node_id -> {estimate_id, embedding_input, embedding, status, snapshot...}
        self.statuses: dict[int, str] = {}            # estimate_id -> status
        self.details: dict[int, str | None] = {}
        self.touch_count: dict[int, int] = {}
        self._locks: set[int] = set()
        self._node_seq = 0

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        self.create_calls += 1
        eid = self._next
        self._next += 1
        rows = []
        for n in nodes:
            self._node_seq += 1
            nid = self._node_seq
            self.nodes[nid] = {
                "id": nid, "estimate_id": eid, "embedding_input": n.embedding_input,
                "embedding": None, "status": "pending", "match_error": None,
            }
            rows.append(StoredEstimateRow(
                id=nid, code=n.code, name=n.name, parent_code=n.parent_code,
                section_type=n.section_type, depth=n.depth, embedding_input=n.embedding_input,
                source_index=n.source_index, status="pending", has_embedding=False,
            ))
        est = Estimate(id=eid, user_id=new.user_id, filename=new.filename, status="pending",
                       created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), rows=rows)  # noqa: UP017
        self.estimates[eid] = est
        self.statuses[eid] = "pending"
        self.details[eid] = None
        self.touch_count[eid] = 0
        self._keys[eid] = new.original_object_key
        return est

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return [
            EstimateSummary(id=e.id, filename=e.filename, status=self.statuses.get(e.id, e.status),
                            nodes_count=len(e.rows), created_at=e.created_at)
            for e in self.estimates.values() if is_admin or e.user_id == owner_id
        ]

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        return est

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        self.estimates.pop(estimate_id)
        return self._keys.pop(estimate_id)

    # --- SP2 ---
    def try_matching_lock(self, estimate_id: int) -> bool:
        if estimate_id in self._locks:
            return False
        self._locks.add(estimate_id)
        return True

    def release_matching_lock(self, estimate_id: int) -> None:
        self._locks.discard(estimate_id)

    def set_status(self, estimate_id: int, status, detail: str | None = None) -> None:
        self.statuses[estimate_id] = str(status)
        self.details[estimate_id] = detail
        self.touch_count[estimate_id] = self.touch_count.get(estimate_id, 0) + 1

    def touch(self, estimate_id: int) -> None:
        self.touch_count[estimate_id] = self.touch_count.get(estimate_id, 0) + 1

    def get_status(self, estimate_id: int) -> str | None:
        return self.statuses.get(estimate_id)

    def fetch_unembedded_nodes(self, estimate_id: int, after_id: int, limit: int) -> list[PendingEmbedding]:
        rows = sorted(
            (n for n in self.nodes.values()
             if n["estimate_id"] == estimate_id and n["embedding"] is None and n["id"] > after_id),
            key=lambda n: n["id"],
        )
        return [PendingEmbedding(id=n["id"], embedding_input=n["embedding_input"]) for n in rows[:limit]]

    def save_node_embedding(self, node_id: int, embedding_input: str, vector: list[float]) -> bool:
        n = self.nodes.get(node_id)
        if n is None or n["embedding_input"] != embedding_input:
            return False
        n["embedding"] = vector
        return True

    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        return [
            MatchableNode(id=n["id"], embedding=n["embedding"], embedding_input=n["embedding_input"])
            for n in sorted(self.nodes.values(), key=lambda n: n["id"])
            if n["estimate_id"] == estimate_id
            and n["status"] in ("pending", "error", "no_match")
            and n["embedding"] is not None
        ]

    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        n = self.nodes[node_id]
        n["status"] = str(result.status)
        n["match_error"] = result.match_error  # на успехе result.match_error=None → обнуляется

    def count_node_errors(self, estimate_id: int) -> int:
        return sum(1 for n in self.nodes.values()
                   if n["estimate_id"] == estimate_id and n["status"] == "error")

    def count_unfinished_nodes(self, estimate_id: int) -> int:
        return sum(1 for n in self.nodes.values()
                   if n["estimate_id"] == estimate_id and n["status"] == "pending")
```

- [ ] **Step 3: Failing-тест фейков**

Create `backend/tests/test_match_fakes.py`:

```python
from __future__ import annotations

from app.domain.entities import EstimateNode, EstimateRowStatus, NewEstimate, NodeMatch
from tests.fakes import FakeEstimateRepository, FakeTaskQueue


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, 1)


def test_lock_is_exclusive_and_releasable() -> None:
    repo = FakeEstimateRepository()
    assert repo.try_matching_lock(1) is True
    assert repo.try_matching_lock(1) is False
    repo.release_matching_lock(1)
    assert repo.try_matching_lock(1) is True


def test_embed_keyset_and_cas_and_matchable_filter() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    ids = sorted(n["id"] for n in repo.nodes.values())
    first = repo.fetch_unembedded_nodes(est.id, after_id=0, limit=1)
    assert len(first) == 1 and first[0].id == ids[0]
    # keyset вперёд — тот же id не вернётся
    assert repo.fetch_unembedded_nodes(est.id, after_id=ids[0], limit=10)[0].id == ids[1]
    # CAS-False на чужой embedding_input
    assert repo.save_node_embedding(ids[0], "не тот", [0.1]) is False
    assert repo.save_node_embedding(ids[0], f"ei 1", [0.1]) is True
    # matchable требует embedding IS NOT NULL
    assert [m.id for m in repo.fetch_matchable_nodes(est.id)] == [ids[0]]


def test_save_match_and_counts_clear_error() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    nid = next(iter(repo.nodes))
    repo.save_node_match(nid, NodeMatch(EstimateRowStatus.ERROR, match_error="boom"))
    assert repo.count_node_errors(est.id) == 1
    repo.save_node_match(nid, NodeMatch(EstimateRowStatus.CONFIDENT, 1, "1", "x", 0.95))
    assert repo.count_node_errors(est.id) == 0 and repo.nodes[nid]["match_error"] is None


def test_set_status_and_touch_bump_heartbeat() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    before = repo.touch_count[est.id]
    repo.touch(est.id)
    repo.set_status(est.id, "running")
    assert repo.touch_count[est.id] == before + 2 and repo.get_status(est.id) == "running"


def test_task_queue_records() -> None:
    q = FakeTaskQueue()
    q.enqueue_match(7)
    q.enqueue_articles_embed()
    assert q.match_calls == [7] and q.articles_embed_calls == 1
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_match_fakes.py tests/test_estimate_service.py -v && uv run ruff check app/domain/ports.py tests/fakes.py tests/test_match_fakes.py`
Expected: PASS (включая прежние тесты `test_estimate_service.py`, использующие `FakeEstimateRepository`), ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/ports.py backend/tests/fakes.py backend/tests/test_match_fakes.py
git commit -m "feat(matching): порты TaskQueue + методы матчинга EstimateRepository/ArticleRepository + фейки"
```

---

## Task 6: `EstimateMatchingService` (оркестрация) + `mark_blocked` на фейках

**Files:**
- Create: `backend/app/services/estimate_matching_service.py`
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Consumes: `MatchingService.match_one`, `Embedder.embed_batch`, `EstimateRepository` (методы Task 5), `ArticleRepository.matching_readiness`, `EstimateStatus`, `EstimateRowStatus`, `NodeMatch`, `TransientError`, `DictionaryNotReadyError`.
- Produces: `EstimateMatchingService.match_estimate(estimate_id) -> None`; `.mark_blocked(estimate_id, detail) -> None`.

- [ ] **Step 1: Failing-тесты сервиса**

Create `backend/tests/test_estimate_matching_service.py`:

```python
from __future__ import annotations

from app.domain.entities import (
    ArticleCandidate,
    EstimateNode,
    EstimateStatus,
    NewEstimate,
    TemplateArticle,
)
from app.domain.errors import DictionaryNotReadyError, TransientError
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.matching_service import MatchingService
from tests.fakes import FakeEstimateRepository, FakeLLMMatcher, FakeRepository


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, 1)


def _article(aid: int, code: str, emb: list[float] | None = None) -> TemplateArticle:
    return TemplateArticle(id=aid, article_code=code, name=f"имя {code}",
                           embedding_input=f"ei {code}", embedding=emb or [0.1])


class _Embedder:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed(self, text):  # не используется
        return [0.1]

    def embed_batch(self, texts):
        self.batches.append(list(texts))
        return [[0.1, float(len(t) % 5)] for t in texts]


def _service(repo, articles, *, embedder=None, llm=None):
    matcher = MatchingService(articles, embedder=None, llm_matcher=llm or FakeLLMMatcher())
    return EstimateMatchingService(matcher=matcher, embedder=embedder or _Embedder(),
                                   estimates=repo, articles=articles)


def _ready_articles(candidates) -> FakeRepository:
    art = FakeRepository(candidates=candidates)
    art._store.append(_article(1, "1.1"))  # total>0, pending==0 (embedding задан в _article)
    return art


def test_blocked_when_dictionary_empty_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeRepository(candidates=[])  # total==0
    import pytest
    with pytest.raises(DictionaryNotReadyError):
        _service(repo, art).match_estimate(est.id)
    # embed-шаг всё равно прошёл (узлы заэмбежены — не впустую)
    assert all(n["embedding"] is not None for n in repo.nodes.values())


def test_blocked_when_articles_pending_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeRepository(candidates=[])
    art._store.append(_article(1, "1.1", emb=None))  # pending>0
    import pytest
    with pytest.raises(DictionaryNotReadyError):
        _service(repo, art).match_estimate(est.id)


def test_happy_path_ready_with_confident() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    _service(repo, art).match_estimate(est.id)
    assert repo.get_status(est.id) == EstimateStatus.READY
    assert next(iter(repo.nodes.values()))["status"] == "confident"


def test_locked_estimate_is_noop() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    repo.try_matching_lock(est.id)  # держим лок «другим воркером»
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    _service(repo, art).match_estimate(est.id)
    assert repo.get_status(est.id) == "pending"  # ничего не сделано


def test_node_transient_becomes_error_partial() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.5)])

    class _BoomLLM(FakeLLMMatcher):
        def choose_best(self, query, candidates):
            raise TransientError("429")

    _service(repo, art, llm=_BoomLLM()).match_estimate(est.id)
    assert repo.get_status(est.id) == EstimateStatus.PARTIAL_ERROR
    assert next(iter(repo.nodes.values()))["status"] == "error"


def test_mark_blocked_noop_if_terminal() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    repo.set_status(est.id, EstimateStatus.READY)
    _service(repo, _ready_articles([])).mark_blocked(est.id, "timeout")
    assert repo.get_status(est.id) == EstimateStatus.READY  # не затёрли результат


def test_mark_blocked_sets_blocked_when_not_terminal() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    _service(repo, _ready_articles([])).mark_blocked(est.id, "timeout")
    assert repo.get_status(est.id) == EstimateStatus.BLOCKED
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_estimate_matching_service.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать сервис**

Create `backend/app/services/estimate_matching_service.py`:

```python
"""Оркестрация матчинга одной сметы: embed → gate → match → статус. Зависит только от портов.

Чист от Celery: gate-неготовность сигналит DictionaryNotReadyError (ожидание/blocked решает
тонкая Celery-обёртка). Транзиент узла гасится инлайн в адаптерах (TransientError) и фиксируется
как error поузлово — без проброса в задачу (нет LLM-амплификации).
"""

from __future__ import annotations

from app.domain.entities import EstimateRowStatus, EstimateStatus, NodeMatch
from app.domain.errors import DictionaryNotReadyError, TransientError
from app.domain.ports import ArticleRepository, Embedder, EstimateRepository
from app.services.matching_service import MatchingService

_EMBED_CHUNK = 100
_HEARTBEAT_EVERY = 50
_TERMINAL = (EstimateStatus.READY, EstimateStatus.PARTIAL_ERROR)


class EstimateMatchingService:
    def __init__(
        self,
        matcher: MatchingService,
        embedder: Embedder,
        estimates: EstimateRepository,
        articles: ArticleRepository,
    ) -> None:
        self._matcher = matcher
        self._embedder = embedder
        self._estimates = estimates
        self._articles = articles

    def match_estimate(self, estimate_id: int) -> None:
        if not self._estimates.try_matching_lock(estimate_id):
            return  # конкурент владеет → no-op
        try:
            self._estimates.set_status(estimate_id, EstimateStatus.RUNNING)  # COMMIT до embed
            self._embed_nodes(estimate_id)
            total, pending = self._articles.matching_readiness()
            if total == 0 or pending > 0:
                raise DictionaryNotReadyError(total=total, pending=pending)  # обёртка ретраит/блокирует
            self._match_nodes(estimate_id)
            errors = self._estimates.count_node_errors(estimate_id)
            unfinished = self._estimates.count_unfinished_nodes(estimate_id)
            if errors or unfinished:
                self._estimates.set_status(
                    estimate_id, EstimateStatus.PARTIAL_ERROR,
                    detail=f"errors={errors} unfinished={unfinished}",
                )
            else:
                self._estimates.set_status(estimate_id, EstimateStatus.READY)
        finally:
            self._estimates.release_matching_lock(estimate_id)

    def _embed_nodes(self, estimate_id: int) -> None:
        last_id = 0
        while chunk := self._estimates.fetch_unembedded_nodes(estimate_id, after_id=last_id, limit=_EMBED_CHUNK):
            try:
                vectors = self._embedder.embed_batch([n.embedding_input for n in chunk])
                for node, vector in zip(chunk, vectors, strict=True):
                    self._estimates.save_node_embedding(node.id, node.embedding_input, vector)
            except TransientError:
                pass  # узлы остаются pending → unfinished → partial_error (ре-триггер доберёт)
            self._estimates.touch(estimate_id)  # heartbeat
            last_id = chunk[-1].id

    def _match_nodes(self, estimate_id: int) -> None:
        for i, node in enumerate(self._estimates.fetch_matchable_nodes(estimate_id), start=1):
            try:
                result = self._matcher.match_one(node.embedding, node.embedding_input)
            except TransientError as exc:  # адаптер исчерпал инлайн-бюджет
                result = NodeMatch(EstimateRowStatus.ERROR, match_error=str(exc))
            self._estimates.save_node_match(node.id, result)
            if i % _HEARTBEAT_EVERY == 0:
                self._estimates.touch(estimate_id)

    def mark_blocked(self, estimate_id: int, detail: str) -> None:
        """Вызывается обёрткой при исчерпании gate-retry. Под локом, не затирает реальный результат."""
        if not self._estimates.try_matching_lock(estimate_id):
            return  # активный матчер → no-op
        try:
            if self._estimates.get_status(estimate_id) in _TERMINAL:
                return  # B успел сматчить на границе ретраев → не клоббим
            self._estimates.set_status(estimate_id, EstimateStatus.BLOCKED, detail=detail)
        finally:
            self._estimates.release_matching_lock(estimate_id)
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_matching_service.py -v && uv run ruff check app/services/estimate_matching_service.py tests/test_estimate_matching_service.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/tests/test_estimate_matching_service.py
git commit -m "feat(matching): EstimateMatchingService — embed→gate→match, mark_blocked под локом"
```

---

## Task 7: Реальные адаптеры репозиториев (Postgres)

**Files:**
- Modify: `backend/app/infrastructure/db/estimate_repository.py`
- Modify: `backend/app/infrastructure/db/article_repository.py`
- Test: `backend/tests/test_estimate_repository_mapping.py`

**Interfaces:**
- Produces: SQL-реализации методов Task 5. Реальная БД **не** тестируется юнитами (как `SqlAlchemyArticleRepository`) — проверяется вручную; юнит-тест покрывает чистый маппинг `save_node_match`→values.

- [ ] **Step 1: `matching_readiness` в ArticleRepository**

В `backend/app/infrastructure/db/article_repository.py` добавить метод (использует уже импортированные `func`, `select`):

```python
    def matching_readiness(self) -> tuple[int, int]:
        total = self._session.scalar(select(func.count()).select_from(TemplateArticleModel)) or 0
        pending = self._session.scalar(
            select(func.count()).select_from(TemplateArticleModel).where(
                TemplateArticleModel.embedding.is_(None)
            )
        ) or 0
        return int(total), int(pending)
```

- [ ] **Step 2: Методы SP2 в SqlAlchemyEstimateRepository**

В `backend/app/infrastructure/db/estimate_repository.py` обновить импорты:

```python
from sqlalchemy import delete, func, select, update

from app.domain.entities import (
    Estimate,
    EstimateNode,
    EstimateStatus,
    EstimateSummary,
    MatchableNode,
    NewEstimate,
    NodeMatch,
    PendingEmbedding,
    StoredEstimateRow,
)
```

Добавить константу-namespace и методы в класс:

```python
_NS_MATCH = 0x4D415443  # "MATC" — namespace advisory-лока матчинга сметы


class SqlAlchemyEstimateRepository(EstimateRepository):
    # ... существующие create/list_for_owner/get/delete без изменений ...

    def try_matching_lock(self, estimate_id: int) -> bool:
        # session-level (не xact): держится через инкрементальные коммиты embed-шага на
        # одном коннекте Session; release в finally + close возвращает коннект (лок снят).
        return bool(
            self._session.scalar(select(func.pg_try_advisory_lock(_NS_MATCH, estimate_id)))
        )

    def release_matching_lock(self, estimate_id: int) -> None:
        self._session.scalar(select(func.pg_advisory_unlock(_NS_MATCH, estimate_id)))

    def set_status(self, estimate_id: int, status: EstimateStatus, detail: str | None = None) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(
                status=str(status), status_detail=detail, updated_at=func.now()
            )
        )
        self._session.commit()

    def touch(self, estimate_id: int) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(updated_at=func.now())
        )
        self._session.commit()

    def get_status(self, estimate_id: int) -> str | None:
        return self._session.scalar(
            select(EstimateModel.status).where(EstimateModel.id == estimate_id)
        )

    def fetch_unembedded_nodes(
        self, estimate_id: int, after_id: int, limit: int
    ) -> list[PendingEmbedding]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.embedding_input)
            .where(
                EstimateRowModel.estimate_id == estimate_id,
                EstimateRowModel.embedding.is_(None),
                EstimateRowModel.id > after_id,
            )
            .order_by(EstimateRowModel.id)
            .limit(limit)
        )
        return [PendingEmbedding(id=r.id, embedding_input=r.embedding_input)
                for r in self._session.execute(stmt)]

    def save_node_embedding(self, node_id: int, embedding_input: str, vector: list[float]) -> bool:
        result = self._session.execute(
            update(EstimateRowModel)
            .where(EstimateRowModel.id == node_id, EstimateRowModel.embedding_input == embedding_input)
            .values(embedding=vector)
        )
        self._session.commit()
        return result.rowcount > 0

    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.embedding, EstimateRowModel.embedding_input)
            .where(
                EstimateRowModel.estimate_id == estimate_id,
                EstimateRowModel.status.in_(("pending", "error", "no_match")),
                EstimateRowModel.embedding.is_not(None),
            )
            .order_by(EstimateRowModel.id)
        )
        return [MatchableNode(id=r.id, embedding=list(r.embedding), embedding_input=r.embedding_input)
                for r in self._session.execute(stmt)]

    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        self._session.execute(
            update(EstimateRowModel).where(EstimateRowModel.id == node_id).values(
                **self._match_values(result)
            )
        )
        self._session.commit()

    @staticmethod
    def _match_values(result: NodeMatch) -> dict:
        # перезаписывает ВЕСЬ снимок-набор (на успехе match_error=None → обнуляется)
        return {
            "status": str(result.status),
            "matched_article_id": result.matched_id,
            "matched_code": result.matched_code,
            "matched_name": result.matched_name,
            "score": result.score,
            "candidates": [
                {"id": c.id, "code": c.code, "name": c.name, "score": c.score}
                for c in result.candidates
            ] or None,
            "match_error": result.match_error,
        }

    def count_node_errors(self, estimate_id: int) -> int:
        return int(self._session.scalar(
            select(func.count()).select_from(EstimateRowModel).where(
                EstimateRowModel.estimate_id == estimate_id, EstimateRowModel.status == "error"
            )
        ) or 0)

    def count_unfinished_nodes(self, estimate_id: int) -> int:
        return int(self._session.scalar(
            select(func.count()).select_from(EstimateRowModel).where(
                EstimateRowModel.estimate_id == estimate_id, EstimateRowModel.status == "pending"
            )
        ) or 0)
```

- [ ] **Step 3: Тест чистого маппинга снимка (без БД)**

Дописать в `backend/tests/test_estimate_repository_mapping.py`:

```python
def test_match_values_overwrites_full_snapshot() -> None:
    from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch
    from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository

    # успех обнуляет match_error
    ok = SqlAlchemyEstimateRepository._match_values(
        NodeMatch(EstimateRowStatus.CONFIDENT, 5, "1.1", "X", 0.95,
                  [MatchCandidate(5, "1.1", "X", 0.95)])
    )
    assert ok["status"] == "confident" and ok["match_error"] is None
    assert ok["candidates"] == [{"id": 5, "code": "1.1", "name": "X", "score": 0.95}]

    # пустой снимок (no_match) → candidates None, score None
    nm = SqlAlchemyEstimateRepository._match_values(NodeMatch(EstimateRowStatus.NO_MATCH))
    assert nm["candidates"] is None and nm["score"] is None and nm["matched_article_id"] is None
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_repository_mapping.py -v && uv run ruff check app/infrastructure/db/estimate_repository.py app/infrastructure/db/article_repository.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/estimate_repository.py backend/app/infrastructure/db/article_repository.py backend/tests/test_estimate_repository_mapping.py
git commit -m "feat(matching): SQL-методы матчинга (advisory-lock, keyset embed, снимок, счётчики) + matching_readiness"
```

---

## Task 8: Транзиент-ретрай в адаптерах эмбеддера/LLM + структурная валидация арбитра

**Files:**
- Create: `backend/app/infrastructure/retry.py`
- Modify: `backend/app/infrastructure/ai/openrouter_embedder.py`
- Modify: `backend/app/infrastructure/ai/anthropic_matcher.py`
- Test: `backend/tests/test_retry.py`

**Interfaces:**
- Produces: `retry_transient(fn, *, budget, classify) -> result` (бросает `TransientError` на исчерпании); адаптеры применяют его + hard-timeout; `choose_best` структурный брак → `None`.

- [ ] **Step 1: Failing-тест хелпера ретрая**

Create `backend/tests/test_retry.py`:

```python
from __future__ import annotations

import pytest

from app.domain.errors import TransientError
from app.infrastructure.retry import retry_transient


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok"

    out = retry_transient(flaky, budget=3, classify=lambda e: isinstance(e, ConnectionError))
    assert out == "ok" and calls["n"] == 3


def test_exhausts_budget_raises_transient() -> None:
    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        retry_transient(always, budget=2, classify=lambda e: isinstance(e, ConnectionError))


def test_non_transient_propagates_as_is() -> None:
    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        retry_transient(boom, budget=3, classify=lambda e: isinstance(e, ConnectionError))
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_retry.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Реализовать хелпер**

Create `backend/app/infrastructure/retry.py`:

```python
"""Инлайн-бюджет ретраев транзиента для внешних вызовов. Граница: исчерпан → TransientError."""

from __future__ import annotations

import time
from collections.abc import Callable

from app.domain.errors import TransientError

_BACKOFF_BASE_S = 0.5


def retry_transient[T](
    fn: Callable[[], T],
    *,
    budget: int,
    classify: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Зовёт fn до budget раз, ретраит только транзиент (classify=True); иначе пробрасывает.

    Исчерпан бюджет на транзиенте → TransientError. Бэкофф экспоненциальный (тест мокает sleep).
    """
    last: Exception | None = None
    for attempt in range(budget):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — классифицируем явно ниже
            if not classify(exc):
                raise
            last = exc
            if attempt < budget - 1:
                sleep(_BACKOFF_BASE_S * (2**attempt))
    raise TransientError(str(last))
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_retry.py -v`
Expected: PASS.

- [ ] **Step 5: Применить в адаптерах (таймаут + бюджет + структурный→None)**

В `backend/app/infrastructure/ai/openrouter_embedder.py`: задать httpx-таймаут из конфига и обернуть сетевой вызов `retry_transient(..., classify=_is_transient)`, где `_is_transient` ловит `httpx.TransportError`/`httpx.TimeoutException`/HTTP 429/5xx. (Точная форма — по текущему телу адаптера; конструктор получает `timeout_s: float`, `retry_budget: int`.)

В `backend/app/infrastructure/ai/anthropic_matcher.py`: так же обернуть вызов LLM в `retry_transient`; **структурный брак ответа** (не-JSON, выбран id вне переданных кандидатов) → вернуть `None` (отказ, без ретрая) — НЕ `TransientError`. Сетевые/429 → транзиент.

> Точные диффы зависят от текущих тел адаптеров — реализатор читает файлы и вставляет вызовы по месту, сохраняя сигнатуры портов `Embedder.embed_batch`/`LLMMatcher.choose_best`. Конструкторы получают `timeout_s`/`retry_budget` (прокидываются из `deps.py` в Task 10).

- [ ] **Step 6: ruff + точечный прогон**

Run: `cd backend && uv run ruff check app/infrastructure/retry.py app/infrastructure/ai/ tests/test_retry.py && uv run pytest tests/test_retry.py -v`
Expected: чисто, PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/retry.py backend/app/infrastructure/ai/openrouter_embedder.py backend/app/infrastructure/ai/anthropic_matcher.py backend/tests/test_retry.py
git commit -m "feat(matching): инлайн-бюджет транзиента в адаптерах (timeout+retry→TransientError), структурный брак LLM→None"
```

---

## Task 9: Celery-приложение, задачи, `CeleryTaskQueue`

**Files:**
- Create: `backend/app/infrastructure/tasks/__init__.py`
- Create: `backend/app/infrastructure/tasks/celery_app.py`
- Create: `backend/app/infrastructure/tasks/tasks.py`
- Create: `backend/app/infrastructure/tasks/task_queue.py`
- Create: `backend/app/services/article_embedding_service.py`
- Modify: `backend/app/domain/ports.py` (метод singleton-лока на `EmbeddingQueueRepository`)
- Modify: `backend/app/infrastructure/db/embedding_queue_repository.py`
- Test: `backend/tests/test_tasks.py`, `backend/tests/test_article_embedding_service.py`

**Interfaces:**
- Consumes: `EstimateMatchingService`, `MatchingService`, `EmbeddingQueueRepository`, `Embedder`, `SessionLocal`, `Settings`, `DictionaryNotReadyError`.
- Produces: `celery_app`; задачи `match_estimate_task(estimate_id)`, `embed_articles_task()`; `CeleryTaskQueue(TaskQueue)`; `EmbeddingQueueRepository.try_embed_lock()/release_embed_lock()`; `drain_articles(queue, embedder) -> int`.

- [ ] **Step 1: Singleton-лок справочного эмбеддинга (порт + SQL) + drain-сервис — failing-тест**

Create `backend/tests/test_article_embedding_service.py`:

```python
from __future__ import annotations

from app.domain.entities import PendingEmbedding
from app.services.article_embedding_service import drain_articles


class _Queue:
    def __init__(self, pending_rounds: list[list[PendingEmbedding]]) -> None:
        self._rounds = pending_rounds
        self.saved: list[int] = []

    def fetch_pending(self, limit: int):
        return self._rounds.pop(0) if self._rounds else []

    def save_embedding(self, article_id, embedding_input, vector) -> bool:
        self.saved.append(article_id)
        return True


class _Embedder:
    def embed(self, text):
        return [0.1]

    def embed_batch(self, texts):
        return [[0.1] for _ in texts]


def test_drain_to_zero_processes_all_rounds() -> None:
    q = _Queue([[PendingEmbedding(1, "a"), PendingEmbedding(2, "b")], [PendingEmbedding(3, "c")]])
    written = drain_articles(q, _Embedder())
    assert written == 3 and q.saved == [1, 2, 3]  # докрутился до нуля (включая «доехавшие» позже)
```

- [ ] **Step 2: Реализовать drain-сервис + лок-методы порта**

Create `backend/app/services/article_embedding_service.py`:

```python
"""Drain-to-zero эмбеддинга справочника: гоняет run_once, пока есть pending. Чист от Celery."""

from __future__ import annotations

from app.domain.ports import Embedder, EmbeddingQueueRepository
from app.services.embedding_worker import run_once

_BATCH = 100


def drain_articles(queue: EmbeddingQueueRepository, embedder: Embedder) -> int:
    """Эмбеддит все pending-статьи (включая добавленные по ходу). Возвращает число записанных."""
    total = 0
    while (written := run_once(queue, embedder, batch_size=_BATCH)) > 0:
        total += written
    return total
```

В `backend/app/domain/ports.py` в `EmbeddingQueueRepository` добавить:

```python
    @abstractmethod
    def try_embed_lock(self) -> bool:
        """Неблокирующий singleton-лок эмбеддинга справочника (константный ключ). False → занят."""
        ...

    @abstractmethod
    def release_embed_lock(self) -> None: ...
```

В `backend/app/infrastructure/db/embedding_queue_repository.py` добавить импорт `func, select` и методы:

```python
_NS_EMBED = 0x454D4244  # "EMBD" — namespace singleton-лока эмбеддинга справочника


class SqlAlchemyEmbeddingQueueRepository(EmbeddingQueueRepository):
    # ... существующее ...

    def try_embed_lock(self) -> bool:
        return bool(self._session.scalar(select(func.pg_try_advisory_lock(_NS_EMBED, 0))))

    def release_embed_lock(self) -> None:
        self._session.scalar(select(func.pg_advisory_unlock(_NS_EMBED, 0)))
```

(`select`/`func` — добавить в импорт `from sqlalchemy import func, select, update`.)

- [ ] **Step 3: Запустить drain-тест — зелёный**

Run: `cd backend && uv run pytest tests/test_article_embedding_service.py -v`
Expected: PASS.

- [ ] **Step 4: Celery-приложение + адаптер очереди + задачи**

Create `backend/app/infrastructure/tasks/__init__.py` (пустой).

Create `backend/app/infrastructure/tasks/celery_app.py`:

```python
"""Celery-приложение. Брокер — Redis (Timeweb); result backend НЕ используется (БД — правда)."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery("ciw", broker=_settings.celery_broker_url, backend=None)
celery_app.conf.update(
    task_soft_time_limit=_settings.task_soft_time_limit_s,
    task_time_limit=_settings.task_time_limit_s,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

Create `backend/app/infrastructure/tasks/tasks.py`. Фабрики из `deps.py` (Task 10) импортируются
**лениво внутри тел задач** — иначе `tasks.py` не импортируется до Task 10 (и был бы цикл
`deps → tasks`). Управление gate-retry вынесено в **чистую функцию `run_match`** (без Celery,
тестируется напрямую):

```python
"""Тонкие Celery-обёртки: сессия → сервис из портов → коммит. Логика брокера живёт ТУТ."""

from __future__ import annotations

from app.core.config import get_settings
from app.domain.errors import DictionaryNotReadyError
from app.infrastructure.db.embedding_queue_repository import SqlAlchemyEmbeddingQueueRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.tasks.celery_app import celery_app
from app.services.article_embedding_service import drain_articles

_settings = get_settings()


def run_match(service, estimate_id: int, *, is_final: bool) -> None:
    """Чистая логика gate-retry без Celery: gate-не-готов и попытки исчерпаны → mark_blocked;
    иначе пробрасывает DictionaryNotReadyError (обёртка решает self.retry)."""
    try:
        service.match_estimate(estimate_id)
    except DictionaryNotReadyError as exc:
        if is_final:
            service.mark_blocked(estimate_id, detail=f"timeout ждали справочник: {exc}")
            return
        raise


@celery_app.task(bind=True, max_retries=_settings.gate_retry_max)
def match_estimate_task(self, estimate_id: int) -> None:
    from app.api.deps import build_estimate_matching_service  # ленивый импорт (нет цикла deps↔tasks)

    session = SessionLocal()
    try:
        service = build_estimate_matching_service(session)
        is_final = self.request.retries >= self.max_retries
        try:
            run_match(service, estimate_id, is_final=is_final)
        except DictionaryNotReadyError as exc:
            raise self.retry(exc=exc, countdown=_settings.gate_retry_backoff_s)
    finally:
        session.close()  # возвращает коннект → session-level advisory-lock снят


@celery_app.task
def embed_articles_task() -> None:
    from app.api.deps import build_embedder  # ленивый импорт

    session = SessionLocal()
    try:
        queue = SqlAlchemyEmbeddingQueueRepository(session)
        if not queue.try_embed_lock():
            return  # singleton → no-op
        try:
            drain_articles(queue, build_embedder())
        finally:
            queue.release_embed_lock()
    finally:
        session.close()
```

Create `backend/app/infrastructure/tasks/task_queue.py`:

```python
"""CeleryTaskQueue — адаптер порта TaskQueue. enqueue → .delay(), возвращает None."""

from __future__ import annotations

from app.domain.ports import TaskQueue
from app.infrastructure.tasks.tasks import embed_articles_task, match_estimate_task


class CeleryTaskQueue(TaskQueue):
    def enqueue_match(self, estimate_id: int) -> None:
        match_estimate_task.delay(estimate_id)

    def enqueue_articles_embed(self) -> None:
        embed_articles_task.delay()
```

> **Windows-dev:** воркер `uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo`. На проде (Linux) — `--pool=prefork --concurrency=N`, `embed_articles_task` в отдельную очередь.

- [ ] **Step 5: Тест чистой `run_match` (gate-retry→blocked) — без Celery/Redis/БД**

Create `backend/tests/test_tasks.py`:

```python
from __future__ import annotations

import pytest

from app.domain.errors import DictionaryNotReadyError
from app.infrastructure.tasks.tasks import run_match


class _Service:
    def __init__(self, raise_gate: bool) -> None:
        self._raise = raise_gate
        self.blocked: list[int] = []
        self.matched: list[int] = []

    def match_estimate(self, estimate_id: int) -> None:
        if self._raise:
            raise DictionaryNotReadyError(total=0, pending=0)
        self.matched.append(estimate_id)

    def mark_blocked(self, estimate_id: int, detail: str) -> None:
        self.blocked.append(estimate_id)


def test_run_match_success() -> None:
    svc = _Service(raise_gate=False)
    run_match(svc, 7, is_final=False)
    assert svc.matched == [7] and svc.blocked == []


def test_run_match_gate_not_final_reraises_for_retry() -> None:
    svc = _Service(raise_gate=True)
    with pytest.raises(DictionaryNotReadyError):
        run_match(svc, 7, is_final=False)        # обёртка сделает self.retry
    assert svc.blocked == []


def test_run_match_gate_final_marks_blocked() -> None:
    svc = _Service(raise_gate=True)
    run_match(svc, 7, is_final=True)             # исчерпаны → blocked, не пробрасывает
    assert svc.blocked == [7]
```

> Импорт `tasks.py` тянет `celery_app` (только конструирование Celery-объекта, без сети). Если в окружении это нежелательно — тест может импортировать `run_match` через `importlib` после установки `CELERY_BROKER_URL` (он уже в conftest). Реальный Redis/`self.retry` не дёргаются: `run_match` чист.

- [ ] **Step 6: Запустить + ruff**

Run: `cd backend && uv run pytest tests/test_tasks.py tests/test_article_embedding_service.py -v && uv run ruff check app/infrastructure/tasks/ app/services/article_embedding_service.py app/infrastructure/db/embedding_queue_repository.py`
Expected: PASS, ruff чисто.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/tasks/ backend/app/services/article_embedding_service.py backend/app/domain/ports.py backend/app/infrastructure/db/embedding_queue_repository.py backend/tests/test_tasks.py backend/tests/test_article_embedding_service.py
git commit -m "feat(matching): Celery-приложение + задачи (gate-retry→blocked, singleton+drain) + CeleryTaskQueue"
```

---

## Task 10: DI-проводка + enqueue-after-commit в `EstimateService`

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/services/estimate_service.py`
- Test: `backend/tests/test_estimate_service.py`

**Interfaces:**
- Produces (DI): `get_task_queue()`, `build_embedder()`, `build_estimate_matching_service(session)`, `get_estimate_matching_service(...)`; `EstimateService.__init__(..., task_queue: TaskQueue)` + enqueue после коммита.

- [ ] **Step 1: Failing-тест — ingest энкьюит match ПОСЛЕ создания**

Дописать в `backend/tests/test_estimate_service.py`:

```python
def test_ingest_enqueues_match_after_create() -> None:
    from tests.fakes import FakeTaskQueue

    storage = FakeObjectStorage()
    repo = FakeEstimateRepository()
    queue = FakeTaskQueue()
    service = EstimateService(EstimateParser(), repo, storage, task_queue=queue)
    est = service.ingest(_xlsx(), "смета.xlsx", owner_id=7).estimate
    assert queue.match_calls == [est.id]          # энкью был
    assert repo.create_calls == 1                  # и строки уже созданы (после коммита)


def test_ingest_storage_failure_does_not_enqueue() -> None:
    from app.domain.errors import StorageError
    from tests.fakes import FakeTaskQueue

    queue = FakeTaskQueue()
    service = EstimateService(EstimateParser(), FakeEstimateRepository(),
                              FakeObjectStorage(fail=True), task_queue=queue)
    import pytest
    with pytest.raises(StorageError):
        service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert queue.match_calls == []                 # сбой put → ни БД, ни enqueue
```

> Существующие тесты `EstimateService` создают сервис без `task_queue` — добавить дефолт-фейк, см. Step 3 (сделать параметр обязательным и обновить хелпер `_service`).

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_estimate_service.py -v`
Expected: FAIL (`task_queue` не принимается / нет enqueue).

- [ ] **Step 3: Проводка в EstimateService**

В `backend/app/services/estimate_service.py`: добавить в импорт `TaskQueue`, в `__init__` параметр `task_queue: TaskQueue`, и в конце `ingest` — после `repository.create(...)` (т.е. после коммита внутри create) — `self._task_queue.enqueue_match(estimate.id)` ПЕРЕД `return`:

```python
    def __init__(self, parser, repository, storage, task_queue) -> None:
        self._parser = parser
        self._repository = repository
        self._storage = storage
        self._task_queue = task_queue

    def ingest(self, content: bytes, filename: str, owner_id: int) -> IngestResult:
        parsed = self._parser.parse(content)
        key = f"estimates/{uuid.uuid4().hex}/{filename}"
        self._storage.put(key, content, _XLSX_CONTENT_TYPE)        # сбой → проброс, БД не тронута
        estimate = self._repository.create(
            NewEstimate(user_id=owner_id, filename=filename, original_object_key=key),
            parsed.nodes,
        )
        self._task_queue.enqueue_match(estimate.id)                # строго ПОСЛЕ коммита create
        return IngestResult(estimate=estimate, positions_count=len(parsed.positions),
                            warnings=parsed.warnings)
```

В `backend/tests/test_estimate_service.py` обновить хелпер `_service`, чтобы передавать `FakeTaskQueue()`. **Также** обновить прямые конструкторы `EstimateService(...)` в `backend/tests/test_estimate_routes.py` (SP1-тесты `test_list_and_get_ownership`, `test_delete_removes_object`, и `_svc_factory`) — добавить `task_queue=FakeTaskQueue()`, иначе они упадут на обязательном параметре (полный прогон в Task 12 это поймал бы, но чиним сразу).

- [ ] **Step 4: DI в deps.py**

В `backend/app/api/deps.py` добавить импорты (`TaskQueue`, `MatchingService`, `EstimateMatchingService`, `CeleryTaskQueue`, `SqlAlchemyEmbeddingQueueRepository`) и провайдеры/фабрики:

```python
@lru_cache
def get_task_queue() -> TaskQueue:
    from app.infrastructure.tasks.task_queue import CeleryTaskQueue  # ленивый импорт: не тащить Celery в API-импорт
    return CeleryTaskQueue()


def build_embedder() -> Embedder:
    settings = get_settings()
    return OpenRouterEmbedder(
        api_key=settings.openrouter_api_key, base_url=settings.embedding_base_url,
        model=settings.embedding_model, dimensions=settings.embedding_dim,
        timeout_s=settings.ai_call_timeout_s, retry_budget=settings.transient_retry_budget,
    )


def build_estimate_matching_service(session: Session) -> EstimateMatchingService:
    """Фабрика для Celery-задачи (вне FastAPI DI): собирает сервис на переданной сессии."""
    settings = get_settings()
    articles = SqlAlchemyArticleRepository(session)
    estimates = SqlAlchemyEstimateRepository(session)
    matcher = MatchingService(articles, embedder=None,
                              llm_matcher=AnthropicLLMMatcher(
                                  api_key=settings.anthropic_api_key, model=settings.llm_model,
                                  timeout_s=settings.ai_call_timeout_s,
                                  retry_budget=settings.transient_retry_budget),
                              confidence_threshold=settings.confidence_threshold)
    return EstimateMatchingService(matcher=matcher, embedder=build_embedder(),
                                   estimates=estimates, articles=articles)
```

Обновить `get_embedder`/`get_llm_matcher` (добавить `timeout_s`/`retry_budget` из настроек — Task 8 расширил конструкторы). Обновить `get_estimate_service`, добавив `task_queue=Depends(get_task_queue)`:

```python
def get_estimate_service(
    parser: EstimateParser = Depends(get_estimate_parser),
    repository: EstimateRepository = Depends(get_estimate_repository),
    storage: ObjectStorage = Depends(get_object_storage),
    task_queue: TaskQueue = Depends(get_task_queue),
) -> EstimateService:
    return EstimateService(parser=parser, repository=repository, storage=storage, task_queue=task_queue)
```

- [ ] **Step 5: Запустить — зелёный + импорт-смоук + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_service.py -v && uv run python -c "import app.api.deps; print('ok')" && uv run ruff check app/api/deps.py app/services/estimate_service.py`
Expected: PASS, `ok`, ruff чисто.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/deps.py backend/app/services/estimate_service.py backend/tests/test_estimate_service.py
git commit -m "feat(matching): DI taskqueue/matching-service + enqueue_match после коммита ingest"
```

---

## Task 11: API — ре-триггер матчинга, эмбеддинг справочника, DTO; снятие `/estimates/match`

**Files:**
- Modify: `backend/app/api/routes/estimates.py`
- Modify: `backend/app/api/routes/articles.py`
- Modify: `backend/app/api/schemas.py`
- Test: `backend/tests/test_estimate_routes.py`, `backend/tests/test_articles_routes.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_task_queue`, `get_estimate_repository`, `require_admin`, `Role`.
- Produces: `POST /api/estimates/{id}/match` (202), `POST /api/articles/embed` (202); `EstimateRowOut` с `matched_code/matched_name/score/status_detail`.

- [ ] **Step 1: Failing-тесты роутов**

Дописать в `backend/tests/test_estimate_routes.py`:

```python
def test_retrigger_match_enqueues_for_owner() -> None:
    from app.api.deps import get_estimate_repository, get_task_queue
    from tests.fakes import FakeTaskQueue

    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2)
    queue = FakeTaskQueue()
    app.dependency_overrides[get_current_user] = _user(uid=2)
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    app.dependency_overrides[get_task_queue] = lambda: queue
    client = TestClient(app)
    resp = client.post("/api/estimates/1/match")
    assert resp.status_code == 202 and queue.match_calls == [1]


def test_retrigger_foreign_estimate_404() -> None:
    from app.api.deps import get_estimate_repository, get_task_queue
    from tests.fakes import FakeTaskQueue

    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2)
    app.dependency_overrides[get_current_user] = _user(uid=9)  # чужой
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    app.dependency_overrides[get_task_queue] = lambda: FakeTaskQueue()
    client = TestClient(app)
    assert client.post("/api/estimates/1/match").status_code == 404


def test_old_match_route_removed() -> None:
    app.dependency_overrides[get_current_user] = _user()
    client = TestClient(app)
    resp = client.post("/api/estimates/match", files={"file": ("a.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 404  # синхронный stateless-матч снят
```

Create `backend/tests/test_articles_routes.py`:

```python
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_task_queue
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import FakeTaskQueue


def _admin() -> User:
    return User(id=1, email="a@mr.kz", password_hash="h", role=Role.ADMIN)


def _user() -> User:
    return User(id=2, email="u@mr.kz", password_hash="h", role=Role.USER)


def test_admin_embed_enqueues() -> None:
    queue = FakeTaskQueue()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_task_queue] = lambda: queue
    try:
        resp = TestClient(app).post("/api/articles/embed")
        assert resp.status_code == 202 and queue.articles_embed_calls == 1
    finally:
        app.dependency_overrides.clear()


def test_non_admin_embed_forbidden() -> None:
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_task_queue] = lambda: FakeTaskQueue()
    try:
        assert TestClient(app).post("/api/articles/embed").status_code == 403
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_estimate_routes.py tests/test_articles_routes.py -v`
Expected: FAIL (нет роутов; старый `/match` ещё отвечает).

- [ ] **Step 3: Реализовать роуты + DTO**

В `backend/app/api/routes/estimates.py`:
- удалить роут `POST /match` и его импорты (`get_matching_service`, `get_parser`, `MatchResultOut`, `ExcelEstimateParser`, `MatchingService`);
- добавить импорты `get_task_queue`, `get_estimate_repository`, `TaskQueue`, `EstimateRepository`;
- добавить роут:

```python
@router.post("/{estimate_id}/match", status_code=status.HTTP_202_ACCEPTED)
def retrigger_match(
    estimate_id: int,
    user: User = Depends(get_current_user),
    repository: EstimateRepository = Depends(get_estimate_repository),
    task_queue: TaskQueue = Depends(get_task_queue),
) -> dict[str, str]:
    est = repository.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    task_queue.enqueue_match(estimate_id)
    # честный ответ: если идёт — задача-дубль возьмёт no-op (живой держатель) / дозаберёт (зависла)
    detail = "уже выполняется" if est.status == "running" else "поставлено в очередь"
    return {"status": "accepted", "detail": detail}
```

В `backend/app/api/routes/articles.py` добавить импорты `get_task_queue`, `TaskQueue` и роут:

```python
@router.post("/embed", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(require_admin)])
def embed_articles(task_queue: TaskQueue = Depends(get_task_queue)) -> dict[str, str]:
    task_queue.enqueue_articles_embed()
    return {"status": "accepted"}
```

И в путях импорта/создания справочника (`import_template`, `create_article`) — после успешного применения вызвать `task_queue.enqueue_articles_embed()` (добавить `task_queue: TaskQueue = Depends(get_task_queue)` в сигнатуры; enqueue после успешного ответа сервиса).

В `backend/app/api/schemas.py` расширить `EstimateRowOut`: добавить `matched_code: str | None`, `matched_name: str | None`, `score: float | None`, и в `from_entity` — прокинуть их из `StoredEstimateRow` (поля добавлены в SP1-сущность? если нет — расширить `StoredEstimateRow` снимком в Task 7-маппинге `_row_to_entity` и здесь). Добавить `status_detail: str | None` в `EstimateDetailOut`/`EstimateSummaryOut` по необходимости.

> `StoredEstimateRow` (SP1) не несёт снимок матчинга — расширить её полями `matched_code/matched_name/score/status_detail` (nullable, default None) и заполнять в `SqlAlchemyEstimateRepository._row_to_entity` из модели. Это часть данного шага (DTO без сущности бессмысленно). Обновить `_row_to_entity` и фейк-`create` соответственно (default None).

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_estimate_routes.py tests/test_articles_routes.py -v`
Expected: PASS.

- [ ] **Step 5: ruff**

Run: `cd backend && uv run ruff check app/api/routes/estimates.py app/api/routes/articles.py app/api/schemas.py`
Expected: чисто.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/estimates.py backend/app/api/routes/articles.py backend/app/api/schemas.py backend/app/domain/entities.py backend/app/infrastructure/db/estimate_repository.py backend/tests/test_estimate_routes.py backend/tests/test_articles_routes.py
git commit -m "feat(matching): API ре-триггер /estimates/{id}/match + /articles/embed + снимок в DTO; снят /estimates/match"
```

---

## Task 12: Снятие старого пути + justfile + полный прогон

**Files:**
- Delete: `backend/app/services/excel_parser.py`, `backend/app/scripts/embed_worker.py`
- Modify: `backend/app/api/deps.py` (снять `get_parser`, `get_matching_service`-старый, `ExcelEstimateParser`)
- Modify: `backend/app/domain/entities.py` (снять `MatchStatus`, `EstimateRow`, `MatchResult`)
- Modify: `backend/app/api/schemas.py` (снять `MatchResultOut`)
- Modify: `backend/app/domain/ports.py` (`LLMMatcher.choose_best` — без изменений сигнатуры; убедиться в отсутствии ссылок на `EstimateRow`)
- Modify: `justfile`
- Test: весь сьют

- [ ] **Step 1: Найти все ссылки на снимаемые символы**

Run: `cd backend && grep -rn "MatchStatus\|MatchResult\|EstimateRow\b\|ExcelEstimateParser\|match_rows\|embed_worker\|get_parser\|get_matching_service" app tests`
Expected: список — все вхождения, которые нужно снять/переписать (ожидаемо: deps.py, entities.py, schemas.py, удаляемые файлы; тесты старого парсера/матча — удалить).

- [ ] **Step 2: Удалить старые файлы и символы**

- Удалить `backend/app/services/excel_parser.py`, `backend/app/scripts/embed_worker.py` и их тесты (`tests/test_excel_parser.py` если есть).
- В `backend/app/domain/entities.py` удалить `MatchStatus`, `EstimateRow`, `MatchResult` (ядро `match_one` их не использует).
- В `backend/app/api/schemas.py` удалить `MatchResultOut`.
- В `backend/app/api/deps.py` удалить `get_parser`, старую фабрику `get_matching_service` (если её больше не зовут роуты — ядро `match_one` собирается в `build_estimate_matching_service`), импорты `ExcelEstimateParser`.
- Прогнать grep из Step 1 повторно — должно быть пусто (кроме обновлённого `match_one`-пути).

- [ ] **Step 3: justfile — воркер матчинга, снять embed-worker**

В `justfile` удалить рецепт `embed-worker` и добавить:

```makefile
# Celery-воркер: матчинг смет + эмбеддинг справочника (dev: solo-pool для Windows).
celery-worker:
    cd {{backend}}; uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo --loglevel=info
```

- [ ] **Step 4: Полный прогон + ruff (вся сюита зелёная)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest && uv run ruff check .`
Expected: вся сюита зелёная (старые тесты, завязанные на снятый путь, удалены/переписаны), ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add -A backend/ justfile
git commit -m "refactor(matching): снять старый путь (/estimates/match, ExcelEstimateParser, MatchStatus, embed-worker) + celery-worker рецепт"
```

---

## Self-Review

**Spec coverage:**
- Celery+Redis, без result backend, TaskQueue-порт → Task 1, 5, 9, 10 ✓
- Миграция 0004 (снимок plain-int + candidates JSONB + status_detail) → Task 2 ✓
- Доменные статусы/NodeMatch + TransientError/DictionaryNotReadyError → Task 3 ✓
- Ядро match_one без ре-эмбеддинга + валидация арбитра (структурный→None) → Task 4 ✓
- Порты+фейки (lock/status/embed/match/счётчики/touch, matching_readiness, TaskQueue) → Task 5 ✓
- Оркестрация match_estimate (embed→gate→match, heartbeat, mark_blocked под локом+терминал) → Task 6 ✓
- SQL-адаптеры (advisory-lock 2-арг session-level, keyset embed, CAS, снимок, счётчики) → Task 7 ✓
- Инлайн транзиент-бюджет + таймауты в адаптерах → Task 8 ✓
- Celery-задачи: gate-retry→blocked, singleton embed + drain-to-zero, тайм-лимиты → Task 9 ✓
- enqueue-after-commit + DI → Task 10 ✓
- API ре-триггер (404 владение, 202, честный ответ при running) + /articles/embed (admin) + снятие /estimates/match → Task 11 ✓
- Снятие старого пути (ExcelEstimateParser/MatchStatus/EstimateRow/embed-worker) + justfile → Task 12 ✓
- Стейт-машина: no_match/needs_review не → partial_error; ре-матч {pending,error,no_match}; иммутабельность confident/needs_review (matchable-фильтр) → Task 5/6/7 ✓
- Тесты: gate→blocked, mark_blocked-no-op, transient→error→partial, heartbeat, keyset/CAS, drain-to-zero, enqueue-after-commit, ownership → распределены ✓

**Заметки реализации:**
- Миграция 0004 применяется к боевой БД вручную: `just migrate` (в тестах БД не поднимается).
- Реальные БД/Redis/MinIO в юнит-тестах не дёргаются — фейки + `task_always_eager`/прямой вызов.
- Advisory-lock держится на коннекте Session всю задачу; `session.close()` в `finally` обёртки возвращает коннект (лок снят) — это и есть «детектор живости» при крахе.
- Тайм-лимиты Celery + per-call HTTP-таймауты обязательны (Task 1 + 8 + 9) — без них семантика `running` неверна.
- `StoredEstimateRow` расширяется снимком в Task 11 (DTO) — держать `_row_to_entity` и фейк-`create` синхронными (default None для не-сматченных).
