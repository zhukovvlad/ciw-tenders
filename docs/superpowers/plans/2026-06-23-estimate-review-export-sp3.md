# SP3 — Ревью/правки матчинга + запись «Статья СМР» + выгрузка .xlsx — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать оператору просмотреть результат матчинга, вручную поправить спорные строки, выгрузить `.xlsx` с заполненной колонкой `Статья СМР`; закрыть долг «залип в running».

**Architecture:** Поверх иммутабельного AI-снимка SP2 добавляется **ось ревью** (`review_status` + `final_*` + `reviewed_at`) к строке `estimate_rows`. Гонку правка↔ре-триггер закрывает CAS на записи AI-снимка (`save_node_match ... WHERE review_status='unreviewed'`), а не лок на правке. Экспорт читает оригинал из MinIO и пишет код по физ.строке `source_index + 2` только в строки-узлы. Clean Architecture: новые порты-методы в `domain/ports.py`, реализации в `infrastructure/`, сценарии в `services/`, DTO в `api/`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 + pgvector, Alembic, openpyxl (запись .xlsx), Pydantic v2; фронт — Vite + React + TS. Управление — `uv` (бэк), `npm` (фронт), `just`.

## Global Constraints

- **Спека (источник правды):** [docs/superpowers/specs/2026-06-23-estimate-review-export-sp3-design.md](../specs/2026-06-23-estimate-review-export-sp3-design.md). Любое расхождение с планом — в пользу спеки.
- **Ветка:** `feat/estimate-review-export` (уже создана от `main`).
- **Бэкенд только через `uv run`** из `backend/` (не системный python/pip). Кириллица в stdout: префикс `PYTHONIOENCODING=utf-8`.
- **Тесты не ходят в сеть/реальную БД/AI** — фейки портов (`backend/tests/fakes.py`) + `app.dependency_overrides`. `conftest.py` задаёт фиктивные env до импорта приложения.
- **ruff:** line-length 100, target py311, `from __future__ import annotations`, type hints обязательны. Перед коммитом: `uv run ruff check .`.
- **Фронт:** eslint строгий + Prettier (printWidth 80, endOfLine lf); `erasableSyntaxOnly` (без enum/parameter properties); импорты через `@/`; `npm run typecheck` = `tsc -b`. shadcn `src/components/ui/` не править.
- **Порог similarity** `confidence_threshold = 0.90` — не трогаем (SP3 его не калибрует).
- **`task_time_limit_s = 660`** (config.py) — порог staleness-sweep.
- **LF переводы строк** во всех файлах.
- **Каждый шаг с кодом показывает код целиком.** Коммиты частые, по завершению задачи.

## File Structure

**Backend — изменяемые:**
- `backend/app/domain/entities.py` — +`ReviewStatus` enum; `StoredEstimateRow` +поля ревью + `candidates`.
- `backend/app/domain/errors.py` — +`RowNotMatchedError`, `InvalidReviewActionError`.
- `backend/app/domain/ports.py` — `ArticleRepository`: +`get_by_id`, +`search`; `EstimateRepository`: +`save_review_decision`, +`get_object_key`, +`is_stale_running`; сужение контракта `fetch_matchable_nodes`/`save_node_match`.
- `backend/app/infrastructure/db/models.py` — `EstimateRowModel` +4 колонки.
- `backend/app/infrastructure/db/estimate_repository.py` — `_row_to_entity` +поля; `fetch_matchable_nodes` +фильтр; `save_node_match` +CAS; новые методы.
- `backend/app/infrastructure/db/article_repository.py` — `get_by_id`, `search`.
- `backend/app/services/estimate_review_service.py` *(новый)* — валидация+применение решения.
- `backend/app/services/estimate_export_service.py` *(новый)* — сборка .xlsx.
- `backend/app/api/schemas.py` — `EstimateRowOut` +поля, `MatchCandidateOut`, `ReviewDecisionIn`, `ArticleSearchOut`.
- `backend/app/api/deps.py` — провайдеры новых сервисов.
- `backend/app/api/routes/estimates.py` — `PATCH .../rows/{id}/review`, `GET .../export`, sweep в `retrigger_match`.
- `backend/app/api/routes/articles.py` — `GET /articles/search`.
- `backend/alembic/versions/0005_estimate_review_axis.py` *(новый)*.
- `backend/tests/fakes.py` — фейки под новые методы + ось ревью в узлах.

**Backend — новые тесты:** `tests/test_estimate_review.py`, `tests/test_estimate_export.py`, `tests/test_article_search.py`, `tests/test_estimate_sweep.py`; правки `tests/test_matching_service.py` (CAS/фильтр).

**Frontend — изменяемые:**
- `frontend/src/lib/types.ts` — `MatchRow`/`Candidate` под реальный DTO.
- `frontend/src/lib/api/estimates.ts` *(новый)* — `getEstimate`, `patchRowReview`, `exportEstimate`.
- `frontend/src/lib/api/articles.ts` — +`searchArticles`.
- `frontend/src/lib/reviewState.ts` — маппинг действий, без `rationale`.
- `frontend/src/pages/estimate/EstimateFlow.tsx`, `ReviewRow.tsx` — с `lib/mock` на `lib/api`.

---

## Task 1: Миграция + ORM + домен (ось ревью)

Фундамент: колонки в БД, ORM-модель, доменные поля. Без поведения — только структура.

**Files:**
- Create: `backend/alembic/versions/0005_estimate_review_axis.py`
- Modify: `backend/app/infrastructure/db/models.py:95-120`
- Modify: `backend/app/domain/entities.py` (рядом с `EstimateRowStatus` ~112-119; `StoredEstimateRow` ~177-194)
- Test: `backend/tests/test_models_review.py` (новый, лёгкий — проверка дефолтов ORM/enum)

**Interfaces:**
- Produces:
  - `ReviewStatus(StrEnum)`: `UNREVIEWED="unreviewed"`, `CONFIRMED="confirmed"`, `OVERRIDDEN="overridden"`, `REJECTED="rejected"`.
  - `StoredEstimateRow` +поля: `candidates: list[MatchCandidate] = []`, `matched_article_id: int | None = None`, `review_status: str = "unreviewed"`, `final_article_id: int | None = None`, `final_code: str | None = None`, `final_name: str | None = None`, `reviewed_at: datetime | None = None`.
  - `EstimateRowModel` +колонки: `review_status` (String(32), NOT NULL, server_default `'unreviewed'`), `final_article_id` (Integer, null), `final_code` (String(64), null), `final_name` (Text, null), `reviewed_at` (DateTime(tz), null).

- [ ] **Step 1: Написать миграцию 0005**

Create `backend/alembic/versions/0005_estimate_review_axis.py`:

```python
"""estimate review axis columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # review_status NOT NULL DEFAULT 'unreviewed' — metadata-only на Postgres (без переписи
    # таблицы); существующие SP1/SP2-строки бэкфиллятся дефолтом.
    op.execute(
        """
        ALTER TABLE estimate_rows
            ADD COLUMN review_status   VARCHAR(32) NOT NULL DEFAULT 'unreviewed',
            ADD COLUMN final_article_id INTEGER,
            ADD COLUMN final_code       VARCHAR(64),
            ADD COLUMN final_name       TEXT,
            ADD COLUMN reviewed_at      TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE estimate_rows
            DROP COLUMN IF EXISTS review_status,
            DROP COLUMN IF EXISTS final_article_id,
            DROP COLUMN IF EXISTS final_code,
            DROP COLUMN IF EXISTS final_name,
            DROP COLUMN IF EXISTS reviewed_at
        """
    )
```

- [ ] **Step 2: Добавить `ReviewStatus` в `entities.py`**

После `class EstimateRowStatus(StrEnum):` (строки 112-119) добавить:

```python
class ReviewStatus(StrEnum):
    """Ось ревью поверх иммутабельного AI-снимка (status). Независима от EstimateRowStatus."""

    UNREVIEWED = "unreviewed"
    CONFIRMED = "confirmed"   # согласие с рекомендацией AI (matched_*)
    OVERRIDDEN = "overridden"  # выбран другой кандидат или ручной подбор
    REJECTED = "rejected"      # явно «статьи нет»
```

- [ ] **Step 3: Расширить `StoredEstimateRow`**

В `entities.py` заменить тело `StoredEstimateRow` (поля после `id: int`, строки ~181-193) на:

```python
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
```

(`MatchCandidate`, `field`, `datetime` уже импортированы/определены в файле.)

- [ ] **Step 4: Добавить колонки в `EstimateRowModel`**

В `models.py` после `match_error` (строка 119) добавить:

```python
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unreviewed"
    )
    final_article_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 5: Написать тест дефолтов модели/enum**

Create `backend/tests/test_models_review.py`:

```python
from __future__ import annotations

