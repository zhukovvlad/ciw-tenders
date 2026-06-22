# SP1: загрузка и хранение сметы + иерархический парсер — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Загрузить Excel-смету, иерархически распарсить нумерованные узлы (с `embedding_input` симметрично справочнику), сохранить смету в БД (узлы `pending`) и исходный файл в MinIO.

**Architecture:** Clean Architecture. Чистый парсер (`bytes → ParsedEstimate`) в `services/`; персистентность через порты `EstimateRepository` (Postgres) и `ObjectStorage` (MinIO/boto3); оркестрация в `EstimateService`; синхронный endpoint загрузки (парс → put в MinIO → запись в БД). Матчинг — отдельный под-проект SP2.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 + Alembic, pandas + openpyxl, pgvector, boto3 (MinIO), pytest.

**Спека:** [docs/superpowers/specs/2026-06-22-estimate-hierarchical-parser-design.md](../specs/2026-06-22-estimate-hierarchical-parser-design.md)

## Global Constraints

- **Clean Architecture:** `api → services → domain ← infrastructure`. Домен без импортов FastAPI/SQLAlchemy/SDK. Порт в `domain/ports.py` → реализация в `infrastructure/`.
- **ruff:** line-length 100, `target py311`, `from __future__ import annotations` в каждом модуле, type hints обязательны. `uv run ruff check .` перед коммитом.
- **Тесты не ходят в реальную БД/AI/MinIO** — фейки портов ([tests/fakes.py](../../../backend/tests/fakes.py)) + `app.dependency_overrides`.
- **Зависимости — только через `uv add`** (не править `pyproject.toml` руками).
- **Кириллица в stdout:** при ручном прогоне Python ставить `PYTHONIOENCODING=utf-8`.
- **Команды из `backend/`:** `cd backend && uv run pytest ...`.
- **Эмбеддинги в SP1 не считаем:** узлы сохраняются `embedding = NULL`, `status = 'pending'`.
- **Колонки сметы (точные):** `№ раздела`, `Наименование раздела / позиции`, `Вид раздела`, `Статья СМР` (выход, игнорируется на входе).
- **`embedding_input` узла** = имена предков (от корня, усечением сегментов) + собственное имя, через `". "` — байт-в-байт как `template_parser`.
- **`source_index`** = исходная 0-based позиция строки данных (`df.iterrows()`), захватывается ДО skip/реклассификаций; **запрещены** `enumerate`-по-выжившим и `reset_index`. Физ.строка Excel = `source_index + 2`.
- **Расхождение со спекой (осознанно):** спека называет `EstimateIngestService` (ingest) и list/get/delete в «API»; в плане они консолидированы в один `EstimateService` (ingest/list/get/delete) — меньше DI-поверхность, чистка MinIO при удалении не течёт в роут.
- **Приватность golden-файла:** реальную смету `temp/Смета — копия.xlsx` в git НЕ коммитим (коммерческие данные). Golden-тест читает её по пути со `skipif(not exists)`; ассерты логики — на синтетических фикстурах.

---

## File Structure

- `backend/app/domain/entities.py` (modify) — сущности парсинга + персистентные.
- `backend/app/domain/ports.py` (modify) — порты `EstimateRepository`, `ObjectStorage`.
- `backend/app/services/estimate_parser.py` (create) — чистый парсер.
- `backend/app/services/estimate_service.py` (create) — ingest/list/get/delete.
- `backend/app/infrastructure/db/estimate_repository.py` (create) — `SqlAlchemyEstimateRepository`.
- `backend/app/infrastructure/storage/__init__.py`, `s3_object_storage.py` (create) — `S3ObjectStorage`.
- `backend/app/infrastructure/db/models.py` (modify) — `EstimateModel`, `EstimateRowModel`.
- `backend/alembic/versions/0003_estimates.py` (create) — миграция.
- `backend/app/core/config.py` (modify) — `S3_*`, `estimate_max_upload_mb`.
- `backend/app/api/schemas.py` (modify) — DTO смет.
- `backend/app/api/deps.py` (modify) — DI смет.
- `backend/app/api/routes/estimates.py` (modify) — роуты загрузки/списка/просмотра/удаления.
- `backend/tests/fakes.py` (modify) — `FakeEstimateRepository`, `FakeObjectStorage`.
- `backend/tests/test_estimate_parser.py`, `test_estimate_service.py`, `test_estimate_routes.py`, `test_estimate_models.py` (create).

---

## Task 1: Конфиг и зависимость boto3

**Files:**
- Modify: `backend/pyproject.toml` (через `uv add`)
- Modify: `backend/app/core/config.py:19-37`
- Modify: `backend/tests/conftest.py` (env по умолчанию)
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.s3_endpoint`, `Settings.s3_access_key`, `Settings.s3_secret_key`, `Settings.s3_bucket`, `Settings.estimate_max_upload_mb: float`.

- [ ] **Step 1: Добавить зависимость boto3**

Run: `cd backend && uv add boto3`
Expected: `boto3` появляется в `pyproject.toml [project.dependencies]`, `uv.lock` обновлён.

- [ ] **Step 2: Failing-тест на новые поля конфига**

Дописать в `backend/tests/test_config.py`:

```python
def test_settings_have_s3_and_upload_limit() -> None:
    from app.core.config import Settings

    s = Settings()  # env заданы в conftest
    assert s.s3_bucket == "estimates"
    assert s.estimate_max_upload_mb == 25.0
    assert s.s3_endpoint  # непустой дефолт
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend && uv run pytest tests/test_config.py::test_settings_have_s3_and_upload_limit -v`
Expected: FAIL (`AttributeError`/`ValidationError` — полей нет).

- [ ] **Step 4: Добавить поля в Settings**

В `backend/app/core/config.py` после `admin_password` добавить:

```python
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "estimates"

    estimate_max_upload_mb: float = 25.0
