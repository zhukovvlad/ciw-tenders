# Золотой фонд решений (decision fund) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exact-match кэш подтверждённых человеком сопоставлений (крошка → статья) перед RAG: повторяющиеся строки решаются мгновенно из накопленных ревью-решений, новое идёт в RAG как сегодня.

**Architecture:** Чистый доменный ключ/резолвер + таблица `decision_fund` (якорь `article_id`, без FK) + стадия `_apply_fund` перед `_match_nodes` (статус `matched_fund` минует арбитра) + промоушен из ревью-решений по двустороннему тумблеру `is_reference`. Источник — `confirmed/overridden`; бенчмарк held-out (фонд гоняется с `apply_fund=False`).

**Tech Stack:** Python 3.11+, FastAPI/Clean Architecture, SQLAlchemy + pgvector (Neon), Alembic (ручные ревизии), pytest + фейки портов, `uv`. Фронт: Vite+React+TS, vitest.

**Спека:** [docs/superpowers/specs/2026-06-30-decision-fund-design.md](../specs/2026-06-30-decision-fund-design.md) — источник правды.

## Global Constraints

- ruff line-length 100, `target py311`; каждый модуль с `from __future__ import annotations`; type hints обязательны.
- Комментарии/строки — по-русски, как в окружающем коде.
- Юнит/сервис-тесты НЕ ходят в реальную БД/AI — фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)) + `app.dependency_overrides`. Исключение — repo-mapping и миграция (против настроенного `DATABASE_URL`, как существующие repo-тесты).
- Команды бэка — строго `uv run` из `backend/`. Кириллица в stdout → `PYTHONIOENCODING=utf-8`.
- Файлы в LF. Перед коммитом — `uv run ruff check .` чисто; фронт — `npm run typecheck` + `npm run lint` + `prettier --check` чисто.
- Ветка: `feat/decision-fund`. Коммит на каждую задачу.
- **Якорь фонда = `article_id`** (PK `template_articles`), БЕЗ FK (зеркалит `estimate_rows.matched_article_id`; `apply_plan` хард-делит статьи).
- **`CRUMB_DERIVATION_VERSION`** — единый источник правды версии: и промоушен (пишет), и lookup (ищет) читают одну константу.
- **Анти-leakage:** бенчмарк в фонд НЕ идёт; `eval_matching` гоняет с `apply_fund=False`.
- **НЕ ТРОГАТЬ:** RAG (эмбеддинг/порог 0.90/арбитр), каталог, `classify_lexical`/LLM-классификатор, `is_excluded`, org-стрип, схему `template_articles`, `build_embedding_input` (только добавить рядом константу).

## File Structure

- `backend/app/domain/decision_fund.py` — **[создать]** `normalize_cache_key`, `cache_key_hash`, `resolve_fund_decision`, `FundHit`, `FundEntry`.
- `backend/app/domain/classification.py` — **[править]** `CRUMB_DERIVATION_VERSION` рядом с `build_embedding_input`.
- `backend/app/domain/entities.py` — **[править]** `EstimateRowStatus.MATCHED_FUND`.
- `backend/app/domain/ports.py` — **[править]** порт `DecisionFundRepository`; +методы в `EstimateRepository`.
- `backend/app/infrastructure/db/models.py` — **[править]** `DecisionFundModel`, `estimates.is_reference`.
- `backend/alembic/versions/0007_decision_fund.py` — **[создать]** таблица + колонка (ручная ревизия).
- `backend/app/infrastructure/db/decision_fund_repository.py` — **[создать]** `SqlAlchemyDecisionFundRepository`.
- `backend/app/infrastructure/db/estimate_repository.py` — **[править]** `set_reference`/`fetch_reference_estimate_ids`/`fetch_promotable_rows`/`fetch_pending_nodes`/`save_fund_hit`.
- `backend/app/services/decision_fund_service.py` — **[создать]** `promote`/`unreference`/`rebuild`.
- `backend/app/services/estimate_matching_service.py` — **[править]** `_apply_fund`, условный гейт, `apply_fund`-флаг, счётчик.
- `backend/app/api/deps.py` — **[править]** фабрики фонд-репо/сервиса; `apply_fund` в `build_estimate_matching_service`.
- `backend/app/api/routes/estimates.py` + `schemas.py` — **[править]** тумблер, админ-rebuild, `matched_fund` в DTO.
- `backend/app/scripts/eval_matching.py` — **[править]** `apply_fund=False`.
- `backend/tests/…` — юниты/сервис/API; `tests/fakes.py` — `FakeDecisionFundRepository` + методы.
- `frontend/src/lib/types.ts`, `lib/api/estimates.ts`, `pages/estimate/*` — **[править]** статус/бейдж/тумблер + vitest.

---

### Task 1: Домен — ключ, резолвер, версия, статус

**Files:**
- Create: `backend/app/domain/decision_fund.py`
- Modify: `backend/app/domain/classification.py`, `backend/app/domain/entities.py`
- Test: `backend/tests/test_decision_fund.py`

**Interfaces:**
- Produces: `normalize_cache_key(embedding_input: str) -> str`; `cache_key_hash(key: str) -> str` (sha256 hex); `resolve_fund_decision(live_article_ids: Sequence[int]) -> int | None`; `FundHit(article_id: int, code: str, name: str)`; `FundEntry(cache_key_hash: str, cache_key: str, crumb_version: int, article_id: int, source_estimate_id: int, source_row_id: int)`; `CRUMB_DERIVATION_VERSION: int` (в `classification.py`); `EstimateRowStatus.MATCHED_FUND`.

- [ ] **Step 1: Написать падающие юниты**

В `backend/tests/test_decision_fund.py`:

```python
from __future__ import annotations

from app.domain.decision_fund import (
    cache_key_hash,
    normalize_cache_key,
    resolve_fund_decision,
)


def test_normalize_collapses_case_and_whitespace() -> None:
    a = normalize_cache_key("Подготовительные  работы. \tМОКАП ")
    b = normalize_cache_key("подготовительные работы. мокап")
    assert a == b == "подготовительные работы. мокап"


def test_hash_is_stable_and_hex64() -> None:
    h = cache_key_hash("подготовительные работы. мокап")
    assert h == cache_key_hash("подготовительные работы. мокап")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def test_resolve_single_live_answer() -> None:
    assert resolve_fund_decision([7]) == 7
    assert resolve_fund_decision([7, 7, 7]) == 7  # повторы одной статьи → она


def test_resolve_conflict_and_empty_give_none() -> None:
    assert resolve_fund_decision([7, 9]) is None   # конфликт
    assert resolve_fund_decision([]) is None        # промах/только мёртвые
```

- [ ] **Step 2: Прогон — RED**

Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_decision_fund.py -q`
Expected: FAIL (модуль `app.domain.decision_fund` не существует).

- [ ] **Step 3: Реализация домена**

`backend/app/domain/decision_fund.py`:

```python
"""Чистые функции золотого фонда решений: нормализация ключа + guard «единственный ответ».

Без БД/AI. Ключ строится поверх уже-org-стрипнутой крошки (embedding_input) — он код-free и
этап-free, поэтому повторяемая работа даёт один ключ независимо от нумерации/этапа.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FundHit:
    """Живое попадание фонда (id + текущие код/имя из каталога — apply-time, без N+1)."""

    article_id: int
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class FundEntry:
    """Запись для upsert при промоушене."""

    cache_key_hash: str
    cache_key: str
    crumb_version: int
    article_id: int
    source_estimate_id: int
    source_row_id: int


def normalize_cache_key(embedding_input: str) -> str:
    """Детерминированная нормализация: регистр + схлопывание пробелов. Версия крошки НЕ внутри
    ключа (хранится отдельной колонкой)."""
    return re.sub(r"\s+", " ", embedding_input.strip().lower())


def cache_key_hash(key: str) -> str:
    """sha256-hex нормализованного ключа — для unique-индекса (TEXT в btree-unique = мина)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def resolve_fund_decision(live_article_ids: Sequence[int]) -> int | None:
    """Guard «единственный ответ»: ровно одна различная статья среди ЖИВЫХ → она; иначе None
    (0 → промах/только мёртвые; ≥2 различных → конфликт → молчим)."""
    distinct = set(live_article_ids)
    return next(iter(distinct)) if len(distinct) == 1 else None
```

В `backend/app/domain/classification.py` — рядом с `build_embedding_input` добавить:

```python
# Версия крошко-деривации для золотого фонда: единый источник правды. И промоушен (пишет
# crumb_version), и lookup (ищет по версии) читают ЭТУ константу. Меняем логику крошки
# (build_embedding_input / org-стрип / резолв предков) → бампаем версию (старый фонд мажет мимо).
CRUMB_DERIVATION_VERSION = 1
```

В `backend/app/domain/entities.py` — в `EstimateRowStatus` добавить значение (после `ERROR`):

```python
    MATCHED_FUND = "matched_fund"  # решено золотым фондом мимо арбитра (виден, переопределяем)
```

- [ ] **Step 4: Прогон — GREEN**

Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_decision_fund.py -q` → PASS. Затем `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/decision_fund.py backend/app/domain/classification.py backend/app/domain/entities.py backend/tests/test_decision_fund.py
git commit -m "feat(domain): ключ/резолвер золотого фонда + CRUMB_DERIVATION_VERSION + статус matched_fund"
```

---

### Task 2: БД — таблица `decision_fund` + `estimates.is_reference`

**Files:**
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0007_decision_fund.py`

**Interfaces:**
- Produces: ORM `DecisionFundModel` (поля §4.1 спеки), колонка `EstimateModel.is_reference`.

- [ ] **Step 1: ORM-модели**

В `models.py` добавить колонку в `EstimateModel`:

```python
    is_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
```

И новую модель (рядом с прочими; импорт `CHAR`/`SmallInteger` из sqlalchemy при нужде):

```python
class DecisionFundModel(Base):
    __tablename__ = "decision_fund"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)  # дебаг, не уникальный
    crumb_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)  # БЕЗ FK (см. спеку §4.1)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    origin: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'human_review'"))
    source_estimate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("cache_key_hash", "crumb_version", "article_id",
                         name="uq_decision_fund_key_version_article"),
    )
