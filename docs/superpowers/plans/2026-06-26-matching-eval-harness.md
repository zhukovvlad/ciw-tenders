# Matching Eval Harness (Спека A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бенчмарк-хранилище gold-разметки в БД + оффлайн-скрипт, прогоняющий размеченную смету через реальный пайплайн матчинга и считающий метрики качества (классификация A/A′ + матчинг B).

**Architecture:** Две новые таблицы (`benchmark`, `benchmark_node`) хранят выверенную специалистом разметку. CLI-скрипт `benchmark_seed` засеивает их из xlsx (гейт подсказывает `expected_kind`, человек подтверждает `no_article`). CLI-скрипт `eval_matching` читает gold из БД, реконструирует транзиентную смету, гоняет реальный `EstimateMatchingService.match_estimate`, читает результаты обратно и печатает сводку + CSV. Чистые доменные функции (нормализация, классы, метрики) изолированы и покрыты юнит-тестами; сетевой прогон тестом не покрывается.

**Tech Stack:** Python 3.11+, SQLAlchemy + pgvector, Alembic (ручные ревизии), openpyxl, pytest. Управление — `uv`, рецепты — `justfile` (PowerShell 5.1).

## Global Constraints

- ruff line-length 100, target py311, type hints обязательны, `from __future__ import annotations` в каждом модуле.
- Clean Architecture: `api → services → domain ← infrastructure`. Доменный слой без импортов SQLAlchemy/SDK. Новая абстракция — только `BenchmarkRepository` в `domain/ports.py`.
- Бэкенд строго через `uv run` (не системный python/pip). Команды из `backend/`: `cd backend; uv run ...`.
- Кириллица в stdout: ставить `PYTHONIOENCODING=utf-8`.
- ORM-модели держать синхронными с Alembic-ревизиями. Новая ревизия — ручная (`op.execute`), как `0003`–`0005`; `expected_kind` хранится `VARCHAR` + `CHECK` (как `users.role`), НЕ PG-ENUM.
- Нормализация кода статьи — байт-в-байт как [template_parser.py:51-52](../../../backend/app/services/template_parser.py#L51): `re.sub(r"\s+","",code).strip(".")` и `re.sub(r"\s+"," ",name).strip()`.
- Юнит-тесты не ходят в реальную БД/AI (фейки портов + `dependency_overrides`); `eval_matching` — инструмент, тестом не покрывается.
- Gold-файл лежит в `temp/` (gitignore); путь — параметр CLI, не хардкод. Данные сметы в репозиторий не коммитятся.

---

### Task 1: Миграция + ORM-модели `benchmark` / `benchmark_node`

**Files:**
- Create: `backend/alembic/versions/0006_benchmark.py`
- Modify: `backend/app/infrastructure/db/models.py` (добавить две модели в конец файла)

**Interfaces:**
- Produces: таблицы `benchmark(id, name, created_at)`, `benchmark_node(id, benchmark_id, source_index, code, name, expected_kind, expected_article_code, expected_article_name)`; ORM-классы `BenchmarkModel`, `BenchmarkNodeModel`.

- [ ] **Step 1: Написать ручную Alembic-ревизию**

Создать `backend/alembic/versions/0006_benchmark.py`:

```python
"""benchmark + benchmark_node

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE benchmark (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE benchmark_node (
            id                     SERIAL PRIMARY KEY,
            benchmark_id           INTEGER NOT NULL REFERENCES benchmark (id) ON DELETE CASCADE,
            source_index           INTEGER NOT NULL,
            code                   VARCHAR(64) NOT NULL,
            name                   TEXT NOT NULL,
            expected_kind          VARCHAR(16) NOT NULL,
            expected_article_code  VARCHAR(64),
            expected_article_name  TEXT,
            CONSTRAINT benchmark_node_kind_check
                CHECK (expected_kind IN ('matchable', 'structural', 'no_article')),
            CONSTRAINT uq_benchmark_node_source
                UNIQUE (benchmark_id, source_index)
        )
        """
    )
    op.execute("CREATE INDEX idx_benchmark_node_benchmark_id ON benchmark_node (benchmark_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_node")
    op.execute("DROP TABLE IF EXISTS benchmark")
```

- [ ] **Step 2: Добавить ORM-модели**

В конец `backend/app/infrastructure/db/models.py` (импорты `CheckConstraint`, `UniqueConstraint`, `ForeignKey`, `Integer`, `String`, `Text`, `DateTime`, `func` уже есть):

```python
class BenchmarkModel(Base):
    __tablename__ = "benchmark"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BenchmarkNodeModel(Base):
    __tablename__ = "benchmark_node"
    __table_args__ = (
        CheckConstraint(
            "expected_kind IN ('matchable', 'structural', 'no_article')",
            name="benchmark_node_kind_check",
        ),
        UniqueConstraint("benchmark_id", "source_index", name="uq_benchmark_node_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("benchmark.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_index: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    expected_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_article_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_article_name: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 3: Применить миграцию**

Run: `cd backend; uv run alembic upgrade head`
Expected: `Running upgrade 0005 -> 0006, benchmark + benchmark_node` без ошибок.

- [ ] **Step 4: Проверить, что схема и ORM согласованы (autogen пустой)**

Run: `cd backend; uv run alembic revision --autogenerate -m "verify benchmark sync"`
Expected: в сгенерированном файле `upgrade()`/`downgrade()` — `pass` (нет расхождений ORM↔БД). **Удалить** этот проверочный файл после.

```bash
git add backend/alembic/versions/0006_benchmark.py backend/app/infrastructure/db/models.py
git commit -m "feat(benchmark): миграция и ORM benchmark/benchmark_node"
```

---

### Task 2: Доменные функции нормализации и классификации gold

**Files:**
- Create: `backend/app/domain/benchmark.py`
- Test: `backend/tests/test_benchmark_domain.py`

**Interfaces:**
- Consumes: `contains_org_token`, `has_work_word` из [classification.py](../../../backend/app/domain/classification.py).
- Produces:
  - `BenchmarkKind(StrEnum)` = `MATCHABLE`/`STRUCTURAL`/`NO_ARTICLE`.
  - `norm_code(raw: str) -> str` — `re.sub(r"\s+","",raw).strip(".")`.
  - `norm_name(raw: str) -> str` — `re.sub(r"\s+"," ", raw.replace("\xa0"," ")).strip().lower()`.
  - `parse_gold_cell(cell: str | None) -> tuple[str | None, str | None]` — `(code, name)` из `(code) Name`; `(None, None)` если пусто/мусор.
  - `suggest_kind(cell: str | None, node_name: str) -> BenchmarkKind`.

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/test_benchmark_domain.py`:

```python
from __future__ import annotations

from app.domain.benchmark import (
    BenchmarkKind,
    norm_code,
    norm_name,
    parse_gold_cell,
    suggest_kind,
)


def test_norm_code_strips_parens_spaces_dots():
    assert norm_code("6.3.1") == "6.3.1"
    assert norm_code(" 6. 3 .1. ") == "6.3.1"


def test_norm_name_lowercases_and_collapses_ws():
    assert norm_name("  Отделка\xa0 кровли ") == "отделка кровли"


def test_parse_gold_cell_extracts_code_and_name():
    assert parse_gold_cell("(6.3.1) Устройство подсистемы фасада") == (
        "6.3.1",
        "Устройство подсистемы фасада",
    )


def test_parse_gold_cell_empty_and_garbage_return_none():
    assert parse_gold_cell(None) == (None, None)
    assert parse_gold_cell("   ") == (None, None)
    assert parse_gold_cell("без скобок") == (None, None)


def test_suggest_kind_matchable_when_cell_present():
    assert suggest_kind("(1.2) Мобилизация", "Мобилизация") is BenchmarkKind.MATCHABLE


def test_suggest_kind_structural_when_empty_and_org_token():
    assert suggest_kind(None, "1 Этап ЖК") is BenchmarkKind.STRUCTURAL
    assert suggest_kind(None, "Корпус № 2; 3; 4") is BenchmarkKind.STRUCTURAL


def test_suggest_kind_no_article_when_empty_work_head_no_org():
    assert suggest_kind(None, "Инженерные системы") is BenchmarkKind.NO_ARTICLE
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend; uv run pytest tests/test_benchmark_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.benchmark'`.

- [ ] **Step 3: Реализовать доменный модуль**

Создать `backend/app/domain/benchmark.py`:

```python
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
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_benchmark_domain.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/benchmark.py backend/tests/test_benchmark_domain.py
git commit -m "feat(benchmark): доменные функции нормализации и подсказки класса"
```

---

### Task 3: Доменный расчёт метрик (A / A′ / B)

**Files:**
- Modify: `backend/app/domain/benchmark.py` (добавить датаклассы и `compute_metrics`)
- Test: `backend/tests/test_benchmark_metrics.py`

**Interfaces:**
- Produces:
  - `NodeOutcome` (вход на узел): `expected_kind: BenchmarkKind`, `expected_code: str | None`, `kept: bool`, `status: str`, `matched_code: str | None`, `top3_codes: list[str]`, `catalog_has_code: bool`, `catalog_name_norm: str | None`.
  - `EvalReport` (агрегат): поля групп A/A′/B (см. ниже).
  - `compute_metrics(outcomes: list[NodeOutcome], *, confident_statuses=("confident",)) -> EvalReport`.
  - `node_flags(o: NodeOutcome) -> dict` — производные флаги строки CSV (`bucket`, `article_renamed`, `top1_hit`, `top3_hit`).

- [ ] **Step 1: Написать падающие тесты**

Создать `backend/tests/test_benchmark_metrics.py`:

```python
from __future__ import annotations

from app.domain.benchmark import BenchmarkKind, NodeOutcome, compute_metrics


def _m(**kw) -> NodeOutcome:
    base = dict(
        expected_kind=BenchmarkKind.MATCHABLE,
        expected_code="1.1",
        kept=True,
        status="confident",
        matched_code="1.1",
        top3_codes=["1.1", "1.2", "1.3"],
        catalog_has_code=True,
        catalog_name_norm=None,
    )
    base.update(kw)
    return NodeOutcome(**base)


def test_group_a_matrix_counts_structural_and_matchable_only():
    outcomes = [
        _m(expected_kind=BenchmarkKind.STRUCTURAL, expected_code=None, kept=False, status="excluded"),
        _m(expected_kind=BenchmarkKind.STRUCTURAL, expected_code=None, kept=True, status="no_match"),
        _m(kept=False, status="excluded"),  # matchable, исключён → FN
        _m(),                               # matchable, оставлен → TP
        _m(expected_kind=BenchmarkKind.NO_ARTICLE, expected_code=None, kept=True, status="no_match"),
    ]
    r = compute_metrics(outcomes)
    assert (r.a_tn, r.a_fp, r.a_fn, r.a_tp) == (1, 1, 1, 1)  # no_article НЕ в матрице


def test_group_a_prime_no_article_split():
    outcomes = [
        _m(expected_kind=BenchmarkKind.NO_ARTICLE, expected_code=None, kept=True, status="no_match"),
        _m(expected_kind=BenchmarkKind.NO_ARTICLE, expected_code=None, kept=True,
           status="confident", matched_code="9.9"),
    ]
    r = compute_metrics(outcomes)
    assert r.no_article_total == 2
    assert r.no_article_correct_no_match == 1
    assert r.no_article_wrong_confident == 1


def test_group_b_top1_top3_only_matchable_kept():
    outcomes = [
        _m(matched_code="1.1", top3_codes=["1.1", "2.2"]),          # top1 hit, top3 hit
        _m(matched_code="9.9", top3_codes=["1.1", "9.9", "3.3"]),   # top1 miss, top3 hit
        _m(matched_code="9.9", top3_codes=["8.8", "9.9", "3.3"]),   # top1 miss, top3 miss
    ]
    r = compute_metrics(outcomes)
    assert r.b_total == 3
    assert r.b_top1_hits == 1
    assert r.b_top3_hits == 2


def test_gold_not_in_catalog_excluded_from_b_denominator():
    outcomes = [
        _m(expected_code="X.Y", catalog_has_code=False, matched_code=None, top3_codes=[]),
        _m(matched_code="1.1", top3_codes=["1.1"]),
    ]
    r = compute_metrics(outcomes)
    assert r.gold_not_in_catalog == 1
    assert r.b_total == 1  # узел с отсутствующим кодом не в знаменателе B


def test_article_renamed_flagged_when_catalog_name_differs():
    o = _m(catalog_name_norm="другое имя")  # снимок отличается → renamed
    r = compute_metrics([o])
    assert r.article_renamed == 1
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend; uv run pytest tests/test_benchmark_metrics.py -v`
Expected: FAIL — `ImportError: cannot import name 'NodeOutcome'`.

- [ ] **Step 3: Реализовать датаклассы и расчёт**

Сперва дополнить блок импортов **в начале** `backend/app/domain/benchmark.py` (рядом с `import re`):

```python
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum  # уже есть — не дублировать
```

Затем добавить в конец `backend/app/domain/benchmark.py`:

```python
@dataclass(frozen=True, slots=True)
class NodeOutcome:
    expected_kind: BenchmarkKind
    expected_code: str | None
    kept: bool
    status: str
    matched_code: str | None
    top3_codes: list[str] = field(default_factory=list)
    catalog_has_code: bool = True
    catalog_name_norm: str | None = None  # текущее имя статьи (norm) или None, если совпадает/нет кода


@dataclass(frozen=True, slots=True)
class EvalReport:
    # Группа A (только structural+matchable)
    a_tn: int
    a_fp: int
    a_fn: int
    a_tp: int
    # Группа A′ (no_article)
    no_article_total: int
    no_article_correct_no_match: int
    no_article_wrong_confident: int
    # Группа B (только matchable, kept, код есть в каталоге)
    b_total: int
    b_top1_hits: int
    b_top3_hits: int
    # Дрейф каталога
    gold_not_in_catalog: int
    article_renamed: int


def _is_renamed(o: NodeOutcome) -> bool:
    return (
        o.expected_kind is BenchmarkKind.MATCHABLE
        and o.catalog_has_code
        and o.catalog_name_norm is not None
    )


def compute_metrics(
    outcomes: Sequence[NodeOutcome], *, confident_statuses: tuple[str, ...] = ("confident",)
) -> EvalReport:
    a_tn = a_fp = a_fn = a_tp = 0
    na_total = na_ok = na_wrong = 0
    b_total = b_top1 = b_top3 = 0
    not_in_cat = renamed = 0

    for o in outcomes:
        if o.expected_kind is BenchmarkKind.STRUCTURAL:
            if o.kept:
                a_fp += 1
            else:
                a_tn += 1
        elif o.expected_kind is BenchmarkKind.MATCHABLE:
            if o.kept:
                a_tp += 1
            else:
                a_fn += 1
            if _is_renamed(o):
                renamed += 1
            if not o.catalog_has_code:
                not_in_cat += 1
            elif o.kept:
                b_total += 1
                if o.matched_code == o.expected_code:
                    b_top1 += 1
                if o.expected_code in o.top3_codes:
                    b_top3 += 1
        elif o.expected_kind is BenchmarkKind.NO_ARTICLE:
            na_total += 1
            if o.status == "no_match":
                na_ok += 1
            elif o.status in confident_statuses:
                na_wrong += 1

    return EvalReport(
        a_tn=a_tn, a_fp=a_fp, a_fn=a_fn, a_tp=a_tp,
        no_article_total=na_total,
        no_article_correct_no_match=na_ok,
        no_article_wrong_confident=na_wrong,
        b_total=b_total, b_top1_hits=b_top1, b_top3_hits=b_top3,
        gold_not_in_catalog=not_in_cat, article_renamed=renamed,
    )
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_benchmark_metrics.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/benchmark.py backend/tests/test_benchmark_metrics.py
git commit -m "feat(benchmark): расчёт метрик A/A'/B + детектор дрейфа"
```

---

### Task 4: Сущности, порт и репозиторий бенчмарка

**Files:**
- Modify: `backend/app/domain/entities.py` (датакласс `BenchmarkNodeSeed`)
- Modify: `backend/app/domain/ports.py` (порт `BenchmarkRepository`)
- Create: `backend/app/infrastructure/db/benchmark_repository.py`
- Test: `backend/tests/test_benchmark_repository.py`

**Interfaces:**
- Produces:
  - `BenchmarkNodeSeed(code, name, source_index, expected_kind: str, expected_article_code: str | None, expected_article_name: str | None)`.
  - `BenchmarkRepository.create(name: str, nodes: list[BenchmarkNodeSeed]) -> int` (benchmark_id).
  - `BenchmarkRepository.get_by_name(name) -> int | None`.
  - `BenchmarkRepository.list_benchmarks() -> list[tuple[int, str]]`.
  - `BenchmarkRepository.fetch_nodes(benchmark_id) -> list[BenchmarkNodeSeed]` (по возрастанию `source_index`).
  - `SqlAlchemyBenchmarkRepository(session)`.

- [ ] **Step 1: Добавить сущность и порт**

В `backend/app/domain/entities.py` (после `NodeToClassify`):

```python
@dataclass(frozen=True, slots=True)
class BenchmarkNodeSeed:
    """Узел бенчмарка: разметка специалиста относительно версии справочника."""

    code: str
    name: str
    source_index: int
    expected_kind: str  # значение BenchmarkKind
    expected_article_code: str | None
    expected_article_name: str | None
```

В `backend/app/domain/ports.py` добавить `BenchmarkNodeSeed` в импорт из `entities` и в конец файла:

```python
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
```

- [ ] **Step 2: Написать падающий тест репозитория**

Создать `backend/tests/test_benchmark_repository.py` (реальная БД недоступна юнит-тестам → тестируем чистый маппинг seed↔ORM через фейк-сессию памяти не выйдет; вместо этого проверяем сборку моделей функцией-хелпером маппинга):

```python
from __future__ import annotations

from app.domain.entities import BenchmarkNodeSeed
from app.infrastructure.db.benchmark_repository import _seed_to_model, _model_to_seed
from app.infrastructure.db.models import BenchmarkNodeModel


def test_seed_to_model_maps_all_fields():
    seed = BenchmarkNodeSeed(
        code="6.3.1", name="Подсистема", source_index=42,
        expected_kind="matchable", expected_article_code="6.3.1",
        expected_article_name="Устройство подсистемы фасада",
    )
    m = _seed_to_model(seed, benchmark_id=7)
    assert m.benchmark_id == 7
    assert m.code == "6.3.1"
    assert m.source_index == 42
    assert m.expected_kind == "matchable"
    assert m.expected_article_code == "6.3.1"
    assert m.expected_article_name == "Устройство подсистемы фасада"


def test_model_to_seed_roundtrip():
    m = BenchmarkNodeModel(
        benchmark_id=1, source_index=3, code="10", name="Инженерные системы",
        expected_kind="no_article", expected_article_code=None,
        expected_article_name=None,
    )
    seed = _model_to_seed(m)
    assert seed.code == "10"
    assert seed.expected_kind == "no_article"
    assert seed.expected_article_code is None
```

- [ ] **Step 3: Запустить — убедиться, что падают**

Run: `cd backend; uv run pytest tests/test_benchmark_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.db.benchmark_repository'`.

- [ ] **Step 4: Реализовать репозиторий**

Создать `backend/app/infrastructure/db/benchmark_repository.py`:

```python
"""SqlAlchemy-репозиторий бенчмарков (gold-разметка). Маппинг seed↔ORM локализован тут."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import BenchmarkNodeSeed
from app.domain.ports import BenchmarkRepository
from app.infrastructure.db.models import BenchmarkModel, BenchmarkNodeModel


def _seed_to_model(seed: BenchmarkNodeSeed, benchmark_id: int) -> BenchmarkNodeModel:
    return BenchmarkNodeModel(
        benchmark_id=benchmark_id,
        source_index=seed.source_index,
        code=seed.code,
        name=seed.name,
        expected_kind=seed.expected_kind,
        expected_article_code=seed.expected_article_code,
        expected_article_name=seed.expected_article_name,
    )


def _model_to_seed(m: BenchmarkNodeModel) -> BenchmarkNodeSeed:
    return BenchmarkNodeSeed(
        code=m.code,
        name=m.name,
        source_index=m.source_index,
        expected_kind=m.expected_kind,
        expected_article_code=m.expected_article_code,
        expected_article_name=m.expected_article_name,
    )


class SqlAlchemyBenchmarkRepository(BenchmarkRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, nodes: list[BenchmarkNodeSeed]) -> int:
        try:
            bench = BenchmarkModel(name=name)
            self._session.add(bench)
            self._session.flush()  # bench.id
            self._session.add_all([_seed_to_model(n, bench.id) for n in nodes])
            self._session.commit()
            return bench.id
        except Exception:
            self._session.rollback()
            raise

    def get_by_name(self, name: str) -> int | None:
        return self._session.execute(
            select(BenchmarkModel.id).where(BenchmarkModel.name == name)
        ).scalar_one_or_none()

    def list_benchmarks(self) -> list[tuple[int, str]]:
        rows = self._session.execute(
            select(BenchmarkModel.id, BenchmarkModel.name).order_by(BenchmarkModel.id)
        ).all()
        return [(r[0], r[1]) for r in rows]

    def fetch_nodes(self, benchmark_id: int) -> list[BenchmarkNodeSeed]:
        rows = self._session.execute(
            select(BenchmarkNodeModel)
            .where(BenchmarkNodeModel.benchmark_id == benchmark_id)
            .order_by(BenchmarkNodeModel.source_index)
        ).scalars().all()
        return [_model_to_seed(m) for m in rows]
```

- [ ] **Step 5: Запустить — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_benchmark_repository.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py \
        backend/app/infrastructure/db/benchmark_repository.py \
        backend/tests/test_benchmark_repository.py
git commit -m "feat(benchmark): сущность, порт и SqlAlchemy-репозиторий бенчмарка"
```

---

### Task 5: Чтение xlsx и сид-скрипт `benchmark_seed`

**Files:**
- Create: `backend/app/infrastructure/benchmark_xlsx.py` (чистое чтение xlsx → seed-узлы)
- Create: `backend/app/scripts/benchmark_seed.py`
- Modify: `justfile` (рецепт `benchmark-seed`)
- Test: `backend/tests/test_benchmark_xlsx.py`

**Interfaces:**
- Consumes: `parse_gold_cell`, `suggest_kind`, `norm_code`, `BenchmarkKind` (Task 2); `BenchmarkNodeSeed` (Task 4); `BenchmarkRepository` (Task 4).
- Produces: `read_benchmark_nodes(path: str) -> list[BenchmarkNodeSeed]` (все строки-узлы, `expected_kind` по гейту); `backend/app/scripts/benchmark_seed.py::main`.

Колонки xlsx (0-based): `0` «№ раздела», `1` «Статья СМР», `2` «Наименование раздела / позиции». Строка-узел: «№ раздела» непуст и все сегменты кода — цифры.

- [ ] **Step 1: Написать падающий тест чтения xlsx**

Создать `backend/tests/test_benchmark_xlsx.py` (генерируем временный xlsx openpyxl, без чтения реальной сметы):

```python
from __future__ import annotations

import openpyxl

from app.domain.benchmark import BenchmarkKind
from app.infrastructure.benchmark_xlsx import read_benchmark_nodes


def _make_xlsx(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№ раздела", "Статья СМР", "Наименование раздела / позиции"])
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_read_nodes_assigns_kinds(tmp_path):
    p = tmp_path / "gold.xlsx"
    _make_xlsx(p, [
        ["1", "(1) Подготовительные работы", "Подготовительные работы"],  # matchable
        ["1.1", None, "1 Этап ЖК"],                                       # structural
        ["10", None, "Инженерные системы"],                               # no_article
        [None, None, "листовая позиция"],                                 # пропуск (не узел)
    ])
    nodes = read_benchmark_nodes(str(p))
    by_code = {n.code: n for n in nodes}
    assert set(by_code) == {"1", "1.1", "10"}
    assert by_code["1"].expected_kind == BenchmarkKind.MATCHABLE.value
    assert by_code["1"].expected_article_code == "1"
    assert by_code["1.1"].expected_kind == BenchmarkKind.STRUCTURAL.value
    assert by_code["10"].expected_kind == BenchmarkKind.NO_ARTICLE.value
    assert nodes[0].source_index < nodes[1].source_index  # порядок сохранён
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_benchmark_xlsx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.benchmark_xlsx'`.

- [ ] **Step 3: Реализовать чтение xlsx**

Создать `backend/app/infrastructure/benchmark_xlsx.py`:

```python
"""Чтение размеченной сметы (xlsx) в seed-узлы бенчмарка. Только для CLI-сида."""

from __future__ import annotations

import re

import openpyxl

from app.domain.benchmark import BenchmarkKind, parse_gold_cell, suggest_kind
from app.domain.entities import BenchmarkNodeSeed

_SECTION_NO_COL = 0   # «№ раздела»
_ARTICLE_COL = 1      # «Статья СМР»
_NAME_COL = 2         # «Наименование раздела / позиции»


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def _is_node_code(raw: object) -> str | None:
    if raw is None:
        return None
    code = re.sub(r"\s+", "", str(raw)).strip(".")
    if not code or not all(seg.isdigit() for seg in code.split(".")):
        return None
    return code


def read_benchmark_nodes(path: str) -> list[BenchmarkNodeSeed]:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    nodes: list[BenchmarkNodeSeed] = []
    for source_index, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        cells = list(row) + [None] * 3
        code = _is_node_code(cells[_SECTION_NO_COL])
        if code is None:
            continue
        name = _clean(cells[_NAME_COL])
        if not name or name.lower() == "nan":
            continue
        cell = cells[_ARTICLE_COL]
        kind = suggest_kind(cell, name)
        art_code, art_name = parse_gold_cell(cell)
        nodes.append(
            BenchmarkNodeSeed(
                code=code,
                name=name,
                source_index=source_index,
                expected_kind=kind.value,
                expected_article_code=art_code if kind is BenchmarkKind.MATCHABLE else None,
                expected_article_name=art_name if kind is BenchmarkKind.MATCHABLE else None,
            )
        )
    return nodes
```

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd backend; uv run pytest tests/test_benchmark_xlsx.py -v`
Expected: PASS.

- [ ] **Step 5: Реализовать сид-скрипт с подтверждением `no_article`**

Создать `backend/app/scripts/benchmark_seed.py`:

```python
"""Сид бенчмарка из размеченной сметы (xlsx → БД). Разовая админ-операция.

Запуск: uv run python -m app.scripts.benchmark_seed --gold "<path>" [--name <name>] [--yes]
`no_article`-узлы печатаются громко и требуют подтверждения (или флаг --yes).
"""

from __future__ import annotations

import argparse
import os

from app.domain.benchmark import BenchmarkKind
from app.infrastructure.benchmark_xlsx import read_benchmark_nodes
from app.infrastructure.db.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.infrastructure.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True, help="путь к размеченному xlsx")
    parser.add_argument("--name", default=None, help="имя бенчмарка (по умолчанию — basename)")
    parser.add_argument("--yes", action="store_true", help="не спрашивать подтверждение no_article")
    args = parser.parse_args()

    nodes = read_benchmark_nodes(args.gold)
    name = args.name or os.path.splitext(os.path.basename(args.gold))[0]

    kinds = {k: 0 for k in (BenchmarkKind.MATCHABLE, BenchmarkKind.STRUCTURAL, BenchmarkKind.NO_ARTICLE)}
    for n in nodes:
        kinds[BenchmarkKind(n.expected_kind)] += 1
    print(f"Узлов: {len(nodes)} | matchable={kinds[BenchmarkKind.MATCHABLE]} "
          f"structural={kinds[BenchmarkKind.STRUCTURAL]} no_article={kinds[BenchmarkKind.NO_ARTICLE]}")

    no_art = [n for n in nodes if n.expected_kind == BenchmarkKind.NO_ARTICLE.value]
    if no_art:
        print("\n=== ПОДТВЕРДИТЕ no_article (работа без статьи в справочнике): ===")
        for n in no_art:
            print(f"  {n.code} | {n.name}")
        if not args.yes:
            answer = input("\nВсе перечисленные узлы действительно без статьи? [y/N]: ").strip().lower()
            if answer != "y":
                raise SystemExit("Отменено. Поправьте разметку в xlsx и повторите.")

    session = SessionLocal()
    try:
        repo = SqlAlchemyBenchmarkRepository(session)
        if repo.get_by_name(name) is not None:
            raise SystemExit(f"Бенчмарк '{name}' уже существует. Удалите его или задайте --name.")
        benchmark_id = repo.create(name, nodes)
        print(f"\nСоздан бенчмарк '{name}' (id={benchmark_id}), узлов: {len(nodes)}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Добавить рецепт в justfile**

После рецепта `create-admin` в `justfile`:

```just
# Засеять бенчмарк gold-разметки из размеченного xlsx: just benchmark-seed gold="temp/..."
benchmark-seed gold name="":
    cd {{backend}}; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.benchmark_seed --gold "{{gold}}" $(if ("{{name}}") {"--name"; "{{name}}"})
```

- [ ] **Step 7: Прогнать сид на реальном gold-файле**

Run: `just benchmark-seed gold="temp/Смета - образец размеченная до конца.xlsx"`
Expected: печать `Узлов: 809 | matchable=783 structural=25 no_article=1`, список `no_article` = `10 | Инженерные системы`, запрос подтверждения; после `y` — `Создан бенчмарк ... узлов: 809`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/benchmark_xlsx.py backend/app/scripts/benchmark_seed.py \
        backend/tests/test_benchmark_xlsx.py justfile
git commit -m "feat(benchmark): чтение xlsx + CLI-сид benchmark-seed"
```

---

### Task 6: Реконструкция сметы из бенчмарка (с паритетом парсера)

**Files:**
- Create: `backend/app/services/benchmark_reconstruct.py`
- Test: `backend/tests/test_benchmark_reconstruct.py`

**Interfaces:**
- Consumes: `BenchmarkNodeSeed` (Task 4); `EstimateNode`, `ParsedEstimate` ([entities.py](../../../backend/app/domain/entities.py)); `EstimateParser` ([estimate_parser.py](../../../backend/app/services/estimate_parser.py)) — для теста паритета.
- Produces: `reconstruct_nodes(seeds: list[BenchmarkNodeSeed]) -> list[EstimateNode]`. `parent_code` = `".".join(segments[:-1]) or None`; `depth` = число сегментов; `section_type=None`; `embedding_input` = плейсхолдер (имя) — пайплайн пересоберёт крошку на классификации.

**Инвариант 2.1:** для одного входа `reconstruct_nodes` даёт тот же набор `code` (и ту же сегментную иерархию `parent_code`/`depth`), что и `EstimateParser`. Крошку строит сам пайплайн из `(code, name)` — поэтому совпадение `code`/имён достаточно.

- [ ] **Step 1: Написать падающий тест паритета с парсером**

Создать `backend/tests/test_benchmark_reconstruct.py`:

```python
from __future__ import annotations

import io

import openpyxl

from app.domain.entities import BenchmarkNodeSeed
from app.services.benchmark_reconstruct import reconstruct_nodes
from app.services.estimate_parser import EstimateParser


def _xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["№ раздела", "Наименование раздела / позиции", "Вид раздела"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reconstruct_matches_parser_codes_and_hierarchy():
    rows = [
        ["1", "Подготовительные работы", "СМР"],
        ["1.1", "Мобилизация", None],
        ["1.1.1", "Снос", None],
    ]
    parsed = EstimateParser().parse(_xlsx_bytes(rows))
    seeds = [
        BenchmarkNodeSeed(code=n.code, name=n.name, source_index=n.source_index,
                          expected_kind="matchable", expected_article_code=None,
                          expected_article_name=None)
        for n in parsed.nodes
    ]
    recon = reconstruct_nodes(seeds)
    assert [n.code for n in recon] == [n.code for n in parsed.nodes]
    assert [n.parent_code for n in recon] == [n.parent_code for n in parsed.nodes]
    assert [n.depth for n in recon] == [n.depth for n in parsed.nodes]


def test_reconstruct_parent_and_depth_from_code():
    seeds = [
        BenchmarkNodeSeed("4.1.2", "Ж/Б конструкции", 5, "matchable", None, None),
    ]
    node = reconstruct_nodes(seeds)[0]
    assert node.parent_code == "4.1"
    assert node.depth == 3
    assert node.embedding_input  # непустой плейсхолдер
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd backend; uv run pytest tests/test_benchmark_reconstruct.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.benchmark_reconstruct'`.

- [ ] **Step 3: Реализовать реконструкцию**

Создать `backend/app/services/benchmark_reconstruct.py`:

```python
"""Реконструкция узлов сметы из seed-узлов бенчмарка для прогона через пайплайн.

Инвариант: тот же code/parent_code/depth, что у EstimateParser. Крошку (embedding_input)
пересобирает сам пайплайн на шаге классификации, поэтому здесь — плейсхолдер.
"""

from __future__ import annotations

from app.domain.entities import BenchmarkNodeSeed, EstimateNode


def reconstruct_nodes(seeds: list[BenchmarkNodeSeed]) -> list[EstimateNode]:
    nodes: list[EstimateNode] = []
    for seed in seeds:
        segments = seed.code.split(".")
        parent_code = ".".join(segments[:-1]) or None
        nodes.append(
            EstimateNode(
                code=seed.code,
                name=seed.name,
                parent_code=parent_code,
                section_type=None,  # в матчинге не используется (org-filter спека)
                embedding_input=seed.name,  # плейсхолдер; пайплайн пересоберёт крошку
                source_index=seed.source_index,
                depth=len(segments),
            )
        )
    return nodes
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_benchmark_reconstruct.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/benchmark_reconstruct.py backend/tests/test_benchmark_reconstruct.py
git commit -m "feat(benchmark): реконструкция узлов сметы с паритетом парсера"
```

---

### Task 7: Харнесс `eval_matching` (прогон + сводка + CSV)

**Files:**
- Create: `backend/app/scripts/eval_matching.py`
- Modify: `justfile` (рецепт `eval-matching`)

**Interfaces:**
- Consumes: `SqlAlchemyBenchmarkRepository.fetch_nodes`/`list_benchmarks` (Task 4); `reconstruct_nodes` (Task 6); `compute_metrics`, `NodeOutcome`, `BenchmarkKind`, `norm_name` (Task 2–3); `build_estimate_matching_service` ([deps.py:175](../../../backend/app/api/deps.py#L175)); `SqlAlchemyEstimateRepository`, `SqlAlchemyArticleRepository`; `NewEstimate` ([entities.py](../../../backend/app/domain/entities.py)); `UserModel` ([models.py](../../../backend/app/infrastructure/db/models.py)).
- Produces: `backend/app/scripts/eval_matching.py::main`.

Логика прогона: fail-fast (справочник проэмбежен) → собрать узлы из бенчмарка → реконструировать → `repo.create` транзиентной сметы (любой существующий user_id) → `match_estimate` → `estimates.get(...)` читает строки обратно → собрать `NodeOutcome` на узел (`status`, `matched_code`, `top3` из `candidates`, `catalog_has_code` через `articles.get_by_code`, `catalog_name_norm` если имя != снимок) → `compute_metrics` → печать сводки + CSV → удалить смету (`finally`, если не `--keep`).

- [ ] **Step 1: Реализовать харнесс**

Создать `backend/app/scripts/eval_matching.py`:

```python
"""Оффлайн-метрика матчинга: прогон бенчмарка через реальный пайплайн.

Запуск: uv run python -m app.scripts.eval_matching [--benchmark <name>] [--report <csv>] [--keep]
Требует проэмбеженный справочник и валидный backend/.env.
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile

from app.api.deps import build_estimate_matching_service
from app.domain.benchmark import BenchmarkKind, NodeOutcome, compute_metrics, norm_name
from app.domain.entities import NewEstimate
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import SessionLocal
from app.services.benchmark_reconstruct import reconstruct_nodes


def _pick_benchmark(repo: SqlAlchemyBenchmarkRepository, name: str | None) -> int:
    items = repo.list_benchmarks()
    if not items:
        raise SystemExit("Нет бенчмарков. Сначала: just benchmark-seed gold=\"...\"")
    if name is not None:
        bid = repo.get_by_name(name)
        if bid is None:
            raise SystemExit(f"Бенчмарк '{name}' не найден. Есть: {[n for _, n in items]}")
        return bid
    if len(items) > 1:
        raise SystemExit(f"Бенчмарков несколько, укажите --benchmark: {[n for _, n in items]}")
    return items[0][0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", default=None)
    parser.add_argument("--report", default=os.path.join(tempfile.gettempdir(), "eval_matching.csv"))
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        articles = SqlAlchemyArticleRepository(session)
        total, pending = articles.matching_readiness()
        if total == 0 or pending > 0:
            raise SystemExit(
                f"Справочник не готов (total={total}, pending={pending}). "
                f"Загрузите шаблон и прогоните эмбеддинг-воркер."
            )

        bench_repo = SqlAlchemyBenchmarkRepository(session)
        benchmark_id = _pick_benchmark(bench_repo, args.benchmark)
        seeds = bench_repo.fetch_nodes(benchmark_id)

        user_id = session.query(UserModel.id).order_by(UserModel.id).limit(1).scalar()
        if user_id is None:
            raise SystemExit("Нет пользователей. Сначала: just create-admin")

        estimates = SqlAlchemyEstimateRepository(session)
        nodes = reconstruct_nodes(seeds)
        estimate = estimates.create(
            NewEstimate(user_id=user_id, filename="__benchmark_eval__", original_object_key="eval"),
            nodes,
        )
        try:
            build_estimate_matching_service(session).match_estimate(estimate.id)
            stored = estimates.get(estimate.id, user_id, is_admin=True)
            _report(seeds, stored, articles, args.report)
        finally:
            if not args.keep:
                estimates.delete(estimate.id, user_id, is_admin=True)
    finally:
        session.close()


def _report(seeds, stored, articles, report_path) -> None:
    seed_by_code = {s.code: s for s in seeds}
    outcomes: list[NodeOutcome] = []
    rows_csv: list[dict] = []
    for row in stored.rows:
        seed = seed_by_code.get(row.code)
        if seed is None:
            continue
        kind = BenchmarkKind(seed.expected_kind)
        top3 = [c.code for c in row.candidates]
        catalog_has = catalog_name_norm = None
        if kind is BenchmarkKind.MATCHABLE and seed.expected_article_code:
            art = articles.get_by_code(seed.expected_article_code)
            catalog_has = art is not None
            if art is not None and seed.expected_article_name is not None:
                if norm_name(art.name) != norm_name(seed.expected_article_name):
                    catalog_name_norm = norm_name(art.name)
        outcomes.append(
            NodeOutcome(
                expected_kind=kind,
                expected_code=seed.expected_article_code,
                kept=row.status != "excluded",
                status=row.status,
                matched_code=row.matched_code,
                top3_codes=top3,
                catalog_has_code=bool(catalog_has) if catalog_has is not None else True,
                catalog_name_norm=catalog_name_norm,
            )
        )
        rows_csv.append({
            "code": row.code, "name": row.name, "expected_kind": seed.expected_kind,
            "gold_code": seed.expected_article_code or "", "gold_name": seed.expected_article_name or "",
            "kept": row.status != "excluded", "status": row.status,
            "chosen_code": row.matched_code or "", "top3_codes": "|".join(top3),
            "top1_hit": row.matched_code == seed.expected_article_code,
            "top3_hit": (seed.expected_article_code in top3) if seed.expected_article_code else "",
            "article_renamed": catalog_name_norm is not None,
        })

    r = compute_metrics(outcomes)
    print("\n=== Группа A (классификация) ===")
    print(f"TN={r.a_tn}  FP={r.a_fp}  FN={r.a_fn} (молчаливый пропуск работы!)  TP={r.a_tp}")
    print("\n=== Группа A' (no_article) ===")
    print(f"всего={r.no_article_total}  → no_match={r.no_article_correct_no_match}  "
          f"ошибочный уверенный матч={r.no_article_wrong_confident}")
    print("\n=== Группа B (матчинг, matchable) ===")
    denom = r.b_total or 1
    print(f"узлов={r.b_total}  top-1={r.b_top1_hits} ({100*r.b_top1_hits/denom:.1f}%)  "
          f"top-3 retrieval={r.b_top3_hits} ({100*r.b_top3_hits/denom:.1f}%)")
    print(f"\nдрейф: gold_not_in_catalog={r.gold_not_in_catalog}  article_renamed={r.article_renamed}")

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
        writer.writeheader()
        writer.writerows(rows_csv)
    print(f"\nCSV-детализация: {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Добавить рецепт в justfile**

После рецепта `benchmark-seed`:

```just
# Оффлайн-метрика матчинга по бенчмарку: just eval-matching [benchmark="<name>"]
eval-matching benchmark="":
    cd {{backend}}; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.eval_matching $(if ("{{benchmark}}") {"--benchmark"; "{{benchmark}}"})
```

- [ ] **Step 3: Прогнать харнесс (нужен проэмбеженный справочник)**

Run: `just eval-matching`
Expected: печать трёх групп метрик (A/A′/B) с числами и путём к CSV. При непроэмбеженном справочнике — понятный фейл-фаст «Справочник не готов».

- [ ] **Step 4: Линт всего нового кода**

Run: `cd backend; uv run ruff check .`
Expected: без ошибок.

- [ ] **Step 5: Полный прогон тестов**

Run: `cd backend; uv run pytest -q`
Expected: все новые тесты зелёные, существующие не сломаны.

- [ ] **Step 6: Commit**

```bash
git add backend/app/scripts/eval_matching.py justfile
git commit -m "feat(benchmark): харнесс eval-matching — прогон, сводка A/A'/B, CSV"
```

---

## Замечания по интеграции

- **`build_estimate_matching_service`** уже собирает реальные адаптеры из `get_settings()` + сессия — харнесс не дублирует wiring.
- **Реюз продового пути:** `match_estimate` сам делает classify → rebuild crumb → embed → gate → match. Реконструкция даёт только `(code, name)`; крошку и классификацию выполняет пайплайн ⇒ достоверность.
- **Cleanup:** транзиентная смета удаляется каскадом (`estimate_rows` через `ON DELETE CASCADE`) в `finally`, кроме `--keep`.
- **Стоимость:** один прогон = эмбеддинг ~760 узлов (matchable+structural остаются до excluded) + арбитр на ветке `needs_review`. Разово и умеренно.
- **Недетерминизм:** top-1 (арбитр) и FP/FN с оргтокеном (классификатор смеси) плавают между прогонами; top-3 retrieval и лексические ячейки стабильны.