```

- [ ] **Step 5: Прокинуть дефолты в тестовое окружение**

В `backend/tests/conftest.py` дописать (S3 не дёргается в тестах, но Settings импортируется при старте app):

```python
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_BUCKET", "estimates")
```

- [ ] **Step 6: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_config.py -v && uv run ruff check app/core/config.py`
Expected: PASS, ruff чисто.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/conftest.py backend/tests/test_config.py
git commit -m "feat(estimates): конфиг S3/MinIO + лимит загрузки, зависимость boto3"
```

---

## Task 2: Миграция 0003 + ORM-модели estimates/estimate_rows

**Files:**
- Create: `backend/alembic/versions/0003_estimates.py`
- Modify: `backend/app/infrastructure/db/models.py`
- Test: `backend/tests/test_estimate_models.py`

**Interfaces:**
- Produces: таблицы `estimates`, `estimate_rows`; ORM `EstimateModel`, `EstimateRowModel`.

- [ ] **Step 1: Написать миграцию 0003 (raw SQL, как 0001)**

Create `backend/alembic/versions/0003_estimates.py`:

```python
"""estimates + estimate_rows

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE estimates (
            id                  SERIAL PRIMARY KEY,
            user_id             INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            filename            TEXT NOT NULL,
            original_object_key TEXT NOT NULL,
            status              VARCHAR(32) NOT NULL DEFAULT 'pending',
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX idx_estimates_user_id ON estimates (user_id)")
    op.execute(
        """
        CREATE TABLE estimate_rows (
            id              SERIAL PRIMARY KEY,
            estimate_id     INTEGER NOT NULL REFERENCES estimates (id) ON DELETE CASCADE,
            source_index    INTEGER NOT NULL,
            code            VARCHAR(64) NOT NULL,
            name            TEXT NOT NULL,
            parent_code     VARCHAR(64),
            section_type    VARCHAR(32),
            depth           INTEGER NOT NULL,
            embedding_input TEXT NOT NULL,
            embedding       VECTOR(768),
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            CONSTRAINT uq_estimate_rows_estimate_source UNIQUE (estimate_id, source_index)
        )
        """
    )
    op.execute("CREATE INDEX idx_estimate_rows_estimate_id ON estimate_rows (estimate_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS estimate_rows")
    op.execute("DROP TABLE IF EXISTS estimates")
```

> **Заметки:** `VECTOR(768)` опирается на расширение `vector`, которое создаёт ревизия `0001`
> (`CREATE EXTENSION IF NOT EXISTS vector`, [0001:21](../../../backend/alembic/versions/0001_initial_schema.py#L21)) — `0003` после неё корректен. Паритет миграция↔ORM нигде не ассертится (тест проверяет лишь метаданные ORM) — в духе конвенций для `0001`; держать в уме при ручном `just migrate`.

- [ ] **Step 2: Добавить ORM-модели**

В конец `backend/app/infrastructure/db/models.py` добавить (использует уже импортированные `Vector`, `_EMBEDDING_DIM`, `ForeignKey`, и т.д.):

```python
class EstimateModel(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EstimateRowModel(Base):
    __tablename__ = "estimate_rows"
    __table_args__ = (
        UniqueConstraint("estimate_id", "source_index", name="uq_estimate_rows_estimate_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_index: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_input: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
```

Добавить `UniqueConstraint` в импорт `sqlalchemy` в шапке файла.

- [ ] **Step 3: Failing-тест на ORM-метаданные (без БД)**

Create `backend/tests/test_estimate_models.py`:

```python
from __future__ import annotations

from app.infrastructure.db.models import EstimateModel, EstimateRowModel


def test_estimate_tables_and_columns() -> None:
    assert EstimateModel.__tablename__ == "estimates"
    cols = set(EstimateModel.__table__.columns.keys())
    assert {"user_id", "filename", "original_object_key", "status"} <= cols

    assert EstimateRowModel.__tablename__ == "estimate_rows"
    rcols = set(EstimateRowModel.__table__.columns.keys())
    assert {"estimate_id", "source_index", "code", "embedding_input", "embedding"} <= rcols
```

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_estimate_models.py -v`
Expected: PASS (модели импортируются, колонки на месте).

- [ ] **Step 5: ruff**

Run: `cd backend && uv run ruff check app/infrastructure/db/models.py tests/test_estimate_models.py`
Expected: чисто.

- [ ] **Step 6: Commit** (миграцию на боевой БД применяет `just migrate` вручную — не в тестах)

```bash
git add backend/alembic/versions/0003_estimates.py backend/app/infrastructure/db/models.py backend/tests/test_estimate_models.py
git commit -m "feat(estimates): миграция 0003 + ORM estimates/estimate_rows"
```

---

## Task 3: Чистый парсер `EstimateParser`

**Files:**
- Modify: `backend/app/domain/entities.py`
- Create: `backend/app/services/estimate_parser.py`
- Test: `backend/tests/test_estimate_parser.py`

**Interfaces:**
- Produces (domain): `EstimateRowKind(StrEnum)`, `EstimateNode`, `EstimatePosition`, `ParsedEstimate`.
- Produces (service): `EstimateParser.parse(content: bytes) -> ParsedEstimate`.
- `EstimateNode(code, name, parent_code, section_type, embedding_input, source_index, depth)`.

- [ ] **Step 1: Добавить доменные сущности парсинга**

В `backend/app/domain/entities.py` (после `EstimateRow` импортов dataclass/StrEnum уже есть) добавить:

```python
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
```

- [ ] **Step 2: Failing-тесты — структура, классификация, dtype, source_index, embedding_input, грязь**

Create `backend/tests/test_estimate_parser.py`:

```python
from __future__ import annotations

import io

import pandas as pd

from app.services.estimate_parser import EstimateParser

_NO = "№ раздела"
_NAME = "Наименование раздела / позиции"
_TYPE = "Вид раздела"


def _xlsx(rows: list[tuple[object, object, object]]) -> bytes:
    """rows: (№ раздела, наименование, вид раздела). None → пустая ячейка."""
    df = pd.DataFrame(rows, columns=[_NO, _NAME, _TYPE])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def test_classifies_nodes_and_positions() -> None:
    content = _xlsx(
        [
            ("1", "Подготовительные работы", "СМР"),
            ("1.1", "Этапы", None),
            (None, "Позиция А", None),
            (None, "Позиция Б", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1", "1.1"]
    assert [p.name for p in parsed.positions] == ["Позиция А", "Позиция Б"]
    assert parsed.positions[0].parent_code == "1.1"


def test_embedding_input_is_ancestors_plus_name_no_descendants() -> None:
    content = _xlsx(
        [
            ("1", "Подготовительные работы", "СМР"),
            ("1.1", "Этапы", None),
            ("1.1.5", "МОКАП", None),
            ("1.1.5.1", "МОКАП фасада", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    by_code = {n.code: n for n in parsed.nodes}
    assert by_code["1.1.5"].embedding_input == "Подготовительные работы. Этапы. МОКАП"
    assert by_code["1.1.5"].parent_code == "1.1"
    assert by_code["1.1.5"].section_type == "СМР"
    assert by_code["1.1.5"].depth == 3


def test_ancestors_by_segment_not_string_prefix() -> None:
    # 1.10 и 1.2 не должны путаться; предки 1.10 — это [1], не [1, 1.1]
    content = _xlsx(
        [
            ("1", "Раздел", "СМР"),
            ("1.2", "Второй", None),
            ("1.10", "Десятый", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    by_code = {n.code: n for n in parsed.nodes}
    assert by_code["1.10"].embedding_input == "Раздел. Десятый"
    assert by_code["1.10"].parent_code == "1"


def test_dtype_numeric_code_read_as_string() -> None:
    # числовые ячейки кода: без dtype=str pandas инферит float (1 → 1.0 → два сегмента)
    content = _xlsx([(1, "Раздел", "СМР"), (1.5, "Подраздел", None)])
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1", "1.5"]
    assert parsed.nodes[0].depth == 1


def test_source_index_integrity_with_skip_above() -> None:
    # пустое имя ВЫШЕ узла: позиционный индекс и счётчик выживших расходятся
    content = _xlsx(
        [
            ("1", "Раздел", "СМР"),   # df idx 0
            ("1.1", None, None),       # df idx 1 — пустое имя, пропускается
            ("1.2", "Живой узел", None),  # df idx 2 → source_index ДОЛЖЕН быть 2
        ]
    )
    parsed = EstimateParser().parse(content)
    live = next(n for n in parsed.nodes if n.code == "1.2")
    assert live.source_index == 2  # на enumerate-по-выжившим было бы 1


def test_duplicate_code_keeps_first_name_and_warns() -> None:
    content = _xlsx(
        [
            ("1", "Первый", "СМР"),
            ("1.1", "Имя-А", None),
            ("1.1", "Имя-Б", None),       # дубль кода
            ("1.1.1", "Дитя", None),
        ]
    )
    parsed = EstimateParser().parse(content)
    assert sum(n.code == "1.1" for n in parsed.nodes) == 2          # оба сохранены
    child = next(n for n in parsed.nodes if n.code == "1.1.1")
    assert child.embedding_input == "Первый. Имя-А. Дитя"           # имя предка — первое
    assert any("1.1" in w for w in parsed.warnings)


def test_non_numeric_code_becomes_position_with_warning() -> None:
    content = _xlsx([("1", "Раздел", "СМР"), ("прим", "Примечание", None)])
    parsed = EstimateParser().parse(content)
    assert [n.code for n in parsed.nodes] == ["1"]
    assert any(p.name == "Примечание" for p in parsed.positions)
    assert parsed.warnings


def test_missing_required_column_raises() -> None:
    df = pd.DataFrame({"X": [1], "Y": [2]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    import pytest

    with pytest.raises(ValueError):
        EstimateParser().parse(buf.getvalue())
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend && uv run pytest tests/test_estimate_parser.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.estimate_parser`).

- [ ] **Step 4: Реализовать парсер**

Create `backend/app/services/estimate_parser.py`:

```python
"""Иерархический парсер сметы. Чистая логика: bytes → ParsedEstimate. Без БД/AI."""

from __future__ import annotations

import io
import re

import pandas as pd

from app.domain.entities import EstimateNode, EstimatePosition, ParsedEstimate

SECTION_NO_COLUMN = "№ раздела"
NAME_COLUMN = "Наименование раздела / позиции"
SECTION_TYPE_COLUMN = "Вид раздела"


def _clean_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


class EstimateParser:
    """Строит дерево узлов из «№ раздела»; листья (№=NaN) — контекст."""

    def parse(self, content: bytes) -> ParsedEstimate:
        # № раздела — принудительно строкой: иначе number-formatted ячейка
        # коэрсится во float (1 → 1.0 → два сегмента), 1.10 схлопывается в 1.1.
        df = pd.read_excel(
            io.BytesIO(content), engine="openpyxl", dtype={SECTION_NO_COLUMN: str}
        )
        missing = {SECTION_NO_COLUMN, NAME_COLUMN} - set(df.columns)
        if missing:
            raise ValueError(f"В файле отсутствуют обязательные колонки: {sorted(missing)}")

        nodes: list[EstimateNode] = []
        positions: list[EstimatePosition] = []
        warnings: list[str] = []
        name_by_code: dict[str, str] = {}            # первое вхождение
        top_type_by_segment: dict[str, str | None] = {}
        last_node_code: str | None = None

        # source_index = ИСХОДНАЯ 0-based позиция (df.iterrows сохраняет RangeIndex);
        # НЕ enumerate по выжившим, НЕ reset_index — иначе после skip уедет на -1.
        for raw_idx, record in df.iterrows():
            source_index = int(raw_idx)  # type: ignore[arg-type]
            no = record[SECTION_NO_COLUMN]
            name = _clean_name(record[NAME_COLUMN])
            if not name or name.lower() == "nan":
                warnings.append(f"строка {source_index}: пустое имя — пропущена")
                continue

            if pd.isna(no):  # POSITION
                if last_node_code is None:
                    warnings.append(f"строка {source_index}: позиция до первого узла")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue

            code = re.sub(r"\s+", "", str(no)).strip(".")
            segments = code.split(".")
            if not code or not all(seg.isdigit() for seg in segments):
                warnings.append(f"строка {source_index}: нечисловой код '{no}' → позиция")
                positions.append(EstimatePosition(name, last_node_code, source_index))
                continue

            # NODE
            depth = len(segments)
            parent_code = ".".join(segments[:-1]) or None
            if code in name_by_code:
                warnings.append(f"строка {source_index}: дубль кода '{code}'")
            else:
                name_by_code[code] = name
            if depth == 1:
                vid = record[SECTION_TYPE_COLUMN] if SECTION_TYPE_COLUMN in df.columns else None
                top_type_by_segment[code] = None if pd.isna(vid) else str(vid).strip()
            section_type = top_type_by_segment.get(segments[0])

            parts: list[str] = []
            for i in range(1, depth):  # предки усечением сегментов
                ancestor = ".".join(segments[:i])
                if ancestor in name_by_code:
                    parts.append(name_by_code[ancestor])
                else:
                    warnings.append(f"строка {source_index}: нет предка '{ancestor}'")
            parts.append(name)
            embedding_input = ". ".join(parts)  # байт-в-байт как template_parser

            nodes.append(
                EstimateNode(
                    code=code,
                    name=name,
                    parent_code=parent_code,
                    section_type=section_type,
                    embedding_input=embedding_input,
                    source_index=source_index,
                    depth=depth,
                )
            )
            last_node_code = code

        return ParsedEstimate(nodes=nodes, positions=positions, warnings=warnings)
```

- [ ] **Step 5: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_estimate_parser.py -v`
Expected: PASS (все тесты Step 2).

- [ ] **Step 6: Golden-тест на реальном файле (skipif, не коммитим файл)**

Дописать в `backend/tests/test_estimate_parser.py`:

```python
import pytest
from pathlib import Path

_GOLDEN = Path(__file__).resolve().parents[2] / "temp" / "Смета — копия.xlsx"


@pytest.mark.skipif(not _GOLDEN.exists(), reason="реальная смета не коммитится (приватность)")
def test_golden_real_estimate_structure() -> None:
    parsed = EstimateParser().parse(_GOLDEN.read_bytes())
    assert len(parsed.nodes) == 809
    assert len(parsed.positions) == 1953
    top = [n for n in parsed.nodes if n.depth == 1]
    assert len(top) == 18
    assert sum(n.section_type == "СМР" for n in top) == 15
    # source_index → физ.ячейка: узел 1.1.5 «МОКАП» на df idx 33 (физ.строка 35)
    mokap = next(n for n in parsed.nodes if n.code == "1.1.5")
    assert mokap.source_index == 33
```

- [ ] **Step 7: Запустить golden + ruff**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest tests/test_estimate_parser.py -v && uv run ruff check app/services/estimate_parser.py tests/test_estimate_parser.py app/domain/entities.py`
Expected: PASS (golden проходит локально, где файл есть; иначе SKIPPED). ruff чисто.

- [ ] **Step 8: Commit**

```bash
git add backend/app/domain/entities.py backend/app/services/estimate_parser.py backend/tests/test_estimate_parser.py
git commit -m "feat(estimates): иерархический парсер сметы (предки+имя, source_index, dtype)"
```

---

## Task 4: Порты + персистентные сущности + фейки

**Files:**
- Modify: `backend/app/domain/entities.py`
- Modify: `backend/app/domain/ports.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_estimate_service.py` (заводим файл, тест фейков)

**Interfaces:**
- Produces (domain entities): `NewEstimate(user_id, filename, original_object_key)`, `StoredEstimateRow(...)`, `Estimate(id, user_id, filename, status, created_at, rows)`, `EstimateSummary(id, filename, status, nodes_count, created_at)`.
- Produces (ports): `EstimateRepository`, `ObjectStorage`.
- `EstimateRepository.create(new, nodes) -> Estimate`; `.list_for_owner(owner_id, *, is_admin) -> list[EstimateSummary]`; `.get(id, requester_id, *, is_admin) -> Estimate | None`; `.delete(id, requester_id, *, is_admin) -> str | None` (ключ удалённого объекта или None).
- `ObjectStorage.put(key, data, content_type) -> None`; `.get(key) -> bytes`; `.delete(key) -> None`.

- [ ] **Step 1: Персистентные сущности**

В `backend/app/domain/entities.py` добавить:

```python
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


@dataclass(frozen=True, slots=True)
class Estimate:
    """Агрегат сохранённой сметы (без original_object_key — наружу не отдаём)."""

    id: int
    user_id: int
    filename: str
    status: str
    created_at: datetime
    rows: list[StoredEstimateRow] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EstimateSummary:
    id: int
    filename: str
    status: str
    nodes_count: int
    created_at: datetime
```

- [ ] **Step 2: Доменная ошибка `StorageError`**

В `backend/app/domain/errors.py` добавить:

```python
class StorageError(Exception):
    """Сбой объектного хранилища (MinIO/S3 недоступно или ошибка операции)."""
```

- [ ] **Step 2b: Порты**

В `backend/app/domain/ports.py` добавить импорты `EstimateNode, NewEstimate, Estimate, EstimateSummary` и классы:

```python
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


class ObjectStorage(ABC):
    """Объектное хранилище (MinIO/S3) для исходных файлов."""

    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
```

- [ ] **Step 3: Фейки в tests/fakes.py**

Добавить импорты и классы (`datetime, timezone` уже импортированы в шапке `fakes.py:5` — не дублировать):

```python
from app.domain.entities import (
    Estimate,
    EstimateNode,
    EstimateSummary,
    NewEstimate,
    StoredEstimateRow,
)
from app.domain.errors import StorageError
from app.domain.ports import EstimateRepository, ObjectStorage


class FakeObjectStorage(ObjectStorage):
    def __init__(self, *, fail: bool = False) -> None:
        self.store: dict[str, bytes] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []
        self._fail = fail

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self._fail:
            raise StorageError("MinIO недоступен")
        self.put_calls.append(key)
        self.store[key] = data

    def get(self, key: str) -> bytes:
        return self.store[key]

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.store.pop(key, None)


class FakeEstimateRepository(EstimateRepository):
    def __init__(self) -> None:
        self.estimates: dict[int, Estimate] = {}
        self._keys: dict[int, str] = {}     # estimate_id -> object_key
        self._next = 1
        self.create_calls = 0

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        self.create_calls += 1
        eid = self._next
        self._next += 1
        rows = [
            StoredEstimateRow(
                id=i + 1,
                code=n.code,
                name=n.name,
                parent_code=n.parent_code,
                section_type=n.section_type,
                depth=n.depth,
                embedding_input=n.embedding_input,
                source_index=n.source_index,
                status="pending",
                has_embedding=False,
            )
            for i, n in enumerate(nodes)
        ]
        est = Estimate(
            id=eid,
            user_id=new.user_id,
            filename=new.filename,
            status="pending",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),  # noqa: UP017
            rows=rows,
        )
        self.estimates[eid] = est
        self._keys[eid] = new.original_object_key
        return est

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return [
            EstimateSummary(
                id=e.id,
                filename=e.filename,
                status=e.status,
                nodes_count=len(e.rows),
                created_at=e.created_at,
            )
            for e in self.estimates.values()
            if is_admin or e.user_id == owner_id
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
```

- [ ] **Step 4: Тест поведения фейков (владение, счётчики)**

Create `backend/tests/test_estimate_service.py` (пока только фейки):

```python
from __future__ import annotations

from app.domain.entities import EstimateNode, NewEstimate
from tests.fakes import FakeEstimateRepository, FakeObjectStorage


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, len(code.split(".")))


def test_repo_ownership_isolation() -> None:
    repo = FakeEstimateRepository()
    repo.create(NewEstimate(1, "a.xlsx", "k1"), [_node("1")])
    repo.create(NewEstimate(2, "b.xlsx", "k2"), [_node("1")])
    assert [s.id for s in repo.list_for_owner(1, is_admin=False)] == [1]
    assert {s.id for s in repo.list_for_owner(9, is_admin=True)} == {1, 2}
    assert repo.get(2, requester_id=1, is_admin=False) is None
    assert repo.delete(1, requester_id=2, is_admin=False) is None  # чужая
    assert repo.delete(1, requester_id=1, is_admin=False) == "k1"  # ключ объекта


def test_fake_storage_records_calls() -> None:
    s = FakeObjectStorage()
    s.put("k", b"data", "x")
    assert s.put_calls == ["k"] and s.get("k") == b"data"
    s.delete("k")
    assert s.delete_calls == ["k"]
```

- [ ] **Step 5: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_service.py -v && uv run ruff check app/domain/ports.py tests/fakes.py`
Expected: PASS, ruff чисто.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/domain/errors.py backend/tests/fakes.py backend/tests/test_estimate_service.py
git commit -m "feat(estimates): порты EstimateRepository/ObjectStorage + StorageError + фейки"
```

---

## Task 5: `EstimateService` (ingest/list/get/delete) на фейках

**Files:**
- Create: `backend/app/services/estimate_service.py`
- Test: `backend/tests/test_estimate_service.py`

**Interfaces:**
- Consumes: `EstimateParser`, `EstimateRepository`, `ObjectStorage`, `EstimateNode`, `NewEstimate`, `Estimate`, `EstimateSummary`.
- Produces: `EstimateService.ingest(content, filename, owner_id) -> IngestResult`; `.list(owner_id, is_admin)`; `.get(id, requester_id, is_admin)`; `.delete(id, requester_id, is_admin) -> bool`.
- `IngestResult(estimate: Estimate, positions_count: int, warnings: list[str])`.

- [ ] **Step 1: Failing-тесты сервиса**

Дописать в `backend/tests/test_estimate_service.py`:

```python
import io

import pandas as pd
import pytest

from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService


def _xlsx() -> bytes:
    df = pd.DataFrame(
        [("1", "Раздел", "СМР"), ("1.1", "Под", None), (None, "Позиция", None)],
        columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _service(storage: FakeObjectStorage) -> tuple[EstimateService, FakeEstimateRepository]:
    repo = FakeEstimateRepository()
    return EstimateService(EstimateParser(), repo, storage), repo


def test_ingest_puts_file_then_saves_nodes_pending() -> None:
    storage = FakeObjectStorage()
    service, repo = _service(storage)
    result = service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert result.estimate.status == "pending"
    assert [r.code for r in result.estimate.rows] == ["1", "1.1"]
    assert all(r.status == "pending" and not r.has_embedding for r in result.estimate.rows)
    assert result.positions_count == 1
    assert len(storage.put_calls) == 1            # файл загружен
    assert repo.create_calls == 1


def test_ingest_storage_failure_does_not_touch_db() -> None:
    from app.domain.errors import StorageError

    storage = FakeObjectStorage(fail=True)
    service, repo = _service(storage)
    with pytest.raises(StorageError):
        service.ingest(_xlsx(), "смета.xlsx", owner_id=7)
    assert repo.create_calls == 0                 # порядок put→INSERT соблюдён


def test_delete_removes_db_and_object() -> None:
    storage = FakeObjectStorage()
    service, repo = _service(storage)
    est = service.ingest(_xlsx(), "смета.xlsx", owner_id=7).estimate
    assert service.delete(est.id, requester_id=7, is_admin=False) is True
    assert storage.delete_calls  # объект удалён best-effort
    assert service.get(est.id, requester_id=7, is_admin=False) is None
```

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_estimate_service.py -v`
Expected: FAIL (`ModuleNotFoundError: app.services.estimate_service`).

- [ ] **Step 3: Реализовать сервис**

Create `backend/app/services/estimate_service.py`:

```python
"""Сценарии работы со сметами: ingest (парс → MinIO → БД) + list/get/delete."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.entities import Estimate, EstimateSummary, NewEstimate
from app.domain.ports import EstimateRepository, ObjectStorage
from app.services.estimate_parser import EstimateParser

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True, slots=True)
class IngestResult:
    estimate: Estimate
    positions_count: int
    warnings: list[str]