```

- [ ] **Step 2: Ручная Alembic-ревизия**

Сначала `uv run alembic heads` — подтвердить, что голова `0006`. Создать `alembic/versions/0007_decision_fund.py`:

```python
"""decision fund table + estimates.is_reference

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimates",
        sa.Column("is_reference", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "decision_fund",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cache_key_hash", sa.String(64), nullable=False),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("crumb_version", sa.SmallInteger(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),  # без FK — снимок переживает churn
        sa.Column("votes", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("origin", sa.String(16), nullable=False, server_default=sa.text("'human_review'")),
        sa.Column("source_estimate_id", sa.Integer(), nullable=False),
        sa.Column("source_row_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cache_key_hash", "crumb_version", "article_id",
                            name="uq_decision_fund_key_version_article"),
    )
    op.create_index("ix_decision_fund_lookup", "decision_fund", ["cache_key_hash", "crumb_version"])


def downgrade() -> None:
    op.drop_index("ix_decision_fund_lookup", table_name="decision_fund")
    op.drop_table("decision_fund")
    op.drop_column("estimates", "is_reference")
```

- [ ] **Step 3: Применить и откатить (проверка обратимости)**

Run: `uv run alembic upgrade head` → ОК. Затем `uv run alembic downgrade -1` → ОК. Затем снова `uv run alembic upgrade head`.
Expected: без ошибок; таблица создаётся/удаляется.

- [ ] **Step 4: Прогон импорта моделей**

Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_models.py -q` (модели импортируются, существующие зелёные). `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/models.py backend/alembic/versions/0007_decision_fund.py
git commit -m "feat(db): таблица decision_fund + estimates.is_reference (ревизия 0007)"
```

---

### Task 3: Порт + SQL-репозиторий фонда + фейк

**Files:**
- Modify: `backend/app/domain/ports.py`
- Create: `backend/app/infrastructure/db/decision_fund_repository.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_decision_fund_repository.py`

**Interfaces:**
- Consumes: `FundHit`, `FundEntry` (Task 1).
- Produces: порт `DecisionFundRepository` — `lookup(key_hashes: Sequence[str], crumb_version: int) -> dict[str, list[FundHit]]`, `upsert(entries: Sequence[FundEntry]) -> None`, `clear() -> None`. `SqlAlchemyDecisionFundRepository`. `FakeDecisionFundRepository`.

- [ ] **Step 1: Падающий repo-маппинг-тест**

`backend/tests/test_decision_fund_repository.py` (против настроенного DB, как существующие repo-тесты; если их паттерн — фикстура сессии, повторить её):

```python
from __future__ import annotations

from app.domain.decision_fund import FundEntry
from app.infrastructure.db.decision_fund_repository import SqlAlchemyDecisionFundRepository
# … фикстура session как в других repo-тестах (см. tests/test_estimate_repository_mapping.py)


def test_lookup_returns_only_live_articles(session, seed_article) -> None:
    live = seed_article(code="1.4", name="Мокап")           # хелпер сидит статью, возвращает id
    repo = SqlAlchemyDecisionFundRepository(session)
    repo.upsert([
        FundEntry("h1", "k1", 1, live, 10, 100),
        FundEntry("h1", "k1", 1, 999999, 11, 101),          # мёртвый article_id
    ])
    hits = repo.lookup(["h1"], crumb_version=1)
    assert [h.article_id for h in hits["h1"]] == [live]      # мёртвый отфильтрован JOIN-ом
    assert hits["h1"][0].name == "Мокап"


def test_lookup_filters_by_version(session, seed_article) -> None:
    a = seed_article(code="1.4", name="Мокап")
    repo = SqlAlchemyDecisionFundRepository(session)
    repo.upsert([FundEntry("h2", "k2", 1, a, 10, 100)])
    assert repo.lookup(["h2"], crumb_version=2) == {}        # другая версия → пусто


def test_upsert_increments_votes_and_updates_source(session, seed_article) -> None:
    a = seed_article(code="1.4", name="Мокап")
    repo = SqlAlchemyDecisionFundRepository(session)
    repo.upsert([FundEntry("h3", "k3", 1, a, 10, 100)])
    repo.upsert([FundEntry("h3", "k3", 1, a, 22, 222)])      # та же пара, другой источник
    row = session.execute(
        __import__("sqlalchemy").text(
            "SELECT votes, source_estimate_id FROM decision_fund "
            "WHERE cache_key_hash='h3' AND crumb_version=1 AND article_id=:a"
        ), {"a": a}
    ).one()
    assert row.votes == 2 and row.source_estimate_id == 22   # source_* = последний
```

(Реализатор: `seed_article` — мелкий локальный хелпер/фикстура, вставляет `TemplateArticleModel` с `embedding_input` и возвращает id; повторить стиль существующих repo-тестов.)

- [ ] **Step 2: Прогон — RED**

Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_decision_fund_repository.py -q`
Expected: FAIL (нет `SqlAlchemyDecisionFundRepository`).

- [ ] **Step 3: Порт + реализация**

В `ports.py`:

```python
class DecisionFundRepository(ABC):
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
```

`backend/app/infrastructure/db/decision_fund_repository.py`:

```python
"""SQL-адаптер золотого фонда. Lookup фильтрует живые статьи JOIN-ом к каталогу (домен чист)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.decision_fund import FundEntry, FundHit
from app.infrastructure.db.models import DecisionFundModel, TemplateArticleModel


class SqlAlchemyDecisionFundRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(
        self, key_hashes: Sequence[str], crumb_version: int
    ) -> dict[str, list[FundHit]]:
        if not key_hashes:
            return {}
        stmt = (
            select(
                DecisionFundModel.cache_key_hash,
                TemplateArticleModel.id,
                TemplateArticleModel.article_code,
                TemplateArticleModel.name,
            )
            .join(TemplateArticleModel, TemplateArticleModel.id == DecisionFundModel.article_id)
            .where(
                DecisionFundModel.cache_key_hash.in_(list(key_hashes)),
                DecisionFundModel.crumb_version == crumb_version,
            )
        )
        out: dict[str, list[FundHit]] = {}
        for r in self._session.execute(stmt):
            out.setdefault(r.cache_key_hash, []).append(
                FundHit(article_id=r.id, code=r.article_code, name=r.name)
            )
        return out

    def upsert(self, entries: Sequence[FundEntry]) -> None:
        for e in entries:
            stmt = (
                pg_insert(DecisionFundModel)
                .values(
                    cache_key_hash=e.cache_key_hash, cache_key=e.cache_key,
                    crumb_version=e.crumb_version, article_id=e.article_id,
                    source_estimate_id=e.source_estimate_id, source_row_id=e.source_row_id,
                )
                .on_conflict_do_update(
                    constraint="uq_decision_fund_key_version_article",
                    set_={
                        "votes": DecisionFundModel.votes + 1,
                        "source_estimate_id": e.source_estimate_id,
                        "source_row_id": e.source_row_id,
                        "updated_at": text("now()"),
                    },
                )
            )
            self._session.execute(stmt)
        self._session.commit()  # один commit на весь промоушен (атомарность + латентность)

    def clear(self) -> None:
        self._session.execute(delete(DecisionFundModel))
        self._session.commit()