from app.domain.entities import ReviewStatus, StoredEstimateRow
from app.infrastructure.db.models import EstimateRowModel


def test_review_status_values() -> None:
    assert ReviewStatus.UNREVIEWED == "unreviewed"
    assert {s.value for s in ReviewStatus} == {
        "unreviewed", "confirmed", "overridden", "rejected"
    }


def test_stored_row_review_defaults() -> None:
    row = StoredEstimateRow(
        id=1, code="1", name="n", parent_code=None, section_type=None,
        depth=0, embedding_input="x", source_index=0, status="pending",
    )
    assert row.review_status == "unreviewed"
    assert row.final_code is None
    assert row.candidates == []


def test_model_has_review_columns() -> None:
    cols = set(EstimateRowModel.__table__.columns.keys())
    assert {"review_status", "final_article_id", "final_code",
            "final_name", "reviewed_at"} <= cols
```

- [ ] **Step 6: Прогнать тесты**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_models_review.py -v`
Expected: 3 passed.

- [ ] **Step 7: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/alembic/versions/0005_estimate_review_axis.py backend/app/domain/entities.py backend/app/infrastructure/db/models.py backend/tests/test_models_review.py
git commit -m "feat(sp3): ось ревью — миграция 0005 + ORM + домен (review_status/final_*)"
```

> **Примечание:** `just migrate` (применение к Neon) — ручной шаг оператора вне субагента (нужен реальный `DATABASE_URL`). Субагент только пишет ревизию; ORM синхронен.

---

## Task 2: SP2-стык — matchable-фильтр + CAS на записи матча

Защита ручных правок до того, как появятся сами правки. Меняем контракт двух методов SP2.

**Files:**
- Modify: `backend/app/infrastructure/db/estimate_repository.py:210-232`
- Modify: `backend/app/domain/ports.py:213-221` (docstring-контракт)
- Modify: `backend/tests/fakes.py` (узлы +`review_status`; `fetch_matchable_nodes`/`save_node_match`)
- Test: `backend/tests/test_estimate_repo_cas.py` (новый, на фейке)

**Interfaces:**
- Consumes: `EstimateRowModel.review_status` (Task 1).
- Produces (изменённый контракт):
  - `fetch_matchable_nodes`: возвращает только `status ∈ {pending,error,no_match}` **И** `embedding IS NOT NULL` **И** `review_status = 'unreviewed'`.
  - `save_node_match(node_id, result)`: пишет AI-снимок **только если** `review_status = 'unreviewed'` (CAS); иначе no-op.
  - Фейк-узел теперь несёт ключи `review_status` (default `"unreviewed"`), `candidates`, `matched_*`, `score`, `final_*`, `reviewed_at`.

- [ ] **Step 1: Расширить фейк-узлы и сузить методы (фейк)**

В `backend/tests/fakes.py`, в `FakeEstimateRepository.create`, в словарь узла (`self.nodes[nid] = {...}`, строки ~273-280) добавить поля ревью/снимка:

```python
            self.nodes[nid] = {
                "id": nid,
                "estimate_id": eid,
                "embedding_input": n.embedding_input,
                "embedding": None,
                "status": "pending",
                "match_error": None,
                "matched_article_id": None,
                "matched_code": None,
                "matched_name": None,
                "score": None,
                "candidates": [],
                "review_status": "unreviewed",
                "final_article_id": None,
                "final_code": None,
                "final_name": None,
                "reviewed_at": None,
            }
```

Заменить `fetch_matchable_nodes` (строки ~384-393) — добавить условие `review_status`:

```python
    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        return [
            MatchableNode(
                id=n["id"], embedding=n["embedding"], embedding_input=n["embedding_input"]
            )
            for n in sorted(self.nodes.values(), key=lambda n: n["id"])
            if n["estimate_id"] == estimate_id
            and n["status"] in ("pending", "error", "no_match")
            and n["embedding"] is not None
            and n["review_status"] == "unreviewed"
        ]
```

Заменить `save_node_match` (строки ~395-398) — CAS по `review_status`:

```python
    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        n = self.nodes[node_id]
        if n["review_status"] != "unreviewed":
            return  # CAS: человек тронул строку — AI-снимок не затирает решение
        n["status"] = str(result.status)
        n["match_error"] = result.match_error
        n["matched_article_id"] = result.matched_id
        n["matched_code"] = result.matched_code
        n["matched_name"] = result.matched_name
        n["score"] = result.score
        n["candidates"] = [
            {"id": c.id, "code": c.code, "name": c.name, "score": c.score}
            for c in result.candidates
        ]
```

- [ ] **Step 2: Написать тест CAS на фейке**

Create `backend/tests/test_estimate_repo_cas.py`:

```python
from __future__ import annotations

from app.domain.entities import (
    EstimateNode, EstimateRowStatus, MatchCandidate, NewEstimate, NodeMatch,
)
from tests.fakes import FakeEstimateRepository


def _seed_one_matchable() -> tuple[FakeEstimateRepository, int]:
    repo = FakeEstimateRepository()
    node = EstimateNode(
        code="1", name="Узел", parent_code=None, section_type="СМР",
        embedding_input="узел", source_index=0, depth=0,
    )
    est = repo.create(NewEstimate(1, "f.xlsx", "key"), [node])
    nid = est.rows[0].id
    repo.nodes[nid]["embedding"] = [0.1]
    repo.nodes[nid]["status"] = "no_match"
    return repo, nid


def test_save_node_match_skips_reviewed_row() -> None:
    repo, nid = _seed_one_matchable()
    repo.nodes[nid]["review_status"] = "overridden"  # человек уже тронул
    result = NodeMatch(
        EstimateRowStatus.CONFIDENT, matched_id=7, matched_code="2.1",
        matched_name="Статья", score=0.95,
        candidates=[MatchCandidate(7, "2.1", "Статья", 0.95)],
    )
    repo.save_node_match(nid, result)
    assert repo.nodes[nid]["status"] == "no_match"  # не затёрто
    assert repo.nodes[nid]["matched_code"] is None


def test_fetch_matchable_excludes_reviewed() -> None:
    repo, nid = _seed_one_matchable()
    assert [n.id for n in repo.fetch_matchable_nodes(1)] == [nid]
    repo.nodes[nid]["review_status"] = "rejected"
    assert repo.fetch_matchable_nodes(1) == []
```

- [ ] **Step 3: Прогнать тест (фейл до правки SQL не требуется — фейк уже сужен)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_repo_cas.py -v`
Expected: 2 passed.

- [ ] **Step 4: Сузить SQL `fetch_matchable_nodes`**

В `estimate_repository.py` в `fetch_matchable_nodes` (строки ~214-218) добавить условие в `.where(...)`:

```python
            .where(
                EstimateRowModel.estimate_id == estimate_id,
                EstimateRowModel.status.in_(("pending", "error", "no_match")),
                EstimateRowModel.embedding.is_not(None),
                EstimateRowModel.review_status == "unreviewed",
            )
```

- [ ] **Step 5: Добавить CAS в SQL `save_node_match`**

Заменить `save_node_match` (строки ~226-232) на:

```python
    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        # CAS: пишем AI-снимок только если строку ещё не тронул человек. Закрывает гонку
        # read(matchable)→write с правкой ревью (SP3): нулевой rowcount → решение сохранено.
        self._session.execute(
            update(EstimateRowModel)
            .where(
                EstimateRowModel.id == node_id,
                EstimateRowModel.review_status == "unreviewed",
            )
            .values(**self._match_values(result))
        )
        self._session.commit()
```

- [ ] **Step 6: Обновить docstring-контракт в `ports.py`**

В `ports.py` заменить docstrings (строки ~213-221):

```python
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
```

- [ ] **Step 7: Прогнать матчинг-тесты (регрессия SP2)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_matching_service.py tests/test_estimate_repo_cas.py -v`
Expected: всё passed (контракт фейка и сервиса согласован).

- [ ] **Step 8: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/app/infrastructure/db/estimate_repository.py backend/app/domain/ports.py backend/tests/fakes.py backend/tests/test_estimate_repo_cas.py
git commit -m "feat(sp3): SP2-стык — matchable исключает тронутые строки, save_node_match CAS на review_status"
```

---

## Task 3: Чтение ревью — обогатить `get()` + `EstimateRowOut`

Отдать фронту кандидатов и ось ревью. Только чтение.

**Files:**
- Modify: `backend/app/infrastructure/db/estimate_repository.py:29-45` (`_row_to_entity`)
- Modify: `backend/app/api/schemas.py:129-146` (`EstimateRowOut`) + новый `MatchCandidateOut`
- Modify: `backend/tests/fakes.py` (`get` должен отдавать узлы с актуальным снимком/осью)
- Test: `backend/tests/test_estimate_detail_review.py` (новый, через TestClient)