class EstimateService:
    def __init__(
        self,
        parser: EstimateParser,
        repository: EstimateRepository,
        storage: ObjectStorage,
    ) -> None:
        self._parser = parser
        self._repository = repository
        self._storage = storage

    def ingest(self, content: bytes, filename: str, owner_id: int) -> IngestResult:
        parsed = self._parser.parse(content)  # бросает ValueError (нет колонок) до put
        key = f"estimates/{uuid.uuid4().hex}/{filename}"
        self._storage.put(key, content, _XLSX_CONTENT_TYPE)  # падение → проброс, БД не тронута
        estimate = self._repository.create(
            NewEstimate(user_id=owner_id, filename=filename, original_object_key=key),
            parsed.nodes,
        )
        return IngestResult(
            estimate=estimate,
            positions_count=len(parsed.positions),
            warnings=parsed.warnings,
        )

    def list(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return self._repository.list_for_owner(owner_id, is_admin=is_admin)

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        return self._repository.get(estimate_id, requester_id, is_admin=is_admin)

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> bool:
        key = self._repository.delete(estimate_id, requester_id, is_admin=is_admin)
        if key is None:
            return False
        try:
            self._storage.delete(key)  # best-effort: сирота подберёт реапер (тех-долг)
        except Exception:  # noqa: BLE001
            pass
        return True
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_service.py -v && uv run ruff check app/services/estimate_service.py`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_service.py backend/tests/test_estimate_service.py
git commit -m "feat(estimates): EstimateService — ingest (put→INSERT) + list/get/delete"
```

---

## Task 6: Реальные адаптеры (Postgres + MinIO)

**Files:**
- Create: `backend/app/infrastructure/db/estimate_repository.py`
- Create: `backend/app/infrastructure/storage/__init__.py`
- Create: `backend/app/infrastructure/storage/s3_object_storage.py`
- Test: `backend/tests/test_estimate_repository_mapping.py`

**Interfaces:**
- Produces: `SqlAlchemyEstimateRepository(session)`, `S3ObjectStorage(...)`. Реализуют порты Task 4.
- Реальные БД/MinIO **не** тестируются юнитами (как `SqlAlchemyArticleRepository`/`OpenRouterEmbedder` — проверяются вручную); юнит-тест покрывает только чистый маппинг model→entity.

- [ ] **Step 1: Реализовать `SqlAlchemyEstimateRepository`**

Create `backend/app/infrastructure/db/estimate_repository.py`:

```python
"""SQL-реализация EstimateRepository (Postgres). Создание сметы + узлов в транзакции."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.entities import (
    Estimate,
    EstimateNode,
    EstimateSummary,
    NewEstimate,
    StoredEstimateRow,
)
from app.domain.ports import EstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel


class SqlAlchemyEstimateRepository(EstimateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

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
        )

    @classmethod
    def _to_entity(cls, m: EstimateModel, rows: list[EstimateRowModel]) -> Estimate:
        return Estimate(
            id=m.id,
            user_id=m.user_id,
            filename=m.filename,
            status=m.status,
            created_at=m.created_at,
            rows=[cls._row_to_entity(r) for r in rows],
        )

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        try:
            est = EstimateModel(
                user_id=new.user_id,
                filename=new.filename,
                original_object_key=new.original_object_key,
                status="pending",
            )
            self._session.add(est)
            self._session.flush()  # получить est.id
            row_models = [
                EstimateRowModel(
                    estimate_id=est.id,
                    source_index=n.source_index,
                    code=n.code,
                    name=n.name,
                    parent_code=n.parent_code,
                    section_type=n.section_type,
                    depth=n.depth,
                    embedding_input=n.embedding_input,
                    embedding=None,
                    status="pending",
                )
                for n in nodes
            ]
            self._session.add_all(row_models)
            self._session.commit()
            # SessionLocal: expire_on_commit=False (session.py) — атрибуты не истекают после
            # commit, поэтому _to_entity читает row_models из памяти БЕЗ перезагрузок (нет N+1
            # на 809 строк). Единственный пост-коммит запрос — refresh(est) ради created_at.
            self._session.refresh(est)
            return self._to_entity(est, sorted(row_models, key=lambda r: r.source_index))
        except Exception:
            self._session.rollback()
            raise

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        counts = (
            select(
                EstimateRowModel.estimate_id,
                func.count().label("n"),
            )
            .group_by(EstimateRowModel.estimate_id)
            .subquery()
        )
        stmt = select(EstimateModel, func.coalesce(counts.c.n, 0)).outerjoin(
            counts, counts.c.estimate_id == EstimateModel.id
        )
        if not is_admin:
            stmt = stmt.where(EstimateModel.user_id == owner_id)
        stmt = stmt.order_by(EstimateModel.created_at.desc())
        return [
            EstimateSummary(
                id=m.id,
                filename=m.filename,
                status=m.status,
                nodes_count=int(n),
                created_at=m.created_at,
            )
            for m, n in self._session.execute(stmt)
        ]

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        rows = list(
            self._session.scalars(
                select(EstimateRowModel)
                .where(EstimateRowModel.estimate_id == estimate_id)
                .order_by(EstimateRowModel.source_index)
            )
        )
        return self._to_entity(est, rows)

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        key = est.original_object_key
        self._session.execute(delete(EstimateModel).where(EstimateModel.id == estimate_id))
        self._session.commit()
        return key
```

- [ ] **Step 2: Реализовать `S3ObjectStorage`**

Create `backend/app/infrastructure/storage/__init__.py` (пустой) и `backend/app/infrastructure/storage/s3_object_storage.py`:

```python
"""Адаптер ObjectStorage на boto3 (S3-совместимый, MinIO через endpoint_url)."""

from __future__ import annotations

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.domain.errors import StorageError
from app.domain.ports import ObjectStorage

_S3_ERRORS = (BotoCoreError, ClientError)


class S3ObjectStorage(ObjectStorage):
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        *,
        ensure_bucket: bool = True,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )
        if ensure_bucket:
            self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except self._client.exceptions.ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        except _S3_ERRORS as exc:  # граница: ошибки boto3 → доменный StorageError
            raise StorageError(f"put {key}: {exc}") from exc

    def get(self, key: str) -> bytes:
        try:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
        except _S3_ERRORS as exc:
            raise StorageError(f"get {key}: {exc}") from exc

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except _S3_ERRORS as exc:
            raise StorageError(f"delete {key}: {exc}") from exc
```

- [ ] **Step 3: Тест маппинга репозитория (без БД)**

Create `backend/tests/test_estimate_repository_mapping.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone

from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel


def test_row_mapping_has_embedding_flag() -> None:
    m = EstimateRowModel(
        id=5, estimate_id=1, source_index=33, code="1.1.5", name="МОКАП",
        parent_code="1.1", section_type="СМР", depth=3, embedding_input="...",
        embedding=None, status="pending",
    )
    row = SqlAlchemyEstimateRepository._row_to_entity(m)
    assert row.code == "1.1.5" and row.source_index == 33 and row.has_embedding is False


def test_estimate_mapping_excludes_object_key() -> None:
    est = EstimateModel(
        id=1, user_id=7, filename="смета.xlsx", original_object_key="k",
        status="pending", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    entity = SqlAlchemyEstimateRepository._to_entity(est, [])
    assert entity.user_id == 7 and entity.filename == "смета.xlsx"
    assert not hasattr(entity, "original_object_key")
```

- [ ] **Step 4: Запустить — зелёный + ruff**

Run: `cd backend && uv run pytest tests/test_estimate_repository_mapping.py -v && uv run ruff check app/infrastructure/db/estimate_repository.py app/infrastructure/storage/`
Expected: PASS, ruff чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/db/estimate_repository.py backend/app/infrastructure/storage/ backend/tests/test_estimate_repository_mapping.py
git commit -m "feat(estimates): адаптеры SqlAlchemyEstimateRepository + S3ObjectStorage"
```

---

## Task 7: DTO-схемы + DI-проводка

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/deps.py`

**Interfaces:**
- Produces (schemas): `EstimateUploadResponse`, `EstimateSummaryOut`, `EstimateRowOut`, `EstimateDetailOut` (+ `from_entity`).
- Produces (DI): `get_object_storage`, `get_estimate_repository`, `get_estimate_service`.

- [ ] **Step 1: DTO-схемы**

В `backend/app/api/schemas.py` добавить импорт `Estimate, EstimateSummary, StoredEstimateRow` и:

```python
class EstimateUploadResponse(BaseModel):
    id: int
    status: str
    nodes_count: int
    positions_count: int
    warnings: list[str]


class EstimateSummaryOut(BaseModel):
    id: int
    filename: str
    status: str
    nodes_count: int
    created_at: datetime

    @classmethod
    def from_entity(cls, s: EstimateSummary) -> EstimateSummaryOut:
        return cls(
            id=s.id, filename=s.filename, status=s.status,
            nodes_count=s.nodes_count, created_at=s.created_at,
        )


class EstimateRowOut(BaseModel):
    code: str
    name: str
    parent_code: str | None
    section_type: str | None
    depth: int
    status: str

    @classmethod
    def from_entity(cls, r: StoredEstimateRow) -> EstimateRowOut:
        return cls(
            code=r.code, name=r.name, parent_code=r.parent_code,
            section_type=r.section_type, depth=r.depth, status=r.status,
        )


class EstimateDetailOut(BaseModel):
    id: int
    filename: str
    status: str
    created_at: datetime
    rows: list[EstimateRowOut]

    @classmethod
    def from_entity(cls, e: Estimate) -> EstimateDetailOut:
        return cls(
            id=e.id, filename=e.filename, status=e.status, created_at=e.created_at,
            rows=[EstimateRowOut.from_entity(r) for r in e.rows],
        )
```

- [ ] **Step 2: DI в deps.py**

В `backend/app/api/deps.py` добавить импорты и провайдеры:

```python
from app.domain.ports import EstimateRepository, ObjectStorage  # к существующим
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.storage.s3_object_storage import S3ObjectStorage
from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService
```

```python
def get_estimate_parser() -> EstimateParser:
    return EstimateParser()


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    return S3ObjectStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )


def get_estimate_repository(session: Session = Depends(get_session)) -> EstimateRepository:
    return SqlAlchemyEstimateRepository(session)


def get_estimate_service(
    parser: EstimateParser = Depends(get_estimate_parser),
    repository: EstimateRepository = Depends(get_estimate_repository),
    storage: ObjectStorage = Depends(get_object_storage),
) -> EstimateService:
    return EstimateService(parser=parser, repository=repository, storage=storage)
```

- [ ] **Step 3: Проверка импорта (без БД/MinIO)**

`get_object_storage` создаёт boto3-клиент лениво (по запросу) — при импорте deps S3 не дёргается. Проверить, что модуль импортируется:

Run: `cd backend && uv run python -c "import app.api.deps; import app.api.schemas; print('ok')"`
Expected: `ok` (создание клиента отложено до вызова `get_object_storage`).

- [ ] **Step 4: ruff**

Run: `cd backend && uv run ruff check app/api/deps.py app/api/schemas.py`
Expected: чисто.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/schemas.py backend/app/api/deps.py
git commit -m "feat(estimates): DTO-схемы + DI-проводка (parser/storage/repo/service)"
```

---

## Task 8: Роуты + пред-валидация + тесты эндпоинтов

**Files:**
- Modify: `backend/app/api/routes/estimates.py`
- Test: `backend/tests/test_estimate_routes.py`

**Interfaces:**
- Consumes: `get_current_user`, `get_estimate_service`, `get_settings`, DTO Task 7, `EstimateService`.
- Produces: `POST /api/estimates`, `GET /api/estimates`, `GET /api/estimates/{id}`, `DELETE /api/estimates/{id}`.

- [ ] **Step 1: Failing-тесты эндпоинтов**

Create `backend/tests/test_estimate_routes.py`:

```python
from __future__ import annotations

import io
from collections.abc import Callable

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_estimate_service, get_settings
from app.core.config import Settings
from app.domain.entities import Role, User
from app.main import app
from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService
from tests.fakes import FakeEstimateRepository, FakeObjectStorage

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def _clear_overrides():
    # teardown-чистка: изоляция НЕ зависит от того, дошёл ли тест до конца
    # (инлайн-clear после упавшего ассерта протекал бы в следующий тест).
    yield
    app.dependency_overrides.clear()


def _xlsx() -> bytes:
    df = pd.DataFrame(
        [("1", "Раздел", "СМР"), ("1.1", "Под", None), (None, "Позиция", None)],
        columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _user(uid: int = 2, role: Role = Role.USER) -> Callable[[], User]:
    return lambda: User(id=uid, email=f"u{uid}@mr.kz", password_hash="h", role=role)


def _svc_factory(repo: FakeEstimateRepository, storage: FakeObjectStorage):
    def _f() -> EstimateService:
        return EstimateService(EstimateParser(), repo, storage)

    return _f


def _client(repo, storage, user=_user()) -> TestClient:
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_estimate_service] = _svc_factory(repo, storage)
    return TestClient(app)


def test_upload_creates_estimate() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["nodes_count"] == 2 and body["positions_count"] == 1
    assert len(storage.put_calls) == 1


def test_upload_rejects_bad_extension_without_storage() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.txt", b"PK\x03\x04xx", "text/plain")})
    assert resp.status_code == 422
    assert storage.put_calls == [] and repo.create_calls == 0


def test_upload_rejects_bad_signature() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", b"not a zip", _XLSX)})
    assert resp.status_code == 422
    assert storage.put_calls == []


def test_upload_rejects_oversize() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    app.dependency_overrides[get_settings] = lambda: Settings(estimate_max_upload_mb=0.0001)
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 413
    assert storage.put_calls == []


def test_upload_missing_column_422_without_storage() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    bad = io.BytesIO()
    pd.DataFrame({"X": [1]}).to_excel(bad, index=False, engine="openpyxl")
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", bad.getvalue(), _XLSX)})
    assert resp.status_code == 422
    assert storage.put_calls == []  # парс падает до put


def test_upload_storage_unavailable_503() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage(fail=True)
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 503
    assert repo.create_calls == 0


def test_list_and_get_ownership() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage).ingest(_xlsx(), "a.xlsx", owner_id=2)
    client = _client(repo, storage)  # user id=2
    assert len(client.get("/api/estimates").json()) == 1
    other = _client(repo, storage, user=_user(uid=9))  # чужой
    assert other.get("/api/estimates/1").status_code == 404