```

В `tests/fakes.py` добавить `FakeDecisionFundRepository`:

```python
class FakeDecisionFundRepository:
    def __init__(self) -> None:
        # (hash, version) -> {article_id -> FundHit}; живость эмулируется наличием в каталоге-фейке
        self.entries: dict[tuple[str, int], dict[int, FundHit]] = {}

    def lookup(self, key_hashes, crumb_version):
        out = {}
        for h in key_hashes:
            hits = list(self.entries.get((h, crumb_version), {}).values())
            if hits:
                out[h] = hits
        return out

    def upsert(self, entries):
        for e in entries:
            bucket = self.entries.setdefault((e.cache_key_hash, e.crumb_version), {})
            # фейк хранит FundHit напрямую (тест задаёт code/name через seed_hit-хелпер)
            bucket.setdefault(e.article_id, FundHit(e.article_id, "", ""))

    def clear(self):
        self.entries.clear()

    def seed_hit(self, key_hash, version, hit: FundHit):  # тест-хелпер
        self.entries.setdefault((key_hash, version), {})[hit.article_id] = hit
```

(`FundHit` импортировать в fakes.)

- [ ] **Step 4: Прогон — GREEN**

Run: `PYTHONIOENCODING=utf-8 uv run pytest tests/test_decision_fund_repository.py -q` → PASS. `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/ports.py backend/app/infrastructure/db/decision_fund_repository.py backend/tests/fakes.py backend/tests/test_decision_fund_repository.py
git commit -m "feat(infra): SQL-репозиторий фонда (lookup живых JOIN-ом, upsert votes/source) + фейк"
```

---

### Task 4: Методы `EstimateRepository` для фонда

**Files:**
- Modify: `backend/app/domain/ports.py`, `backend/app/infrastructure/db/estimate_repository.py`, `backend/tests/fakes.py`
- Test: `backend/tests/test_estimate_repository_mapping.py` (или новый)

**Interfaces:**
- Produces (на `EstimateRepository`): `set_reference(estimate_id, value: bool) -> None`; `fetch_reference_estimate_ids() -> list[int]`; `fetch_promotable_rows(estimate_id) -> list[PromotableRow]` (`PromotableRow(row_id, embedding_input, status, review_status, final_article_id)`); `fetch_pending_nodes(estimate_id) -> list[PendingNode]` (`PendingNode(row_id, embedding_input)`, `status='pending'` AND `review_status='unreviewed'`); `save_fund_hit(node_id, article_id, code, name) -> None`.

- [ ] **Step 1: Падающий repo-тест**

```python
def test_save_fund_hit_writes_snapshot_and_skips_arbiter(session, seed_estimate_row) -> None:
    rid = seed_estimate_row(status="pending", review_status="unreviewed", embedding_input="к. лист")
    repo = SqlAlchemyEstimateRepository(session)
    repo.save_fund_hit(rid, article_id=5, code="1.4", name="Мокап")
    row = repo._row(rid)  # мелкий хелпер чтения; или прямой select
    assert row.status == "matched_fund"
    assert row.matched_article_id == 5 and row.matched_code == "1.4"
    assert row.candidates is None and row.score is None


def test_save_fund_hit_cas_skips_reviewed(session, seed_estimate_row) -> None:
    rid = seed_estimate_row(status="pending", review_status="confirmed", embedding_input="x")
    repo = SqlAlchemyEstimateRepository(session)
    repo.save_fund_hit(rid, article_id=5, code="1.4", name="Мокап")
    assert repo._row(rid).status != "matched_fund"  # CAS по unreviewed не дал перезаписать
```

- [ ] **Step 2: Прогон — RED** → FAIL (нет `save_fund_hit`).

- [ ] **Step 3: Реализация + порт**

В `ports.py` (`EstimateRepository`) добавить абстрактные методы с теми же сигнатурами (см. Interfaces); добавить доменные dataclass `PromotableRow`/`PendingNode` в `entities.py`.

В `estimate_repository.py`:

```python
    def set_reference(self, estimate_id: int, value: bool) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(is_reference=value)
        )
        self._session.commit()

    def fetch_reference_estimate_ids(self) -> list[int]:
        return list(
            self._session.scalars(
                select(EstimateModel.id).where(EstimateModel.is_reference.is_(True))
            )
        )

    def fetch_promotable_rows(self, estimate_id: int) -> list[PromotableRow]:
        stmt = select(
            EstimateRowModel.id, EstimateRowModel.embedding_input,
            EstimateRowModel.status, EstimateRowModel.review_status,
            EstimateRowModel.final_article_id,
        ).where(EstimateRowModel.estimate_id == estimate_id)
        return [
            PromotableRow(r.id, r.embedding_input, r.status, r.review_status, r.final_article_id)
            for r in self._session.execute(stmt)
        ]

    def fetch_pending_nodes(self, estimate_id: int) -> list[PendingNode]:
        stmt = select(EstimateRowModel.id, EstimateRowModel.embedding_input).where(
            EstimateRowModel.estimate_id == estimate_id,
            EstimateRowModel.status == "pending",
            EstimateRowModel.review_status == "unreviewed",  # защитный: pending ⟹ unreviewed
        )
        return [PendingNode(r.id, r.embedding_input) for r in self._session.execute(stmt)]

    def save_fund_hit(self, node_id: int, article_id: int, code: str, name: str) -> None:
        # CAS по unreviewed — как save_node_match; candidates/score обнуляем (снимок без кандидатов)
        self._session.execute(
            update(EstimateRowModel)
            .where(EstimateRowModel.id == node_id, EstimateRowModel.review_status == "unreviewed")
            .values(status="matched_fund", matched_article_id=article_id,
                    matched_code=code, matched_name=name, candidates=None, score=None,
                    match_error=None)
        )
        self._session.commit()