**Interfaces:**
- Consumes: `StoredEstimateRow` +поля (Task 1); фейк-узлы +ось (Task 2).
- Produces: `EstimateRowOut` с полями `id`, `candidates: list[MatchCandidateOut]`, `review_status`, `final_article_id`, `final_code`, `final_name`, `reviewed_at`; `MatchCandidateOut(id,code,name,score)`. `source_index` наружу **не** отдаём (спека §3.1).

- [ ] **Step 1: Обогатить `_row_to_entity` (SQL-репо)**

Заменить `_row_to_entity` (строки ~30-45) на:

```python
    @staticmethod
    def _row_to_entity(m: EstimateRowModel) -> StoredEstimateRow:
        return StoredEstimateRow(
            id=m.id,
            code=m.code,
            name=m.name,
            parent_code=m.parent_code,
            section_type=m.section_type,
            depth=m.depth,
            embedding_input=m.embedding_input,
            source_index=m.source_index,
            status=m.status,
            has_embedding=m.embedding is not None,
            matched_article_id=m.matched_article_id,
            matched_code=m.matched_code,
            matched_name=m.matched_name,
            score=m.score,
            candidates=[
                MatchCandidate(id=c.get("id"), code=c["code"], name=c["name"], score=c["score"])
                for c in (m.candidates or [])
            ],
            review_status=m.review_status,
            final_article_id=m.final_article_id,
            final_code=m.final_code,
            final_name=m.final_name,
            reviewed_at=m.reviewed_at,
        )
```

Добавить импорт `MatchCandidate` в начало файла (в блок `from app.domain.entities import (...)`).

- [ ] **Step 2: Фейк `get` отдаёт актуальный снимок узлов**

В `fakes.py` заменить `FakeEstimateRepository.get` (строки ~323-327) — собирать строки из `self.nodes` (а не из замороженного `est.rows`), чтобы тесты видели правки/матч:

```python
    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        rows = [self._row_entity(r, self.nodes[r.id]) for r in est.rows]
        return Estimate(
            id=est.id, user_id=est.user_id, filename=est.filename,
            status=self.statuses.get(est.id, est.status),
            created_at=est.created_at, rows=rows,
            status_detail=self.details.get(est.id),
        )

    @staticmethod
    def _row_entity(base: StoredEstimateRow, n: dict) -> StoredEstimateRow:
        return StoredEstimateRow(
            id=base.id, code=base.code, name=base.name, parent_code=base.parent_code,
            section_type=base.section_type, depth=base.depth,
            embedding_input=base.embedding_input, source_index=base.source_index,
            status=n["status"], has_embedding=n["embedding"] is not None,
            matched_article_id=n["matched_article_id"], matched_code=n["matched_code"],
            matched_name=n["matched_name"], score=n["score"],
            candidates=[
                MatchCandidate(id=c.get("id"), code=c["code"], name=c["name"], score=c["score"])
                for c in n["candidates"]
            ],
            review_status=n["review_status"], final_article_id=n["final_article_id"],
            final_code=n["final_code"], final_name=n["final_name"],
            reviewed_at=n["reviewed_at"],
        )
```

Убедиться, что `MatchCandidate` импортирован в `fakes.py` (добавить в импорт `from app.domain.entities import (...)`).

- [ ] **Step 3: Расширить DTO `EstimateRowOut`**

В `schemas.py` заменить блок `EstimateRowOut` (строки ~129-146) на (и добавить `MatchCandidateOut` перед ним):

```python
class MatchCandidateOut(BaseModel):
    id: int | None
    code: str
    name: str
    score: float


class EstimateRowOut(BaseModel):
    id: int
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    status: str
    matched_article_id: int | None = None
    matched_code: str | None = None
    matched_name: str | None = None
    score: float | None = None
    candidates: list[MatchCandidateOut] = []
    review_status: str = "unreviewed"
    final_article_id: int | None = None
    final_code: str | None = None
    final_name: str | None = None
    reviewed_at: datetime | None = None

    @classmethod
    def from_entity(cls, r: StoredEstimateRow) -> EstimateRowOut:
        return cls(
            id=r.id, code=r.code, name=r.name, parent_code=r.parent_code,
            section_type=r.section_type, depth=r.depth, status=r.status,
            matched_article_id=r.matched_article_id, matched_code=r.matched_code,
            matched_name=r.matched_name, score=r.score,
            candidates=[
                MatchCandidateOut(id=c.id, code=c.code, name=c.name, score=c.score)
                for c in r.candidates
            ],
            review_status=r.review_status, final_article_id=r.final_article_id,
            final_code=r.final_code, final_name=r.final_name, reviewed_at=r.reviewed_at,
        )
```

- [ ] **Step 4: Тест детали через TestClient**

Create `backend/tests/test_estimate_detail_review.py`:

```python
from __future__ import annotations

from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch


def test_detail_exposes_candidates_and_review_axis(
    client, auth_headers, estimate_repo, seed_estimate
):
    eid, nid = seed_estimate  # смета с одним узлом
    estimate_repo.nodes[nid]["embedding"] = [0.1]
    estimate_repo.save_node_match(
        nid,
        NodeMatch(
            EstimateRowStatus.NEEDS_REVIEW, matched_id=7, matched_code="2.1",
            matched_name="Статья", score=0.7,
            candidates=[MatchCandidate(7, "2.1", "Статья", 0.7)],
        ),
    )
    resp = client.get(f"/api/estimates/{eid}", headers=auth_headers)
    assert resp.status_code == 200
    row = resp.json()["rows"][0]
    assert row["id"] == nid
    assert row["review_status"] == "unreviewed"
    assert row["candidates"][0]["code"] == "2.1"
    assert "source_index" not in row
```

> **Фикстуры** `client`/`auth_headers`/`estimate_repo`/`seed_estimate` — общие для SP3-тестов. Если их нет в `conftest.py`, реализатор Task 3 добавляет их там (фейк-репо через `app.dependency_overrides[get_estimate_repository]`, фейк-юзер через override `get_current_user`, `seed_estimate` создаёт смету с одним узлом и возвращает `(eid, nid)`). Существующие SP2-тесты (`test_matching_service.py`/`test_api.py`) — образец стиля override.

- [ ] **Step 5: Прогнать**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_detail_review.py -v`
Expected: passed.

- [ ] **Step 6: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/app/infrastructure/db/estimate_repository.py backend/app/api/schemas.py backend/tests/fakes.py backend/tests/test_estimate_detail_review.py backend/tests/conftest.py
git commit -m "feat(sp3): GET /estimates/{id} отдаёт кандидатов и ось ревью (EstimateRowOut +поля)"
```

---

## Task 4: Правка решения — `PATCH .../rows/{id}/review`

Сценарий валидации действия и заморозки `final_*`, новый сервис, роут.