def test_delete_removes_object() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage).ingest(_xlsx(), "a.xlsx", owner_id=2)
    client = _client(repo, storage)
    resp = client.delete("/api/estimates/1")
    assert resp.status_code == 204
    assert storage.delete_calls  # объект MinIO удалён


def test_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/estimates").status_code == 401
```

> **Изоляция тестов:** `app.dependency_overrides` чистит **autouse-фикстура** `_clear_overrides` в teardown — инлайн-`clear()` в телах НЕ используем (упавший ассерт до `clear()` протёк бы в следующий тест, особенно ломая `test_requires_auth`).

- [ ] **Step 2: Запустить — падает**

Run: `cd backend && uv run pytest tests/test_estimate_routes.py -v`
Expected: FAIL (новых роутов нет; existing 401-тест может пройти).

- [ ] **Step 3: Реализовать роуты**

В `backend/app/api/routes/estimates.py` добавить импорты и роуты (старый `POST /estimates/match` оставить как есть):

```python
from app.api.deps import get_current_user, get_estimate_service, get_settings
from app.api.schemas import EstimateDetailOut, EstimateSummaryOut, EstimateUploadResponse
from app.core.config import Settings
from app.domain.entities import Role, User
from app.domain.errors import StorageError
from app.services.estimate_service import EstimateService