```

Зеркально реализовать эти методы в `FakeEstimateRepository` (tests/fakes.py): `set_reference` ставит флаг; `fetch_reference_estimate_ids` фильтрует; `fetch_promotable_rows`/`fetch_pending_nodes` отдают строки из фейк-хранилища; `save_fund_hit` пишет снимок с тем же CAS по `review_status=='unreviewed'`.

- [ ] **Step 4: Прогон** — `PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_repository_mapping.py -q` → PASS; `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/ports.py backend/app/domain/entities.py backend/app/infrastructure/db/estimate_repository.py backend/tests/fakes.py backend/tests/test_estimate_repository_mapping.py
git commit -m "feat(infra): EstimateRepository — set_reference/fetch_promotable/pending/save_fund_hit"
```

---

### Task 5: Сервис промоушена (`promote` / `unreference` / `rebuild`)

**Files:**
- Create: `backend/app/services/decision_fund_service.py`
- Test: `backend/tests/test_decision_fund_service.py`

**Interfaces:**
- Consumes: `EstimateRepository` (Task 4), `DecisionFundRepository` (Task 3), `normalize_cache_key`/`cache_key_hash`/`FundEntry`/`CRUMB_DERIVATION_VERSION`.
- Produces: `DecisionFundService(estimates, fund)` с `promote(estimate_id)`, `unreference(estimate_id)`, `rebuild()`.

- [ ] **Step 1: Падающие сервис-тесты (фейки)**

```python
def test_promote_takes_only_confirmed_overridden() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    # строки: confirmed→в фонд, unreviewed→нет, confident-unreviewed→нет
    eid = repo.seed_estimate_with_rows([
        Row(embedding_input="a", status="needs_review", review_status="confirmed", final_article_id=5),
        Row(embedding_input="b", status="needs_review", review_status="unreviewed", final_article_id=None),
        Row(embedding_input="c", status="confident", review_status="unreviewed", final_article_id=9),
    ])
    DecisionFundService(repo, fund).promote(eid)
    keys = {k for (k, _v) in fund.entries}
    assert keys == {cache_key_hash(normalize_cache_key("a"))}   # только confirmed-строка
    assert repo.is_reference(eid) is True


def test_promote_anti_inflation_skips_confirmed_fund_hit() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    eid = repo.seed_estimate_with_rows([
        Row(embedding_input="a", status="matched_fund", review_status="confirmed", final_article_id=5),
        Row(embedding_input="b", status="matched_fund", review_status="overridden", final_article_id=7),
    ])
    DecisionFundService(repo, fund).promote(eid)
    # matched_fund+confirmed НЕ промоутится (накрутка); matched_fund+overridden → промоутится
    assert (cache_key_hash(normalize_cache_key("a")), 1) not in fund.entries
    assert (cache_key_hash(normalize_cache_key("b")), 1) in fund.entries


def test_rebuild_clears_and_repromotes_reference_only() -> None:
    repo, fund = FakeEstimateRepository(), FakeDecisionFundRepository()
    e1 = repo.seed_estimate_with_rows([Row("a", "needs_review", "confirmed", 5)]); repo.set_reference(e1, True)
    e2 = repo.seed_estimate_with_rows([Row("b", "needs_review", "confirmed", 9)])  # НЕ reference
    fund.upsert([FundEntry("stale", "stale", 1, 1, 0, 0)])
    DecisionFundService(repo, fund).rebuild()
    keys = {k for (k, _v) in fund.entries}
    assert keys == {cache_key_hash(normalize_cache_key("a"))}  # stale убран, e2 не вошёл
```

(`Row`/`seed_estimate_with_rows`/`is_reference` — хелперы фейка из Task 4; добавить недостающее.)

- [ ] **Step 2: Прогон — RED** → FAIL (нет `DecisionFundService`).

- [ ] **Step 3: Реализация**

`backend/app/services/decision_fund_service.py`:

```python
"""Use-case золотого фонда: промоушен из ревью-решений, снятие источника, пересборка.

Предикат и анти-накрутка — здесь (бизнес-логика), репозитории дают примитивы.
"""

from __future__ import annotations

from app.domain.classification import CRUMB_DERIVATION_VERSION
from app.domain.decision_fund import FundEntry, cache_key_hash, normalize_cache_key
from app.domain.ports import DecisionFundRepository, EstimateRepository

_PROMOTABLE_REVIEW = {"confirmed", "overridden"}


class DecisionFundService:
    def __init__(self, estimates: EstimateRepository, fund: DecisionFundRepository) -> None:
        self._estimates = estimates
        self._fund = fund

    def promote(self, estimate_id: int) -> int:
        entries: list[FundEntry] = []
        for r in self._estimates.fetch_promotable_rows(estimate_id):
            if r.review_status not in _PROMOTABLE_REVIEW:
                continue
            # анти-накрутка: фонд-хит, который человек лишь ПОДТВЕРДИЛ, обратно не рекрутируем
            if r.status == "matched_fund" and r.review_status == "confirmed":
                continue
            if r.final_article_id is None:
                continue  # перестраховка (confirmed/overridden гарантируют непустой, см. спеку §2.1)
            key = normalize_cache_key(r.embedding_input)
            entries.append(FundEntry(
                cache_key_hash=cache_key_hash(key), cache_key=key,
                crumb_version=CRUMB_DERIVATION_VERSION, article_id=r.final_article_id,
                source_estimate_id=estimate_id, source_row_id=r.row_id,
            ))
        self._fund.upsert(entries)
        # флаг ставим только если реально что-то запромоутили — иначе «пустая» эталонная смета
        # (0 confirmed-строк), которую rebuild гоняет вхолостую. Эндпоинт вернёт count → UI подскажет.
        if entries:
            self._estimates.set_reference(estimate_id, True)
        return len(entries)

    def unreference(self, estimate_id: int) -> None:
        self._estimates.set_reference(estimate_id, False)

    def rebuild(self) -> None:
        self._fund.clear()
        for eid in self._estimates.fetch_reference_estimate_ids():
            self.promote(eid)