**Files:**
- Modify: `backend/app/domain/errors.py`
- Modify: `backend/app/domain/ports.py` (`ArticleRepository.get_by_id`; `EstimateRepository.save_review_decision`)
- Modify: `backend/app/infrastructure/db/article_repository.py` (+`get_by_id`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (+`save_review_decision`)
- Create: `backend/app/services/estimate_review_service.py`
- Modify: `backend/app/api/schemas.py` (+`ReviewDecisionIn`)
- Modify: `backend/app/api/deps.py` (провайдер `get_estimate_review_service`)
- Modify: `backend/app/api/routes/estimates.py` (роут)
- Modify: `backend/tests/fakes.py` (`FakeArticleRepository.get_by_id`, `FakeEstimateRepository.save_review_decision`)
- Test: `backend/tests/test_estimate_review.py`

**Interfaces:**
- Consumes: `StoredEstimateRow` (Task 1/3), `EstimateRepository.get` (ownership), `MatchCandidate`.
- Produces:
  - `RowNotMatchedError(Exception)` → 409; `InvalidReviewActionError(Exception)` → 422.
  - `ArticleRepository.get_by_id(article_id: int) -> TemplateArticle | None`.
  - `EstimateRepository.save_review_decision(node_id: int, *, review_status: str, final_article_id: int | None, final_code: str | None, final_name: str | None) -> None` (пишет ось + `reviewed_at=now()`).
  - `EstimateReviewService.apply(estimate_id, row_id, action, article_id, requester_id, *, is_admin) -> StoredEstimateRow`.
  - `ReviewDecisionIn`: `action: Literal["confirm","pick","reject"]`, `article_id: int | None = None`.

- [ ] **Step 1: Доменные ошибки**

В `backend/app/domain/errors.py` добавить:

```python
class RowNotMatchedError(Exception):
    """Строка ещё не сматчена (status=pending) — ревью невозможно. → 409."""


class InvalidReviewActionError(Exception):
    """Действие не применимо к строке (confirm без matched_*, статья не найдена). → 422."""
```

- [ ] **Step 2: `get_by_id` в article-repo (порт + SQL + фейк)**

В `ports.py` `class ArticleRepository`, после `get_by_code` добавить:

```python
    @abstractmethod
    def get_by_id(self, article_id: int) -> TemplateArticle | None: ...
```

В `article_repository.py` после `get_by_code` (строка ~52) добавить:

```python
    def get_by_id(self, article_id: int) -> TemplateArticle | None:
        model = self._session.get(TemplateArticleModel, article_id)
        return self._to_entity(model) if model is not None else None
```

В `fakes.py` `FakeArticleRepository` добавить (рядом с `get_by_code`; если фейк хранит `self.rows: dict[str, TemplateArticle]` по коду — ищем по id):

```python
    def get_by_id(self, article_id: int) -> TemplateArticle | None:
        return next((a for a in self.rows.values() if a.id == article_id), None)
```

- [ ] **Step 3: `save_review_decision` (порт + SQL + фейк)**

В `ports.py` `class EstimateRepository`, после `save_node_match` добавить:

```python
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
```

В `estimate_repository.py` после `save_node_match` добавить:

```python
    def save_review_decision(
        self,
        node_id: int,
        *,
        review_status: str,
        final_article_id: int | None,
        final_code: str | None,
        final_name: str | None,
    ) -> None:
        self._session.execute(
            update(EstimateRowModel).where(EstimateRowModel.id == node_id).values(
                review_status=review_status,
                final_article_id=final_article_id,
                final_code=final_code,
                final_name=final_name,
                reviewed_at=func.now(),
            )
        )
        self._session.commit()
```

В `fakes.py` `FakeEstimateRepository` добавить:

```python
    def save_review_decision(
        self, node_id: int, *, review_status: str,
        final_article_id: int | None, final_code: str | None, final_name: str | None,
    ) -> None:
        n = self.nodes[node_id]
        n["review_status"] = review_status
        n["final_article_id"] = final_article_id
        n["final_code"] = final_code
        n["final_name"] = final_name
        n["reviewed_at"] = datetime(2026, 1, 2, tzinfo=timezone.utc)  # noqa: UP017
```

- [ ] **Step 4: Написать failing-тест сервиса/роута**

Create `backend/tests/test_estimate_review.py`:

```python
from __future__ import annotations

from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch


def _match(repo, nid, status, *, mid=None, code=None, name=None, score=None, cands=()):
    repo.nodes[nid]["embedding"] = [0.1]
    repo.save_node_match(
        nid,
        NodeMatch(status, matched_id=mid, matched_code=code, matched_name=name,
                  score=score, candidates=list(cands)),
    )


def test_confirm_needs_review_freezes_matched(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7, cands=[MatchCandidate(7, "2.1", "Статья", 0.7)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_status"] == "confirmed"
    assert body["final_code"] == "2.1"
    assert body["final_article_id"] == 7


def test_confirm_no_match_is_422(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 422


def test_pick_candidate_overridden(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7,
           cands=[MatchCandidate(7, "2.1", "Статья", 0.7), MatchCandidate(9, "3.2", "Иная", 0.5)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 9},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "overridden"
    assert resp.json()["final_code"] == "3.2"  # заморожено из снимка кандидата


def test_pick_manual_from_catalog(client, auth_headers, estimate_repo, article_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    article_repo.add_article(id=42, code="9.9", name="Ручная")  # хелпер фейка
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 42},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "overridden"
    assert resp.json()["final_code"] == "9.9"


def test_reject_clears_final(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NO_MATCH)
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["review_status"] == "rejected"
    assert resp.json()["final_code"] is None


def test_review_pending_row_409(client, auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate  # status=pending по умолчанию
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 409


def test_review_foreign_estimate_404(client, other_auth_headers, estimate_repo, seed_estimate):
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7, cands=[MatchCandidate(7, "2.1", "Статья", 0.7)])
    resp = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=other_auth_headers, json={"action": "confirm"},
    )
    assert resp.status_code == 404
```

> Реализатор добавляет в фейк `FakeArticleRepository` хелпер `add_article(id, code, name)` (кладёт `TemplateArticle` с `embedding=None`) и фикстуры `article_repo`/`other_auth_headers` в `conftest.py` (по образцу Task 3).

- [ ] **Step 5: Прогнать — убедиться, что падает (нет сервиса/роута)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_review.py -v`
Expected: FAIL (404/405 на PATCH — роута ещё нет).

- [ ] **Step 6: Сервис `EstimateReviewService`**

Create `backend/app/services/estimate_review_service.py`:

```python
"""Сценарий правки решения ревью (SP3). Зависит только от портов.

Пишет ось ревью (review_status/final_*), НЕ трогает AI-снимок (matched_*/candidates).
final_* морозятся в момент решения: кандидат → из снимка; ручной подбор → из справочника.
"""

from __future__ import annotations

from app.domain.entities import ReviewStatus, StoredEstimateRow
from app.domain.errors import InvalidReviewActionError, RowNotMatchedError
from app.domain.ports import ArticleRepository, EstimateRepository

_PENDING = "pending"


class EstimateReviewService:
    def __init__(self, estimates: EstimateRepository, articles: ArticleRepository) -> None:
        self._estimates = estimates
        self._articles = articles

    def apply(
        self,
        estimate_id: int,
        row_id: int,
        action: str,
        article_id: int | None,
        requester_id: int,
        *,
        is_admin: bool,
    ) -> StoredEstimateRow:
        est = self._estimates.get(estimate_id, requester_id, is_admin=is_admin)
        if est is None:
            raise LookupError("Смета не найдена")  # роут → 404
        row = next((r for r in est.rows if r.id == row_id), None)
        if row is None:
            raise LookupError("Строка не найдена")
        if row.status == _PENDING:
            raise RowNotMatchedError("Строка ещё не сматчена")

        if action == "confirm":
            self._confirm(row)
        elif action == "pick":
            self._pick(row, article_id)
        elif action == "reject":
            self._reject(row_id)
        else:
            raise InvalidReviewActionError(f"Неизвестное действие: {action!r}")

        updated = self._estimates.get(estimate_id, requester_id, is_admin=is_admin)
        assert updated is not None
        return next(r for r in updated.rows if r.id == row_id)

    def _confirm(self, row: StoredEstimateRow) -> None:
        if row.matched_article_id is None:
            raise InvalidReviewActionError("Нет рекомендации AI — confirm недоступен")
        self._estimates.save_review_decision(
            row.id, review_status=str(ReviewStatus.CONFIRMED),
            final_article_id=row.matched_article_id,
            final_code=row.matched_code, final_name=row.matched_name,
        )

    def _pick(self, row: StoredEstimateRow, article_id: int | None) -> None:
        if article_id is None:
            raise InvalidReviewActionError("pick требует article_id")
        cand = next((c for c in row.candidates if c.id == article_id), None)
        if cand is not None:
            code, name = cand.code, cand.name
        else:
            art = self._articles.get_by_id(article_id)
            if art is None:
                raise InvalidReviewActionError("Статья не найдена")
            code, name = art.article_code, art.name
        status = (
            ReviewStatus.CONFIRMED
            if article_id == row.matched_article_id
            else ReviewStatus.OVERRIDDEN
        )
        self._estimates.save_review_decision(
            row.id, review_status=str(status),
            final_article_id=article_id, final_code=code, final_name=name,
        )

    def _reject(self, row_id: int) -> None:
        self._estimates.save_review_decision(
            row_id, review_status=str(ReviewStatus.REJECTED),
            final_article_id=None, final_code=None, final_name=None,
        )
```

- [ ] **Step 7: DTO + провайдер**

В `schemas.py` добавить (рядом с прочими estimate-DTO; `Literal` импортировать из `typing`):

```python
class ReviewDecisionIn(BaseModel):
    action: Literal["confirm", "pick", "reject"]
    article_id: int | None = None
```

В начало `schemas.py` добавить `from typing import Literal`.

В `deps.py` после `get_estimate_service` добавить:

```python
def get_estimate_review_service(
    repository: EstimateRepository = Depends(get_estimate_repository),
    articles: ArticleRepository = Depends(get_repository),
) -> EstimateReviewService:
    return EstimateReviewService(estimates=repository, articles=articles)
```

Добавить импорт `from app.services.estimate_review_service import EstimateReviewService` в `deps.py`.

- [ ] **Step 8: Роут PATCH**

В `routes/estimates.py` добавить импорты:

```python
from app.api.deps import get_estimate_review_service
from app.api.schemas import EstimateRowOut, ReviewDecisionIn
from app.domain.errors import InvalidReviewActionError, RowNotMatchedError
from app.services.estimate_review_service import EstimateReviewService
```

И роут:

```python
@router.patch("/{estimate_id}/rows/{row_id}/review", response_model=EstimateRowOut)
def review_row(
    estimate_id: int,
    row_id: int,
    decision: ReviewDecisionIn,
    user: User = Depends(get_current_user),
    service: EstimateReviewService = Depends(get_estimate_review_service),
) -> EstimateRowOut:
    try:
        row = service.apply(
            estimate_id, row_id, decision.action, decision.article_id,
            user.id or 0, is_admin=user.role is Role.ADMIN,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except RowNotMatchedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except InvalidReviewActionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return EstimateRowOut.from_entity(row)
```

- [ ] **Step 9: Прогнать тесты ревью**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_review.py -v`
Expected: все passed.

- [ ] **Step 10: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/app/domain/errors.py backend/app/domain/ports.py backend/app/infrastructure/db/article_repository.py backend/app/infrastructure/db/estimate_repository.py backend/app/services/estimate_review_service.py backend/app/api/schemas.py backend/app/api/deps.py backend/app/api/routes/estimates.py backend/tests/fakes.py backend/tests/test_estimate_review.py
git commit -m "feat(sp3): PATCH /estimates/{id}/rows/{id}/review — confirm/pick/reject + заморозка final_*"
```

---

## Task 5: Лексический поиск по справочнику

**Files:**
- Modify: `backend/app/domain/ports.py` (`ArticleRepository.search`)
- Modify: `backend/app/infrastructure/db/article_repository.py` (+`search`)
- Modify: `backend/app/api/schemas.py` (+`ArticleSearchOut`)
- Modify: `backend/app/api/routes/articles.py` (роут)
- Modify: `backend/tests/fakes.py` (`FakeArticleRepository.search`)
- Test: `backend/tests/test_article_search.py`

**Interfaces:**
- Produces:
  - `ArticleRepository.search(q: str, limit: int = 20) -> list[TemplateArticle]` — `code ILIKE %q% OR name ILIKE %q%`, order by code, **не** фильтрует по embedding.
  - `ArticleSearchOut(id, code, name)`.
  - `GET /articles/search?q=...&limit=20` — `len(q.strip()) >= 2` иначе 400.

- [ ] **Step 1: Failing-тест**

Create `backend/tests/test_article_search.py`:

```python
from __future__ import annotations


def test_search_matches_code_and_name(client, auth_headers, article_repo):
    article_repo.add_article(id=1, code="1.4.1", name="Мокап фасада")
    article_repo.add_article(id=2, code="9.9", name="Демонтаж")
    resp = client.get("/api/articles/search?q=фасад", headers=auth_headers)
    assert resp.status_code == 200
    codes = [a["code"] for a in resp.json()]
    assert codes == ["1.4.1"]


def test_search_short_query_400(client, auth_headers):
    resp = client.get("/api/articles/search?q=ф", headers=auth_headers)
    assert resp.status_code == 400


def test_search_includes_unembedded(client, auth_headers, article_repo):
    # ручной подбор должен видеть статьи без эмбеддинга (embedding IS NULL)
    article_repo.add_article(id=3, code="2.2", name="Кровля")  # фейк: embedding=None
    resp = client.get("/api/articles/search?q=кров", headers=auth_headers)
    assert [a["code"] for a in resp.json()] == ["2.2"]
```

- [ ] **Step 2: Прогнать — падает (нет роута)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_article_search.py -v`
Expected: FAIL (404).

- [ ] **Step 3: Порт + фейк**

В `ports.py` `class ArticleRepository` после `get_by_id` добавить:

```python
    @abstractmethod
    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        """Лексический поиск code ILIKE %q% OR name ILIKE %q% (НЕ фильтрует по embedding)."""
        ...
```

В `fakes.py` `FakeArticleRepository.search`:

```python
    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        ql = q.lower()
        hits = [
            a for a in self.rows.values()
            if ql in a.article_code.lower() or ql in a.name.lower()
        ]
        return sorted(hits, key=lambda a: a.article_code)[:limit]
```

- [ ] **Step 4: SQL `search`**

В `article_repository.py` после `get_by_id` добавить (импортов хватает — `select`, `func` есть; `TemplateArticleModel` есть):

```python
    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        # экранируем LIKE-метасимволы в пользовательском вводе
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = (
            select(TemplateArticleModel)
            .where(
                TemplateArticleModel.article_code.ilike(like, escape="\\")
                | TemplateArticleModel.name.ilike(like, escape="\\")
            )
            .order_by(_CODE_ORDER)
            .limit(limit)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]
```

- [ ] **Step 5: DTO + роут**

В `schemas.py` добавить:

```python
class ArticleSearchOut(BaseModel):
    id: int
    code: str
    name: str
```

В `routes/articles.py` добавить импорты (`Query` из fastapi, `get_current_user`, `ArticleSearchOut`) и роут:

```python
@router.get("/search", response_model=list[ArticleSearchOut],
            dependencies=[Depends(get_current_user)])
def search_articles(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    service: ArticleService = Depends(get_article_service),
) -> list[ArticleSearchOut]:
    return [
        ArticleSearchOut(id=a.id or 0, code=a.article_code, name=a.name)
        for a in service.search(q.strip(), limit=limit)
    ]
```

> `Query(min_length=2)` даёт FastAPI-валидацию `q` (короткий `q` → 422, не 400). **Если тест требует именно 400** (явный guard), вместо `min_length` сделать `q: str = Query(...)` и в теле: `if len(q.strip()) < 2: raise HTTPException(400, "Запрос слишком короткий")`. Реализатор выбирает второй вариант, чтобы тест `test_search_short_query_400` проходил.

Добавить метод `search` в `ArticleService` (`backend/app/services/article_service.py`) — тонкий проброс в репозиторий:

```python
    def search(self, q: str, limit: int = 20) -> list[TemplateArticle]:
        return self._repository.search(q, limit=limit)
```

- [ ] **Step 6: Прогнать**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_article_search.py -v`
Expected: passed (с guard-вариантом 400).

- [ ] **Step 7: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/app/domain/ports.py backend/app/infrastructure/db/article_repository.py backend/app/services/article_service.py backend/app/api/schemas.py backend/app/api/routes/articles.py backend/tests/fakes.py backend/tests/test_article_search.py
git commit -m "feat(sp3): GET /articles/search — лексический ILIKE по code+name, без фильтра по embedding"
```

---

## Task 6: Экспорт `.xlsx`

**Files:**
- Modify: `backend/app/domain/ports.py` (`EstimateRepository.get_object_key`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (+`get_object_key`)
- Create: `backend/app/services/estimate_export_service.py`
- Modify: `backend/app/api/deps.py` (провайдер)
- Modify: `backend/app/api/routes/estimates.py` (роут)
- Modify: `backend/tests/fakes.py` (`FakeEstimateRepository.get_object_key`)
- Test: `backend/tests/test_estimate_export.py`

**Interfaces:**
- Consumes: `ObjectStorage.get`, `EstimateRepository.get` (строки), `StoredEstimateRow` (ось ревью).
- Produces:
  - `EstimateRepository.get_object_key(estimate_id, requester_id, *, is_admin) -> str | None`.
  - `EstimateExportService.export(estimate_id, requester_id, *, is_admin, strict=False) -> bytes` — кидает `LookupError` (404), `StorageError` (503), `InvalidReviewActionError` при `strict` и непросмотренных (роут → 409).
  - `GET /estimates/{id}/export[?strict=true]` → `StreamingResponse` (.xlsx).
- Правило ячейки `Статья СМР` (спека §5): `confirmed`/`overridden` → `final_code`; `rejected` → пусто; `unreviewed+confident` → `matched_code`; иначе (`unreviewed` + `needs_review`/`no_match`/`error`/`pending`) → пусто. Пишем только в **строки-узлы** по `physical_row = source_index + 2`.

- [ ] **Step 1: Проверить наличие openpyxl**

Run: `cd backend && uv run python -c "import openpyxl; print(openpyxl.__version__)"`
Expected: версия печатается (pandas-стек её тянет). Если ImportError → `cd backend && uv add openpyxl`, затем коммит lock-файлов отдельно.

- [ ] **Step 2: `get_object_key` (порт + SQL + фейк)**

В `ports.py` `class EstimateRepository` после `delete` добавить:

```python
    @abstractmethod
    def get_object_key(
        self, estimate_id: int, requester_id: int, *, is_admin: bool
    ) -> str | None:
        """original_object_key с проверкой владения (None — не найдена/чужая)."""
        ...
```

В `estimate_repository.py` после `delete`:

```python
    def get_object_key(
        self, estimate_id: int, requester_id: int, *, is_admin: bool
    ) -> str | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        return est.original_object_key
```

В `fakes.py` `FakeEstimateRepository`:

```python
    def get_object_key(
        self, estimate_id: int, requester_id: int, *, is_admin: bool
    ) -> str | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        return self._keys.get(estimate_id)
```

- [ ] **Step 3: Failing-тест экспорта (golden раунд-трип)**

Create `backend/tests/test_estimate_export.py`:

```python
from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest

from app.domain.entities import EstimateRowStatus, NodeMatch
from app.domain.errors import StorageError


def _make_original(rows: list[tuple[int, str, str]]) -> bytes:
    """rows: (physical_row, code-в-колонке-A, имя). Строка 1 — заголовки."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="№")
    ws.cell(row=1, column=2, value="Наименование")
    ws.cell(row=1, column=3, value="Статья СМР")  # пустая колонка-приёмник
    for phys, code, name in rows:
        ws.cell(row=phys, column=1, value=code)
        ws.cell(row=phys, column=2, value=name)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_export_writes_final_code_to_node_physrow(
    client, auth_headers, estimate_repo, object_storage, seed_estimate_with_source_index
):
    # узел с source_index=33 → физ.строка 35
    eid, nid = seed_estimate_with_source_index(source_index=33)
    object_storage.store["key"] = _make_original([(35, "1.1.5", "Кладка")])
    estimate_repo.nodes[nid]["embedding"] = [0.1]
    estimate_repo.save_node_match(
        nid, NodeMatch(EstimateRowStatus.NEEDS_REVIEW, matched_id=7, matched_code="2.1",
                       matched_name="Статья", score=0.7, candidates=[]),
    )
    estimate_repo.save_review_decision(
        nid, review_status="overridden", final_article_id=7,
        final_code="ИТ-9", final_name="Выбрано",
    )
    resp = client.get(f"/api/estimates/{eid}/export", headers=auth_headers)
    assert resp.status_code == 200
    wb = openpyxl.load_workbook(BytesIO(resp.content))
    ws = wb.active
    assert ws.cell(row=35, column=3).value == "ИТ-9"  # колонка «Статья СМР»


def test_export_unreviewed_needs_review_is_blank(
    client, auth_headers, estimate_repo, object_storage, seed_estimate_with_source_index
):
    eid, nid = seed_estimate_with_source_index(source_index=0)
    object_storage.store["key"] = _make_original([(2, "1", "Узел")])
    estimate_repo.nodes[nid]["embedding"] = [0.1]
    estimate_repo.save_node_match(
        nid, NodeMatch(EstimateRowStatus.NEEDS_REVIEW, matched_id=7, matched_code="2.1",
                       matched_name="Статья", score=0.7, candidates=[]),
    )
    resp = client.get(f"/api/estimates/{eid}/export", headers=auth_headers)
    wb = openpyxl.load_workbook(BytesIO(resp.content))
    assert wb.active.cell(row=2, column=3).value in (None, "")  # пусто, не AI-догадка


def test_export_strict_409_when_unreviewed(
    client, auth_headers, estimate_repo, object_storage, seed_estimate_with_source_index
):
    eid, nid = seed_estimate_with_source_index(source_index=0)
    object_storage.store["key"] = _make_original([(2, "1", "Узел")])
    estimate_repo.nodes[nid]["embedding"] = [0.1]
    estimate_repo.save_node_match(
        nid, NodeMatch(EstimateRowStatus.NO_MATCH, candidates=[]),
    )
    resp = client.get(f"/api/estimates/{eid}/export?strict=true", headers=auth_headers)
    assert resp.status_code == 409


def test_export_storage_down_503(
    client, auth_headers, estimate_repo, object_storage, seed_estimate_with_source_index
):
    eid, nid = seed_estimate_with_source_index(source_index=0)
    # ключа нет в store → FakeObjectStorage.get кинет KeyError; адаптер переведёт в StorageError
    resp = client.get(f"/api/estimates/{eid}/export", headers=auth_headers)
    assert resp.status_code == 503
```

> Реализатор добавляет фикстуры `object_storage` (FakeObjectStorage через override `get_object_storage`) и `seed_estimate_with_source_index(source_index)` в `conftest.py`. Для `test_export_storage_down_503` фейк-хранилище должно кидать `StorageError` на отсутствующий ключ — реализатор правит `FakeObjectStorage.get`: `try: return self.store[key] except KeyError: raise StorageError("нет объекта")`.

- [ ] **Step 4: Прогнать — падает**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_export.py -v`
Expected: FAIL (нет роута/сервиса).

- [ ] **Step 5: Сервис экспорта**

Create `backend/app/services/estimate_export_service.py`:

```python
"""Сценарий выгрузки сметы в .xlsx (SP3): оригинал из MinIO → заполнить «Статья СМР».

Пишем код только в строки-узлы по физ.строке source_index+2 (инвариант SP1: заголовок в
строке 1). Правило значения — см. спеку §5. Позиции-листья не трогаем (как в оригинале).
"""

from __future__ import annotations

from io import BytesIO

import openpyxl

from app.domain.entities import StoredEstimateRow
from app.domain.errors import InvalidReviewActionError, StorageError
from app.domain.ports import EstimateRepository, ObjectStorage

_HEADER = "статья смр"  # нормализованный заголовок-приёмник


class EstimateExportService:
    def __init__(self, estimates: EstimateRepository, storage: ObjectStorage) -> None:
        self._estimates = estimates
        self._storage = storage

    def export(
        self, estimate_id: int, requester_id: int, *, is_admin: bool, strict: bool = False
    ) -> bytes:
        key = self._estimates.get_object_key(estimate_id, requester_id, is_admin=is_admin)
        if key is None:
            raise LookupError("Смета не найдена")
        est = self._estimates.get(estimate_id, requester_id, is_admin=is_admin)
        assert est is not None
        if strict:
            unreviewed = [
                r for r in est.rows
                if r.review_status == "unreviewed" and r.status in ("needs_review", "no_match")
            ]
            if unreviewed:
                raise InvalidReviewActionError(
                    f"Не просмотрено строк: {len(unreviewed)}"
                )
        try:
            raw = self._storage.get(key)
        except StorageError:
            raise
        wb = openpyxl.load_workbook(BytesIO(raw))
        ws = wb.active
        col = self._find_or_create_column(ws)
        for row in est.rows:
            value = self._cell_value(row)
            if value is not None:
                ws.cell(row=row.source_index + 2, column=col, value=value)
        out = BytesIO()
        wb.save(out)
        return out.getvalue()

    @staticmethod
    def _find_or_create_column(ws) -> int:  # noqa: ANN001 — openpyxl Worksheet
        for cell in ws[1]:
            if cell.value is not None and str(cell.value).strip().casefold() == _HEADER:
                return cell.column
        col = ws.max_column + 1
        ws.cell(row=1, column=col, value="Статья СМР")
        return col

    @staticmethod
    def _cell_value(row: StoredEstimateRow) -> str | None:
        if row.review_status in ("confirmed", "overridden"):
            return row.final_code  # для confirmed это matched_code (заморожен в правке)
        if row.review_status == "rejected":
            return None
        if row.review_status == "unreviewed" and row.status == "confident":
            return row.matched_code
        return None  # unreviewed + needs_review/no_match/error/pending → пусто
```

> **Связка с SP1:** `source_index + 2` верно ровно пока SP1-парсер ([estimate_parser.py](../../backend/app/services/estimate_parser.py)) не меняет чтение (заголовок в строке 1, без `skiprows`/`dropna`/`reset_index`). Меняются в одном такте; golden раунд-трип (Step 3) — страж офсета.

- [ ] **Step 6: Провайдер + роут**

В `deps.py` добавить провайдер:

```python
def get_estimate_export_service(
    repository: EstimateRepository = Depends(get_estimate_repository),
    storage: ObjectStorage = Depends(get_object_storage),
) -> EstimateExportService:
    return EstimateExportService(estimates=repository, storage=storage)
```

Импорт `from app.services.estimate_export_service import EstimateExportService`.

В `routes/estimates.py` добавить импорты (`StreamingResponse` из `fastapi.responses`, `Query`, `get_estimate_export_service`, `EstimateExportService`, `StorageError`) и роут:

```python
@router.get("/{estimate_id}/export")
def export_estimate(
    estimate_id: int,
    strict: bool = Query(False),
    user: User = Depends(get_current_user),
    service: EstimateExportService = Depends(get_estimate_export_service),
) -> StreamingResponse:
    try:
        data = service.export(
            estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN, strict=strict
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidReviewActionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище недоступно") from exc
    filename = "estimate_matched.xlsx"
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

(`InvalidReviewActionError` уже импортирован в Task 4.)

- [ ] **Step 7: Прогнать**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_export.py -v`
Expected: 4 passed.

- [ ] **Step 8: Ruff + коммит**

```bash
cd backend && uv run ruff check .
git add backend/app/domain/ports.py backend/app/infrastructure/db/estimate_repository.py backend/app/services/estimate_export_service.py backend/app/api/deps.py backend/app/api/routes/estimates.py backend/tests/fakes.py backend/tests/test_estimate_export.py
git commit -m "feat(sp3): GET /estimates/{id}/export — .xlsx с «Статья СМР» (узлы по физ.строке, strict-гейт, 503)"
```

---

## Task 7: Staleness-sweep на ре-триггере

**Files:**
- Modify: `backend/app/domain/ports.py` (`EstimateRepository.is_stale_running`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (+`is_stale_running`)
- Modify: `backend/app/api/routes/estimates.py` (`retrigger_match` — sweep)
- Modify: `backend/tests/fakes.py` (`is_stale_running`)
- Test: `backend/tests/test_estimate_sweep.py`

**Interfaces:**
- Produces:
  - `EstimateRepository.is_stale_running(estimate_id, max_age_seconds: int) -> bool` — `status='running' AND updated_at < now() - max_age_seconds`.
  - `retrigger_match`: перед enqueue, если `is_stale_running` И `try_matching_lock` берётся → `set_status(PENDING)` + release; `detail` отражает исход.

- [ ] **Step 1: Failing-тест**

Create `backend/tests/test_estimate_sweep.py`:

```python
from __future__ import annotations


def test_retrigger_sweeps_stale_running(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"
    estimate_repo.stale_running.add(eid)  # фейк: помечаем «протухшим»
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "pending"  # сброшено
    assert "после сбоя" in resp.json()["detail"]


def test_retrigger_running_not_stale_no_reset(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"  # свежий heartbeat → не в stale_running
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "running"
    assert resp.json()["detail"] == "уже выполняется"


def test_retrigger_stale_but_lock_held_no_reset(client, auth_headers, estimate_repo, seed_estimate):
    eid, _ = seed_estimate
    estimate_repo.statuses[eid] = "running"
    estimate_repo.stale_running.add(eid)
    estimate_repo._locks.add(eid)  # живой воркер держит лок
    resp = client.post(f"/api/estimates/{eid}/match", headers=auth_headers)
    assert resp.status_code == 202
    assert estimate_repo.statuses[eid] == "running"  # не тронуто — лок занят
```

- [ ] **Step 2: Фейк `is_stale_running` + поле**

В `fakes.py` `FakeEstimateRepository.__init__` добавить `self.stale_running: set[int] = set()`. И метод:

```python
    def is_stale_running(self, estimate_id: int, max_age_seconds: int) -> bool:
        return (
            self.statuses.get(estimate_id) == "running"
            and estimate_id in self.stale_running
        )
```

- [ ] **Step 3: Прогнать — падает (нет sweep в роуте)**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_sweep.py -v`
Expected: FAIL (detail/статус не совпадают).

- [ ] **Step 4: Порт + SQL**

В `ports.py` `class EstimateRepository` после `get_status` добавить:

```python
    @abstractmethod
    def is_stale_running(self, estimate_id: int, max_age_seconds: int) -> bool:
        """True, если status='running' и updated_at старше max_age_seconds (мёртвый прогон)."""
        ...
```

В `estimate_repository.py` (импортировать `text` из sqlalchemy в начале файла — `from sqlalchemy import delete, func, select, text, update`) после `get_status`:

```python
    def is_stale_running(self, estimate_id: int, max_age_seconds: int) -> bool:
        stmt = select(EstimateModel.id).where(
            EstimateModel.id == estimate_id,
            EstimateModel.status == "running",
            EstimateModel.updated_at
            < func.now() - (text(":age * interval '1 second'").bindparams(age=max_age_seconds)),
        )
        return self._session.scalar(stmt) is not None
```

- [ ] **Step 5: Sweep в `retrigger_match`**

Заменить тело `retrigger_match` (`routes/estimates.py` строки ~32-48) на (нужны `get_settings`, `Settings`, `EstimateStatus`):

```python
@router.post("/{estimate_id}/match", status_code=status.HTTP_202_ACCEPTED)
def retrigger_match(
    estimate_id: int,
    user: User = Depends(get_current_user),
    repository: EstimateRepository = Depends(get_estimate_repository),
    task_queue: TaskQueue = Depends(get_task_queue),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    est = repository.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")

    swept = False
    if est.status == "running" and repository.is_stale_running(
        estimate_id, settings.task_time_limit_s
    ):
        # try_advisory_lock — арбитр живости: взялся → прежний держатель мёртв → сбрасываем.
        if repository.try_matching_lock(estimate_id):
            try:
                repository.set_status(
                    estimate_id, EstimateStatus.PENDING, detail="сброшено после сбоя воркера"
                )
                swept = True
            finally:
                repository.release_matching_lock(estimate_id)

    task_queue.enqueue_match(estimate_id)
    if swept:
        detail = "перезапущено после сбоя"
    elif est.status == "running":
        detail = "уже выполняется"
    else:
        detail = "поставлено в очередь"
    return {"status": "accepted", "detail": detail}
```

Добавить импорты в `routes/estimates.py`: `from app.api.deps import get_settings`, `from app.core.config import Settings` (уже есть), `from app.domain.entities import EstimateStatus, Role, User`.

- [ ] **Step 6: Прогнать**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_sweep.py -v`
Expected: 3 passed.

- [ ] **Step 7: Ruff + полный бэк-прогон + коммит**

```bash
cd backend && uv run ruff check .
cd backend && PYTHONIOENCODING=utf-8 uv run pytest
git add backend/app/domain/ports.py backend/app/infrastructure/db/estimate_repository.py backend/app/api/routes/estimates.py backend/tests/fakes.py backend/tests/test_estimate_sweep.py
git commit -m "feat(sp3): staleness-sweep на ре-триггере — мёртвый running→pending под арбитражем лока"
```

Expected полного прогона: всё passed (1 skipped — lock-интеграция SP2, как в SP2).

---

## Task 8: Frontend — переключение ревью/экспорта с моков на реальный API

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api/estimates.ts`
- Modify: `frontend/src/lib/api/articles.ts` (+`searchArticles`)
- Modify: `frontend/src/lib/reviewState.ts` (без `rationale`)
- Modify: `frontend/src/pages/estimate/ReviewRow.tsx` (поиск из реального API, без `rationale`)
- Modify: `frontend/src/pages/estimate/EstimateFlow.tsx` (загрузка/правки/экспорт через API)
- Test: `frontend/src/lib/api/estimates.test.ts`

**Interfaces:**
- Consumes (бэк-DTO): `EstimateRowOut` (Task 3), `PATCH .../review` (Task 4), `GET /articles/search` (Task 5), `GET .../export` (Task 6).
- Produces (фронт-API):
  - `getEstimate(id: number): Promise<EstimateDetail>`
  - `patchRowReview(estimateId, rowId, action, articleId?): Promise<EstimateRow>`
  - `exportEstimate(id: number): Promise<Blob>`
  - `searchArticles(q: string): Promise<ArticleHit[]>`

- [ ] **Step 1: Типы под реальный DTO**

В `frontend/src/lib/types.ts` заменить `Candidate` и `MatchRow` (строки 3-19) на:

```ts
export type MatchStatus = "confident" | "needs_review" | "no_match" | "error"
export type ReviewStatus = "unreviewed" | "confirmed" | "overridden" | "rejected"

export interface Candidate {
  id: number | null
  article_code: string
  name: string
  score: number
}

export interface MatchRow {
  row_number: number // ← row.id из бэка
  source_name: string // ← row.name
  status: MatchStatus
  score: number
  matched_code: string | null
  matched_name: string | null
  matched_article_id: number | null
  candidates: Candidate[]
  review_status: ReviewStatus
  final_article_id: number | null
  final_code: string | null
  final_name: string | null
}
```

(Удалить `rationale` и `section_name`. `ReviewRow.tsx` использовал `c.article_code`/`c.name`/`c.score` — сохранено.)

- [ ] **Step 2: API-модуль смет + тест**

Create `frontend/src/lib/api/estimates.ts`:

```ts
import type { Candidate, MatchRow, MatchStatus, ReviewStatus } from "@/lib/types"
import { apiGet, apiSend } from "./client"

interface RowDto {
  id: number
  name: string
  status: MatchStatus
  score: number | null
  matched_code: string | null
  matched_name: string | null
  matched_article_id: number | null
  candidates: { id: number | null; code: string; name: string; score: number }[]
  review_status: ReviewStatus
  final_article_id: number | null
  final_code: string | null
  final_name: string | null
}

interface DetailDto {
  id: number
  filename: string
  status: string
  rows: RowDto[]
}

export function rowFromDto(r: RowDto): MatchRow {
  return {
    row_number: r.id,
    source_name: r.name,
    status: r.status,
    score: r.score ?? 0,
    matched_code: r.matched_code,
    matched_name: r.matched_name,
    matched_article_id: r.matched_article_id,
    candidates: r.candidates.map(
      (c): Candidate => ({
        id: c.id,
        article_code: c.code,
        name: c.name,
        score: c.score,
      })
    ),
    review_status: r.review_status,
    final_article_id: r.final_article_id,
    final_code: r.final_code,
    final_name: r.final_name,
  }
}

export async function getEstimate(
  id: number
): Promise<{ fileName: string; rows: MatchRow[] }> {
  const dto = await apiGet<DetailDto>(`/estimates/${id}`)
  return { fileName: dto.filename, rows: dto.rows.map(rowFromDto) }
}

export async function patchRowReview(
  estimateId: number,
  rowId: number,
  action: "confirm" | "pick" | "reject",
  articleId?: number
): Promise<MatchRow> {
  const dto = await apiSend<RowDto>(
    "PATCH",
    `/estimates/${estimateId}/rows/${rowId}/review`,
    { action, article_id: articleId ?? null }
  )
  return rowFromDto(dto)
}

export async function exportEstimate(id: number): Promise<Blob> {
  const token = sessionStorage.getItem("ciw.auth.token")
  const res = await fetch(`/api/estimates/${id}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Экспорт не удался (${res.status})`)
  return res.blob()
}
```

Create `frontend/src/lib/api/estimates.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { rowFromDto } from "@/lib/api/estimates"

describe("rowFromDto", () => {
  it("maps DTO to MatchRow (id→row_number, code→article_code)", () => {
    const row = rowFromDto({
      id: 42,
      name: "Кладка",
      status: "needs_review",
      score: 0.7,
      matched_code: "2.1",
      matched_name: "Статья",
      matched_article_id: 7,
      candidates: [{ id: 7, code: "2.1", name: "Статья", score: 0.7 }],
      review_status: "unreviewed",
      final_article_id: null,
      final_code: null,
      final_name: null,
    })
    expect(row.row_number).toBe(42)
    expect(row.source_name).toBe("Кладка")
    expect(row.candidates[0].article_code).toBe("2.1")
    expect(row.review_status).toBe("unreviewed")
  })
})
```

- [ ] **Step 3: `searchArticles` в реальном articles-API**

В `frontend/src/lib/api/articles.ts` добавить:

```ts
import type { Candidate } from "@/lib/types"

export async function searchArticles(query: string): Promise<Candidate[]> {
  const q = query.trim()
  if (q.length < 2) return []
  const hits = await apiGet<{ id: number; code: string; name: string }[]>(
    `/articles/search?q=${encodeURIComponent(q)}`
  )
  return hits.map((h) => ({
    id: h.id,
    article_code: h.code,
    name: h.name,
    score: 0,
  }))
}
```

- [ ] **Step 4: `ReviewRow` — реальный поиск, без rationale**

В `frontend/src/pages/estimate/ReviewRow.tsx`:
- заменить импорт `import { searchArticles } from "@/lib/mock/api"` на `import { searchArticles } from "@/lib/api/articles"`;
- удалить блок `rationale` (строки ~85-92: `{row.rationale && (...)}`).

`reviewState.ts` `pickCandidate`/`manualPick` уже кладут `code`/`name` — менять не требуется (тип `Candidate` сохранил `article_code`/`name`).

- [ ] **Step 5: `EstimateFlow` — загрузка/правки/экспорт через API**

Это интеграционная склейка. Заменить мок-импорты и обработчики в `EstimateFlow.tsx`:
- Импорт: убрать `from "@/lib/mock/api"`; добавить `import { exportEstimate, getEstimate, patchRowReview } from "@/lib/api/estimates"` и `import { uploadEstimate } from "@/lib/api/estimates"` *(если загрузка идёт через бэк — иначе используем существующий upload-эндпоинт SP1: `POST /estimates`)*.
- `handleFile`: загрузить файл (SP1 `POST /estimates` → `id`), затем поллить `getEstimate(id)` до статуса `ready`/`partial_error` (ProcessingScreen), затем `dispatch({type:"load", state: initReview(fileName, rows)})`.
- Каждое действие ревью (`onPickCandidate`/`onManualPick`/`onConfirmNoMatch`/`confirmArbiter`) — вызывает `patchRowReview(...)` и обновляет строку в state из ответа.
- `handleExport`: `const blob = await exportEstimate(id)` → скачать (создать `URL.createObjectURL(blob)` + `<a download>`).

> **Замечание реализатору:** загрузка/поллинг сметы (SP1-`POST /estimates` + `GET /estimates/{id}`) — отдельная склейка; если фронт SP1 ещё на мок-загрузке, оформить `uploadEstimate(file)` в `lib/api/estimates.ts` поверх `apiUpload` и поллинг-хелпер. Дебаунс поиска (мин-длина 2, задержка ~250мс) — в `ReviewRow.runSearch`. Это самая крупная фронт-задача; держать изменения сфокусированными, типы strict.

- [ ] **Step 6: Прогнать фронт-проверки**

Run: `cd frontend && npm run typecheck`
Expected: без ошибок.

Run: `cd frontend && npx vitest run src/lib/api/estimates.test.ts`
Expected: passed.

Run: `cd frontend && npx vitest run`
Expected: вся фронт-сюита зелёная (правки в существующих `ReviewScreen.test`/`ReviewRow.test`/`EstimateFlow.test` — обновить под новые типы/API; мок `lib/mock/api` для смет больше не используется ревью-потоком).

- [ ] **Step 7: Lint + коммит**

```bash
just lint
git add frontend/src/lib/types.ts frontend/src/lib/api/estimates.ts frontend/src/lib/api/estimates.test.ts frontend/src/lib/api/articles.ts frontend/src/lib/reviewState.ts frontend/src/pages/estimate/ReviewRow.tsx frontend/src/pages/estimate/EstimateFlow.tsx frontend/src/pages/estimate/*.test.tsx
git commit -m "feat(sp3): фронт ревью/экспорта на реальный API (getEstimate/patchRowReview/exportEstimate/searchArticles), без rationale"
```

---

## Финал ветки (после Task 8)

- [ ] Полный бэк: `cd backend && uv run ruff check . && PYTHONIOENCODING=utf-8 uv run pytest`
- [ ] Полный фронт: `just lint && cd frontend && npm run typecheck && npx vitest run`
- [ ] Финальное whole-branch ревью (base = merge-base с `main`) — spec ✅ + quality, как в SP1/SP2.
- [ ] Devlog: `docs/devlog/2026-06-23-estimate-review-export.md` (отчёт; кандидаты на чистку — в TECH_DEBT, не в девлог). Закрыть в TECH_DEBT пункт «🟡 SP2-матчинг: статус running не самовосстанавливается» (погашено staleness-sweep'ом).
- [ ] `superpowers:finishing-a-development-branch`.

---

## Self-Review (выполнено при написании плана)

**Spec coverage:** §1 объём → Tasks 1-8; §2 модель данных → Task 1; §3 чтение/правка/CAS → Tasks 2-4; §3.4 край A (устаревший pick деградирует в ручной-подбор) → реализуется веткой `_pick` (кандидат ∉ снимка → справочник), названо в спеке; §4 поиск → Task 5; §5 экспорт (правило, только узлы, заголовок нормализацией, strict, 503) → Task 6; §6 sweep → Task 7; §7.1 rationale выкинут → Task 8 Step 4; §7.2 частичный экспорт → Task 6; фронт → Task 8.

**Placeholder scan:** код приведён целиком в каждом шаге; «замечания реализатору» касаются только фикстур-склейки (conftest) и крупной фронт-интеграции (Task 8 Step 5), где точная форма зависит от состояния SP1-загрузки на фронте — это явные solution-границы, не заглушки в коде.

**Type consistency:** `save_review_decision` (keyword-only) — сигнатура одинакова в порту/SQL/фейке/сервисе; `final_*` имена сквозные; `MatchCandidate(id,code,name,score)` — единый конструктор в репо/фейке/DTO; `ReviewStatus` строковые значения совпадают с правилом экспорта и фильтром CAS; фронт `rowFromDto` маппит `code`→`article_code` консистентно с `ReviewRow`/`reviewState`.