_XLSX_SIGNATURE = b"PK\x03\x04"


@router.post("", response_model=EstimateUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_estimate(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
    settings: Settings = Depends(get_settings),
) -> EstimateUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ожидается файл .xlsx")
    max_bytes = int(settings.estimate_max_upload_mb * 1024 * 1024)
    too_large = HTTPException(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        f"Файл больше {settings.estimate_max_upload_mb} МБ",
    )
    if file.size is not None and file.size > max_bytes:  # быстрый путь, если size заполнен
        raise too_large
    content = await file.read()
    if len(content) > max_bytes:  # авторитетный бэкстоп — не зависит от версии Starlette
        raise too_large
    if not content.startswith(_XLSX_SIGNATURE):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Файл не является .xlsx (ZIP)")

    try:
        result = service.ingest(content, file.filename, owner_id=user.id or 0)
    except ValueError as exc:  # нет обязательных колонок — до put в MinIO
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except StorageError as exc:  # ТОЛЬКО сбой MinIO → 503; прочее (БД и т.п.) → 500
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Хранилище недоступно") from exc

    return EstimateUploadResponse(
        id=result.estimate.id,
        status=result.estimate.status,
        nodes_count=len(result.estimate.rows),
        positions_count=result.positions_count,
        warnings=result.warnings,
    )


@router.get("", response_model=list[EstimateSummaryOut])
def list_estimates(
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> list[EstimateSummaryOut]:
    is_admin = user.role is Role.ADMIN
    items = service.list(user.id or 0, is_admin=is_admin)
    return [EstimateSummaryOut.from_entity(s) for s in items]


@router.get("/{estimate_id}", response_model=EstimateDetailOut)
def get_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> EstimateDetailOut:
    est = service.get(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    return EstimateDetailOut.from_entity(est)


@router.delete("/{estimate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    service: EstimateService = Depends(get_estimate_service),
) -> None:
    if not service.delete(estimate_id, user.id or 0, is_admin=user.role is Role.ADMIN):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
```

Примечание: у роутера `estimates` уже есть `dependencies=[Depends(get_current_user)]` на уровне router — `get_current_user` в сигнатурах нужен, чтобы получить `user` в теле (это не двойная аутентификация, просто доступ к объекту).

- [ ] **Step 4: Запустить — зелёный**

Run: `cd backend && uv run pytest tests/test_estimate_routes.py -v`
Expected: PASS (все 9 тестов).

- [ ] **Step 5: Полный прогон + ruff**

Run: `cd backend && PYTHONIOENCODING=utf-8 uv run pytest && uv run ruff check .`
Expected: вся сюита зелёная (старые тесты не сломаны), ruff чисто.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/estimates.py backend/tests/test_estimate_routes.py
git commit -m "feat(estimates): роуты upload/list/get/delete + пред-валидация (тип/размер/сигнатура)"
```

---

## Self-Review

**Spec coverage:**
- Парсер (правила 1–9, `embedding_input`, `source_index`, dtype, лениво к грязи) → Task 3 ✓
- Модель данных (estimates/estimate_rows, VECTOR(768) без HNSW, uniqueness) → Task 2 ✓
- `parent_code` (не self-FK) → Task 2 (модель) + Task 3 (вычисление) ✓
- Порты `EstimateRepository`/`ObjectStorage` → Task 4 ✓
- MinIO/boto3 адаптер, конфиг S3_*/лимит → Task 1 + Task 6 ✓
- Сервис ingest (put→INSERT), list/get/delete, чистка MinIO при delete → Task 5 ✓
- API + пред-валидация (тип/сигнатура/размер→422/413, бэкстоп по `len(content)`); `StorageError`→503 (только MinIO, прочее→500); 404 владение; 401; autouse-чистка overrides → Task 8 ✓
- Типизированный `StorageError`: адаптер оборачивает boto3, роут ловит только его на 503 → Tasks 4, 6, 8 ✓
- Тесты: golden (skipif), синтетика грязи, source_index-целостность, не-вызов хранилища при отказе → Tasks 3, 8 ✓
- Вне объёма (матчинг, реапер сирот, обратная запись) → не реализуется (SP2/SP3) ✓

**Заметки реализации:**
- Реапер осиротевших объектов MinIO — занести в [docs/TECH_DEBT.md](../../TECH_DEBT.md) при выполнении Task 6 (назван в спеке).
- Миграция 0003 применяется к боевой БД вручную: `just migrate` (в тестах БД не поднимается).
- `_GOLDEN`-тест проходит только локально (где лежит `temp/Смета — копия.xlsx`); в чистом окружении — SKIPPED (файл намеренно не в git).