```

- [ ] **Step 4: Прогон** → PASS; `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/decision_fund_service.py backend/tests/test_decision_fund_service.py backend/tests/fakes.py
git commit -m "feat(service): промоушен фонда (предикат confirmed/overridden + анти-накрутка) + rebuild"
```

---

### Task 6: Интеграция в матчинг — `_apply_fund`, гейт, выключатель, счётчик

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`, `backend/app/api/deps.py`, `backend/app/scripts/eval_matching.py`
- Test: `backend/tests/test_estimate_matching_service.py`

**Interfaces:**
- Consumes: `DecisionFundRepository`, `normalize_cache_key`/`cache_key_hash`/`resolve_fund_decision`/`CRUMB_DERIVATION_VERSION`, `fetch_pending_nodes`/`save_fund_hit`.
- Produces: `EstimateMatchingService(..., fund: DecisionFundRepository, apply_fund: bool = True)`; стадия `_apply_fund`; счётчик `matched_fund` в summary.

- [ ] **Step 1: Падающие сервис-тесты**

```python
def test_apply_fund_hit_writes_matched_fund_and_skips_arbiter() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("Подг. МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    row = repo.get(est.id, 1, is_admin=True).rows[0]
    assert row.status == "matched_fund" and row.matched_article_id == 5


def test_apply_fund_conflict_and_miss_stay_pending() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    key = cache_key_hash(normalize_cache_key("Подг. МОКАП"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    fund.seed_hit(key, CRUMB_DERIVATION_VERSION, FundHit(7, "1.5", "Иное"))  # 2-е живое → конфликт
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # конфликт → RAG


def test_apply_fund_disabled_is_noop() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    fund.seed_hit(cache_key_hash(normalize_cache_key("Подг. МОКАП")),
                  CRUMB_DERIVATION_VERSION, FundHit(5, "1.4", "Мокап"))
    svc = _matching_service(repo, articles, fund, apply_fund=False)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # выключен → не трогает


def test_crumb_version_bump_misses_old_keys() -> None:
    repo, articles = FakeEstimateRepository(), FakeRepository(candidates=[])
    fund = FakeDecisionFundRepository()
    est = repo.create(NewEstimate(1, "f.xlsx", "k"),
                      [EstimateNode("1.1.5", "МОКАП", "1.1", None, "Подг. МОКАП", 0, 3)])
    # запись осела на СТАРОЙ версии (99); лукап идёт на CRUMB_DERIVATION_VERSION → промах
    fund.seed_hit(cache_key_hash(normalize_cache_key("Подг. МОКАП")), 99, FundHit(5, "1.4", "Мокап"))
    svc = _matching_service(repo, articles, fund, apply_fund=True)
    svc._apply_fund(est.id)  # noqa: SLF001
    assert repo.get(est.id, 1, is_admin=True).rows[0].status == "pending"  # версия не та → холодно
```

(Хелпер `_matching_service(repo, articles, fund, apply_fund)` — как существующий `_classify_service`, плюс fund/apply_fund.)

- [ ] **Step 2: Прогон — RED** → FAIL.

- [ ] **Step 3: Реализация**

В `__init__` `EstimateMatchingService` добавить параметры `fund: DecisionFundRepository`, `apply_fund: bool = True` и сохранить (`self._fund`, `self._apply_fund_enabled`).

**КРИТИЧНО — пред-инициализация и ОБА call-site.** `_log_summary` зовётся в ДВУХ местах `match_estimate`:
успех (строка 84) и `except Exception` (строка 91). Поэтому `excluded`/`counts` предынициализированы ДО `try`
(строки 59-60) — чтобы except-путь мог их передать, даже если исключение прилетело раньше присвоения. Новый
`fund_hits` **обязан** следовать тому же паттерну, иначе except-путь бросит `UnboundLocalError` и замаскирует
исходное исключение (а happy-path тесты этого не поймают).

(1) Рядом с `excluded = 0` (строка 59) добавить:

```python
        fund_hits = 0
```

(2) В `try`, заменить существующий безусловный блок гейта (строки 67-72) на: стадия фонда → условный гейт:

```python
            self._embed_nodes(estimate_id)
            logger.debug("Матчинг %s: эмбеддинг завершён", estimate_id)
            fund_hits = self._apply_fund(estimate_id)  # NEW: до арбитра
            # гейт каталога — только если после фонда остались не-фондовые matchable (pending).
            # На полностью-фондовой смете (0 pending) спурьозный DictionaryNotReadyError не летит.
            if self._estimates.count_unfinished_nodes(estimate_id):
                total, pending = self._articles.matching_readiness()
                if total == 0 or pending > 0:
                    raise DictionaryNotReadyError(total=total, pending=pending)
            counts = self._match_nodes(estimate_id)
```

(3) **Оба** вызова `_log_summary` (строки 84 и 91) → добавить `fund_hits`:

```python
            self._log_summary(estimate_id, counts, excluded, fund_hits, start)
```

(4) Сигнатуру `_log_summary` расширить `fund_hits: int` (после `excluded`), добавить в формат-строку
(`… matched_fund=%d …`, аргумент `fund_hits`) и в `extra={... "matched_fund": fund_hits}`.

Метод:

```python
    def _apply_fund(self, estimate_id: int) -> int:
        if not self._apply_fund_enabled:
            return 0
        nodes = self._estimates.fetch_pending_nodes(estimate_id)  # все pending, вектор не нужен
        if not nodes:
            return 0
        by_hash = {n.row_id: cache_key_hash(normalize_cache_key(n.embedding_input)) for n in nodes}
        found = self._fund.lookup(list(set(by_hash.values())), CRUMB_DERIVATION_VERSION)
        hits = 0
        for n in nodes:
            candidates = found.get(by_hash[n.row_id], [])
            decision = resolve_fund_decision([h.article_id for h in candidates])
            if decision is None:
                continue  # промах/конфликт → остаётся pending → RAG
            hit = next(h for h in candidates if h.article_id == decision)
            self._estimates.save_fund_hit(n.row_id, hit.article_id, hit.code, hit.name)
            hits += 1
        return hits
```

(Импорты домена; флаг сохранить как `self._apply_fund_enabled = apply_fund`.) Счётчик добавить в сигнатуру/тело `_log_summary` (новый аргумент `fund_hits`, лог `extra={... "matched_fund": fund_hits}`).

В `deps.py` `build_estimate_matching_service(session, *, apply_fund: bool = True)`: создать `SqlAlchemyDecisionFundRepository(session)`, передать `fund=...` и `apply_fund=apply_fund` в конструктор. (FastAPI DI-путь — тоже прокинуть фонд; web по умолчанию `apply_fund=True`.)

В `eval_matching.py` (Task §7 спеки): `build_estimate_matching_service(session, apply_fund=False).match_estimate(estimate.id)`.

- [ ] **Step 4: Прогон файла** — `PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_matching_service.py -q` → PASS (новые + существующие). `uv run ruff check .` → чисто.

> **Осознать при прогоне (не баги):** (1) условие гейта — `count_unfinished_nodes` (= `status=='pending'`),
> чуть шире спецовского «matchable» (pending+вектор): транзиентно-безвекторный pending тоже даёт `remaining>0`
> → гейт проверится. Безопасно (спурьозных срабатываний строго ≤ сегодняшних), отдельный `count_matchable` не
> заводим. (2) Побочка: смета со ВСЕМИ excluded (0 pending) теперь пропускает гейт → READY (раньше безусловный
> гейт мог кинуть `DictionaryNotReadyError` на пустом каталоге). Это починка (все-ORG смете каталог не нужен),
> но если существующий тест лочил старое поведение на 0-pending смете — он споткнётся здесь; поправь тест под
> новое (корректное) поведение.

> **Заметка реализатору (в тест ре-прогона):** спасённый фонд-хит без вектора на ре-триггере один раз
> переэмбедится (`fetch_unembedded_nodes` исключает только `excluded`, не `matched_fund`) — безвредно
> (`save_node_embedding` статус не трогает, CAS по `embedding_input`). Не считать «неожиданный» embed регрессом.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/app/api/deps.py backend/app/scripts/eval_matching.py backend/tests/test_estimate_matching_service.py backend/tests/fakes.py
git commit -m "feat(matching): стадия _apply_fund перед арбитром + условный гейт + выключатель + счётчик"
```

---

### Task 7: API — тумблер, админ-rebuild, `matched_fund` в DTO

**Files:**
- Modify: `backend/app/api/routes/estimates.py`, `backend/app/api/schemas.py`, `backend/app/api/deps.py`
- Test: `backend/tests/test_estimate_routes.py`

**Interfaces:**
- Consumes: `DecisionFundService` (Task 5).
- Produces: `PATCH /estimates/{id}/reference` (body `{is_reference: bool}`, authz владелец/админ); `POST /estimates/fund/rebuild` (authz админ); `matched_fund` сериализуется в строках детали.

- [ ] **Step 1: Падающие API-тесты**

```python
def test_toggle_reference_promotes_and_sets_flag() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    # смета с confirmed-строкой; тумблер ON → is_reference + промоушен
    client = _client(repo, storage, fund)
    eid = _seed_reviewed(repo)  # хелпер: смета с confirmed-строкой
    resp = client.patch(f"/api/estimates/{eid}/reference", json={"is_reference": True})
    assert resp.status_code == 200
    assert repo.is_reference(eid) is True and fund.entries  # запромоутилось

def test_rebuild_requires_admin() -> None:
    client = _client(repo, storage, fund, user=_user(role=Role.USER))
    assert client.post("/api/estimates/fund/rebuild").status_code == 403
```

- [ ] **Step 2: Прогон — RED** → FAIL.

- [ ] **Step 3: Реализация**

В `schemas.py`: DTO статуса строки уже строковый — убедиться, что `matched_fund` проходит (если есть Enum-валидация на `status`, расширить). Добавить `class ReferenceToggleIn(BaseModel): is_reference: bool`.

В `deps.py`: `get_decision_fund_service()` (строит `DecisionFundService(SqlAlchemyEstimateRepository(session), SqlAlchemyDecisionFundRepository(session))`).

В `routes/estimates.py`:

```python
@router.patch("/{estimate_id}/reference", status_code=status.HTTP_200_OK)
def toggle_reference(
    estimate_id: int,
    body: ReferenceToggleIn,
    user: User = Depends(get_current_user),
    fund_service: DecisionFundService = Depends(get_decision_fund_service),
    repository: EstimateRepository = Depends(get_estimate_repository),
) -> dict:
    est = repository.get(estimate_id, user.id or 0, is_admin=user.role == Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    if body.is_reference:
        promoted = fund_service.promote(estimate_id)  # 0 → is_reference не выставлен (см. Task 5)
        return {"is_reference": promoted > 0, "promoted": promoted}
    fund_service.unreference(estimate_id)
    return {"is_reference": False, "promoted": 0}


@router.post("/fund/rebuild", status_code=status.HTTP_202_ACCEPTED)
def rebuild_fund(
    user: User = Depends(require_admin),
    fund_service: DecisionFundService = Depends(get_decision_fund_service),
) -> dict:
    fund_service.rebuild()
    return {"status": "rebuilt"}
```

(`require_admin` — существующий гвард из `deps.py`.)

- [ ] **Step 4: Прогон** — `PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_routes.py -q` → PASS; `uv run ruff check .` → чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/estimates.py backend/app/api/schemas.py backend/app/api/deps.py backend/tests/test_estimate_routes.py
git commit -m "feat(api): тумблер is_reference (промоушен/снятие) + админ-rebuild фонда + matched_fund в DTO"
```

---

### Task 8: Фронт — статус «из фонда» + тумблер «в фонд»

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/lib/api/estimates.ts`, компонент строки результата и экран ревью/«готово» в `frontend/src/pages/estimate/`
- Test: vitest рядом с компонентами

**Interfaces:**
- Consumes: статус строки `matched_fund`; эндпоинты `PATCH /estimates/{id}/reference`, `POST /estimates/fund/rebuild`.

- [ ] **Step 1: Падающий vitest** — рендер строки со статусом `matched_fund` показывает бейдж «из фонда» (а не как needs_review/confident); тумблер «в фонд» вызывает `setReference(id, true)`.
- [ ] **Step 2: Прогон — RED** (`npm run test -- <file>`).
- [ ] **Step 3: Реализация:** в `types.ts` добавить `"matched_fund"` в `MatchStatus`; в `estimates.ts` — `setReference(id, value)` (PATCH) и `rebuildFund()` (POST); в таблице строк — ветка бейджа «из фонда» для `matched_fund`; на экране ревью/«готово» — переключатель «Эталонная смета / в фонд», дёргающий `setReference`. Бейдж — стиль соседних статусов (lucide-иконка).
- [ ] **Step 4: Прогон** — vitest PASS; `npm run typecheck` + `npm run lint` + `npx prettier --check <touched>` чисто.
- [ ] **Step 5: Commit** — `git commit -m "feat(front): статус «из фонда» + тумблер «в фонд» + rebuild"`.

---

### Task 9: Верификация сьюта (пост-замер — отдельно, платно)

**Files:** нет правок кода.

- [ ] **Step 1: Полный бэк-сьют** — `cd backend && PYTHONIOENCODING=utf-8 uv run pytest -q` → всё зелёное (фонд не сломал существующее; `eval_matching` гоняет `apply_fund=False`).
- [ ] **Step 2: ruff + фронт** — `cd backend && uv run ruff check .`; `cd frontend && npm run typecheck && npm run lint` → чисто.
- [ ] **Step 3: Миграция применена** — `cd backend && uv run alembic upgrade head` на рабочей БД.
- [ ] **Step 4 (ОТДЕЛЬНО, требует подтверждения человека — платно/живая БД):** пост-замер ценности фонда — НЕ через бенчмарк (held-out). На реальной смете: пометить эталонную (`reference`), повторно прогнать похожую → счётчик `matched_fund` в summary + парный прогон `apply_fund=False` vs `True` со счётом вызовов арбитра (реальная экономия LLM). Зафиксировать в devlog. **Контроллер запускает только после явного «го».**
- [ ] **Step 5: Commit** (devlog) — `git commit -m "docs(devlog): золотой фонд — верификация + пост-замер ценности"`.

---

## Self-Review

- **Покрытие спеки:** §3 домен → Task 1; §4.1 таблица/§4.2 флаг → Task 2; порт+SQL-репо (lookup живых, upsert source/votes) → Task 3; методы estimate-репо (§4.3 снимок, §5.2 кандидаты) → Task 4; §5.1 промоушен+предикат+анти-накрутка+§6 rebuild/un-reference → Task 5; §5.2 `_apply_fund`+§5.3 гейт+выключатель+§5.4 счётчик → Task 6; api тумблер/rebuild/DTO → Task 7; фронт-бейдж/тумблер → Task 8; §7 замер (held-out, парный прогон) → Task 9. Инвалидация §6: delete — JOIN живых (Task 3 тест); crumb_version-bump — Task 6 тест; un-reference+rebuild — Task 5 тест.
- **Плейсхолдеры:** код приведён в нагруженных шагах (домен, SQL, предикат, `_apply_fund`, все спец-мандатные локи Task 6: hit/conflict/disabled/crumb-bump — конкретны). Task 8 (фронт) — шаги прозой: точная разметка бейджа/тумблера зависит от структуры компонентов, которую реализатор читает на месте (паттерн соседних `*.test.tsx`); это осознанное масштабирование фронт-задачи, не скрытый TODO. Хелперы `_matching_service`/`_client`/`seed_*` — по образцу существующих `_classify_service`/`_client`.
- **Согласованность типов:** `normalize_cache_key`/`cache_key_hash`/`resolve_fund_decision`/`FundHit`/`FundEntry`/`CRUMB_DERIVATION_VERSION`/`DecisionFundRepository.lookup(key_hashes, crumb_version)`/`save_fund_hit(node_id, article_id, code, name)`/`DecisionFundService.promote/unreference/rebuild` — имена и сигнатуры совпадают во всех задачах.
- **Отложено (НЕ в плане, по спеке §8):** голоса/веса (D), acceptable-sets+метрика (E), негативные записи, авто-split/merge, bulk-seed.
