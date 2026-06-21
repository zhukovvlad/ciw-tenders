# Template Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать админу загрузить справочник СМР из Excel в дерево `template_articles` (парсинг + санитайз + upsert с защитой удаления), а векторные эмбеддинги наполнять фоновым воркером через `google/gemini-embedding-2` (OpenRouter).

**Architecture:** Две фазы. Синхронный импорт: `TemplateParser` → чистая логика `compute_plan` → `TemplateIngestService.import_template` → `ArticleImportRepository.apply_plan` (одна транзакция, строки пишутся с `embedding=NULL`). Асинхронная фаза: `embed_worker` поллит `embedding IS NULL`, батч-эмбеддит `embedding_input`, пишет вектор через compare-and-swap. Чистая логика (parser, diff, orchestration, worker loop) покрыта юнит-тестами на фейках; SQL-адаптеры и миграция проверяются end-to-end смоук-прогоном (Task 9).

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 + pgvector, Alembic, pandas/openpyxl, httpx (OpenRouter), pytest + httpx TestClient, uv.

**Spec:** [docs/superpowers/specs/2026-06-21-template-ingestion-design.md](../specs/2026-06-21-template-ingestion-design.md)

## Global Constraints

- Чистая архитектура: направление `api → services → domain ← infrastructure`. Доменный слой без импортов FastAPI/SQLAlchemy/SDK. Бизнес-логика — в `services/`, не в роутах/репозиториях.
- Новая внешняя зависимость → сначала порт в `domain/ports.py`, реализация в `infrastructure/`.
- Все команды бэкенда — через `uv run` внутри `.venv` (не системный python/pip). Зависимости — только через `uv add`/`uv remove`.
- Ruff: line-length 100, target py311, `from __future__ import annotations` во всех модулях, type hints обязательны. Перед коммитом — `cd backend; uv run ruff check .`.
- Юнит-тесты НЕ ходят в реальную БД/AI — фейки портов ([backend/tests/fakes.py](../../../backend/tests/fakes.py)) + `app.dependency_overrides`.
- Windows PowerShell 5.1: в `justfile` разделитель команд `;`, не `&&`. Кириллица в stdout требует `PYTHONIOENCODING=utf-8`.
- Бэкенд-порт 8260. Эмбеддинг-размерность 768 (`VECTOR(768)`, HNSW). Эмбеддер: `google/gemini-embedding-2` через OpenRouter c `dimensions: 768`.
- `article_code` хранится нормализованным (`1.4.1`), UNIQUE. `embedding_input` самоподобен: `child.embedding_input == parent.embedding_input + ". " + child.name`.

---

### Task 1: Переключение эмбеддера на gemini-embedding-2 через OpenRouter

**Files:**
- Modify: `backend/pyproject.toml` (deps: +httpx, −google-generativeai) — через `uv`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/tests/conftest.py`
- Create: `backend/app/infrastructure/ai/openrouter_embedder.py`
- Delete: `backend/app/infrastructure/ai/gemini_embedder.py`
- Modify: `backend/app/api/deps.py:102-105` (`get_embedder`)
- Test: `backend/tests/test_openrouter_embedder.py`, `backend/tests/test_config.py`

**Interfaces:**
- Consumes: порт `Embedder` ([backend/app/domain/ports.py:34-41](../../../backend/app/domain/ports.py#L34-L41)) — `embed(text: str) -> list[float]`, `embed_batch(texts: list[str]) -> list[list[float]]`.
- Produces: `OpenRouterEmbedder(api_key: str, base_url: str = "https://openrouter.ai/api/v1", model: str = "google/gemini-embedding-2", dimensions: int = 768, *, client: httpx.Client | None = None, timeout: float = 60.0)`. Settings-поля `openrouter_api_key: str`, `embedding_base_url: str`, `embedding_model` (дефолт `"google/gemini-embedding-2"`), `embedding_dim: int = 768`.

- [ ] **Step 1: Поменять зависимости через uv**

```bash
cd backend
uv add httpx
uv remove google-generativeai
```
Expected: `httpx` появляется в `[project].dependencies`, `google-generativeai` исчезает; `uv.lock` обновлён.

- [ ] **Step 2: Добавить настройки эмбеддера в config.py**

В [backend/app/core/config.py](../../../backend/app/core/config.py) заменить блок AI-ключей/параметров:

```python
    database_url: str
    google_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    confidence_threshold: float = 0.90
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "google/gemini-embedding-2"
    llm_model: str = "claude-3-5-sonnet-20240620"
    embedding_dim: int = 768
```

- [ ] **Step 3: Написать падающий тест эмбеддера**

Создать `backend/tests/test_openrouter_embedder.py`:

```python
from __future__ import annotations

import json

import httpx

from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder


def _embedder(handler, captured) -> OpenRouterEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterEmbedder(
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-embedding-2",
        dimensions=768,
        client=client,
    )


def test_embed_single_builds_request_and_parses() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    out = _embedder(handler, captured).embed("бетон")

    assert out == [0.1, 0.2, 0.3]
    assert captured["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "google/gemini-embedding-2"
    assert captured["body"]["dimensions"] == 768
    assert captured["body"]["input"] == "бетон"


def test_embed_batch_sends_list_and_keeps_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"] == ["a", "b"]
        return httpx.Response(200, json={"data": [{"embedding": [1.0]}, {"embedding": [2.0]}]})

    out = _embedder(handler, {}).embed_batch(["a", "b"])
    assert out == [[1.0], [2.0]]


def test_embed_batch_empty_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("не должно быть запроса на пустой вход")

    assert _embedder(handler, {}).embed_batch([]) == []
```

- [ ] **Step 4: Запустить тест — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_openrouter_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError: app.infrastructure.ai.openrouter_embedder`.

- [ ] **Step 5: Реализовать OpenRouterEmbedder**

Создать `backend/app/infrastructure/ai/openrouter_embedder.py`:

```python
"""Реализация Embedder через OpenRouter (OpenAI-совместимый /embeddings).

Модель google/gemini-embedding-2 с параметром dimensions=768 (Matryoshka) — вектор
ложится в существующую схему VECTOR(768)/HNSW.
"""

from __future__ import annotations

import httpx

from app.domain.ports import Embedder


class OpenRouterEmbedder(Embedder):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "google/gemini-embedding-2",
        dimensions: int = 768,
        *,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._client = client or httpx.Client(timeout=timeout)

    def _post(self, value: str | list[str]) -> list[list[float]]:
        resp = self._client.post(
            f"{self._base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": value, "dimensions": self._dimensions},
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]

    def embed(self, text: str) -> list[float]:
        return self._post(text)[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._post(texts)
```

- [ ] **Step 6: Запустить тест — убедиться, что проходит**

Run: `cd backend; uv run pytest tests/test_openrouter_embedder.py -v`
Expected: PASS (3 теста).

- [ ] **Step 7: Удалить GeminiEmbedder и переключить DI**

Удалить файл `backend/app/infrastructure/ai/gemini_embedder.py`.

В [backend/app/api/deps.py](../../../backend/app/api/deps.py) заменить импорт и `get_embedder`:

```python
from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder
```
```python
@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return OpenRouterEmbedder(
        api_key=settings.openrouter_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
    )
```
Убрать строку `from app.infrastructure.ai.gemini_embedder import GeminiEmbedder`.

- [ ] **Step 8: Обновить .env.example и conftest**

В `backend/.env.example` заменить блок AI-ключей/параметров:

```
# AI ключи
GOOGLE_API_KEY=your-gemini-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
OPENROUTER_API_KEY=sk-or-...

# Параметры сопоставления и эмбеддинга
CONFIDENCE_THRESHOLD=0.90
EMBEDDING_BASE_URL=https://openrouter.ai/api/v1
EMBEDDING_MODEL=google/gemini-embedding-2
LLM_MODEL=claude-3-5-sonnet-20240620
```

В [backend/tests/conftest.py](../../../backend/tests/conftest.py) добавить строку после `ANTHROPIC_API_KEY`:

```python
os.environ.setdefault("OPENROUTER_API_KEY", "test")
```

- [ ] **Step 9: Добавить тест дефолтов конфига**

В `backend/tests/test_config.py` добавить:

```python
def test_embedding_defaults() -> None:
    settings = Settings(jwt_secret="x")  # type: ignore[call-arg]
    assert settings.embedding_model == "google/gemini-embedding-2"
    assert settings.embedding_base_url == "https://openrouter.ai/api/v1"
    assert settings.embedding_dim == 768
    assert settings.openrouter_api_key == ""
```

- [ ] **Step 10: Прогнать тесты и линт**

Run: `cd backend; uv run pytest tests/test_openrouter_embedder.py tests/test_config.py -v; uv run ruff check .`
Expected: все PASS, ruff чисто. (Тесты матчинга используют `FakeEmbedder`, на смену эмбеддера не реагируют.)

- [ ] **Step 11: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/.env.example backend/tests/conftest.py backend/app/infrastructure/ai/openrouter_embedder.py backend/app/api/deps.py backend/tests/test_openrouter_embedder.py backend/tests/test_config.py
git rm backend/app/infrastructure/ai/gemini_embedder.py
git commit -m "feat(embedder): gemini-embedding-2 via OpenRouter, retire GeminiEmbedder"
```

---

### Task 2: Приведение слоя данных к дереву (entity / ORM / миграция / репозиторий)

Сменa поля `section_name` на дерево — ломающее изменение типа `TemplateArticle`, поэтому все потребители правятся в одной задаче, чтобы оставить проект зелёным. Новых фич нет — только выравнивание под реальную схему (ревизия `0001`) + колонка `embedding_input`.

**Files:**
- Modify: `backend/app/domain/entities.py:25-33`
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/alembic/versions/0002_add_embedding_input.py`
- Modify: `backend/app/infrastructure/db/article_repository.py`
- Modify: `backend/app/domain/ports.py` (`ArticleRepository`: +`get_by_code`)
- Modify: `backend/app/services/article_service.py`
- Modify: `backend/app/api/deps.py:118-122` (`get_article_service` без эмбеддера)
- Modify: `backend/app/api/schemas.py` (DTO без `section_name`)
- Modify: `backend/app/api/routes/articles.py`
- Modify: `backend/app/infrastructure/ai/anthropic_matcher.py:36`
- Modify: `backend/tests/fakes.py` (`FakeRepository`: tree-shape, `get_by_code`)
- Modify: `backend/tests/test_api.py:25`, `backend/tests/test_matching_service.py:11`, `backend/tests/test_authz_matrix.py:61,72`

**Interfaces:**
- Produces: новый `TemplateArticle(article_code: str, name: str, embedding_input: str, parent_id: int | None = None, id: int | None = None, embedding: list[float] | None = None)`. Метод `ArticleRepository.get_by_code(code: str) -> TemplateArticle | None`. `ArticleService.create(article_code: str, name: str, parent_code: str | None = None) -> TemplateArticle`. `list_all` сортирует по коду численно. `search_similar` исключает строки с `embedding IS NULL`.

- [ ] **Step 1: Обновить доменную сущность**

В [backend/app/domain/entities.py](../../../backend/app/domain/entities.py) заменить класс `TemplateArticle`:

```python
@dataclass(frozen=True, slots=True)
class TemplateArticle:
    """Эталонная статья справочника СМР (узел дерева через parent_id)."""

    article_code: str
    name: str
    embedding_input: str
    parent_id: int | None = None
    id: int | None = None
    embedding: list[float] | None = None
```

- [ ] **Step 2: Обновить ORM-модель под реальную схему 0001 + embedding_input**

В [backend/app/infrastructure/db/models.py](../../../backend/app/infrastructure/db/models.py) заменить класс `TemplateArticleModel` и добавить `ForeignKey` в импорт из `sqlalchemy`:

```python
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
```
```python
class TemplateArticleModel(Base):
    __tablename__ = "template_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("template_articles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    article_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_input: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: Написать миграцию 0002**

Создать `backend/alembic/versions/0002_add_embedding_input.py`:

```python
"""add embedding_input to template_articles

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default='' нужен только чтобы пройти NOT NULL на возможных легаси-строках;
    # на практике таблица пуста. После добавления дефолт снимаем.
    op.add_column(
        "template_articles",
        sa.Column("embedding_input", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("template_articles", "embedding_input", server_default=None)


def downgrade() -> None:
    op.drop_column("template_articles", "embedding_input")
```

- [ ] **Step 4: Обновить репозиторий (маппинг, сортировка, фильтр NULL, get_by_code)**

Заменить содержимое [backend/app/infrastructure/db/article_repository.py](../../../backend/app/infrastructure/db/article_repository.py):

```python
"""Реализация ArticleRepository поверх PostgreSQL + pgvector.

Векторный поиск — косинусная дистанция `<=>`; similarity = 1 - distance (порог 0.90).
Сортировка списка — по коду численно (string_to_array(code,'.')::int[]), т.к. строковая
сортировка ломается на '1.10' vs '1.2'.
"""

from __future__ import annotations

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.ports import ArticleRepository
from app.infrastructure.db.models import TemplateArticleModel

_CODE_ORDER = cast(func.string_to_array(TemplateArticleModel.article_code, "."), ARRAY(Integer))


class SqlAlchemyArticleRepository(ArticleRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: TemplateArticleModel) -> TemplateArticle:
        return TemplateArticle(
            id=model.id,
            parent_id=model.parent_id,
            article_code=model.article_code,
            name=model.name,
            embedding_input=model.embedding_input,
            embedding=list(model.embedding) if model.embedding is not None else None,
        )

    def add(self, article: TemplateArticle) -> TemplateArticle:
        model = TemplateArticleModel(
            parent_id=article.parent_id,
            article_code=article.article_code,
            name=article.name,
            embedding_input=article.embedding_input,
            embedding=article.embedding,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def get_by_code(self, code: str) -> TemplateArticle | None:
        stmt = select(TemplateArticleModel).where(TemplateArticleModel.article_code == code)
        model = self._session.scalars(stmt).one_or_none()
        return self._to_entity(model) if model is not None else None

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        stmt = select(TemplateArticleModel).order_by(_CODE_ORDER).limit(limit).offset(offset)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def delete(self, article_id: int) -> None:
        model = self._session.get(TemplateArticleModel, article_id)
        if model is not None:
            self._session.delete(model)
            self._session.commit()

    def search_similar(self, embedding: list[float], top_k: int = 3) -> list[ArticleCandidate]:
        distance = TemplateArticleModel.embedding.cosine_distance(embedding)
        stmt = (
            select(TemplateArticleModel, distance.label("distance"))
            .where(TemplateArticleModel.embedding.is_not(None))
            .order_by(distance)
            .limit(top_k)
        )
        return [
            ArticleCandidate(article=self._to_entity(model), score=1.0 - float(dist))
            for model, dist in self._session.execute(stmt)
        ]
```

- [ ] **Step 5: Добавить get_by_code в порт ArticleRepository**

В [backend/app/domain/ports.py](../../../backend/app/domain/ports.py) в класс `ArticleRepository` добавить абстрактный метод (после `add`):

```python
    @abstractmethod
    def get_by_code(self, code: str) -> TemplateArticle | None: ...
```

- [ ] **Step 6: Адаптировать ArticleService под дерево (без эмбеддера)**

Заменить содержимое [backend/app/services/article_service.py](../../../backend/app/services/article_service.py):

```python
"""Сервис управления справочником. Эмбеддинг не делает — вектор заполнит воркер."""

from __future__ import annotations

from app.domain.entities import TemplateArticle
from app.domain.ports import ArticleRepository


class ArticleService:
    def __init__(self, repository: ArticleRepository) -> None:
        self._repository = repository

    def create(
        self, article_code: str, name: str, parent_code: str | None = None
    ) -> TemplateArticle:
        parent_id: int | None = None
        embedding_input = name
        if parent_code:
            parent = self._repository.get_by_code(parent_code)
            if parent is None:
                raise ValueError(f"Родитель с кодом {parent_code} не найден")
            parent_id = parent.id
            embedding_input = f"{parent.embedding_input}. {name}"
        article = TemplateArticle(
            article_code=article_code,
            name=name,
            embedding_input=embedding_input,
            parent_id=parent_id,
            embedding=None,
        )
        return self._repository.add(article)

    def list(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._repository.list_all(limit=limit, offset=offset)

    def delete(self, article_id: int) -> None:
        self._repository.delete(article_id)
```

- [ ] **Step 7: Убрать эмбеддер из get_article_service**

В [backend/app/api/deps.py](../../../backend/app/api/deps.py) заменить `get_article_service`:

```python
def get_article_service(
    repository: ArticleRepository = Depends(get_repository),
) -> ArticleService:
    return ArticleService(repository=repository)
```

- [ ] **Step 8: Обновить DTO (schemas.py) без section_name**

В [backend/app/api/schemas.py](../../../backend/app/api/schemas.py) заменить `ArticleCreate`, `ArticleOut`, `CandidateOut`:

```python
class ArticleCreate(BaseModel):
    # код — только числовые сегменты через точку: list_all сортирует через cast в int[],
    # нечисловой код уронил бы GET /api/articles (см. Task 7).
    article_code: str = Field(..., pattern=r"^\d+(\.\d+)*$", examples=["1.4.1"])
    name: str = Field(..., min_length=1, examples=["Мокап фасада"])
    parent_code: str | None = Field(default=None, pattern=r"^\d+(\.\d+)*$", examples=["1.4"])


class ArticleOut(BaseModel):
    id: int
    article_code: str
    name: str
    parent_id: int | None

    @classmethod
    def from_entity(cls, entity: TemplateArticle) -> ArticleOut:
        return cls(
            id=entity.id or 0,
            article_code=entity.article_code,
            name=entity.name,
            parent_id=entity.parent_id,
        )


class CandidateOut(BaseModel):
    article_code: str
    name: str
    score: float
```

И в `MatchResultOut.from_entity` убрать `section_name=...` из конструкции `CandidateOut` (оставить `article_code`, `name`, `score`).

- [ ] **Step 9: Обновить роуты статей (create под parent_code, поднять дефолт limit)**

В [backend/app/api/routes/articles.py](../../../backend/app/api/routes/articles.py) в `create_article` заменить тело:

```python
    article = service.create(
        article_code=payload.article_code,
        name=payload.name,
        parent_code=payload.parent_code,
    )
    return ArticleOut.from_entity(article)
```

И поднять дефолтный `limit` в `list_articles`, чтобы дерево (362 строки) не обрезалось при просмотре справочника целиком:

```python
@router.get("", response_model=list[ArticleOut])
def list_articles(
    limit: int = 1000,
    offset: int = 0,
    service: ArticleService = Depends(get_article_service),
) -> list[ArticleOut]:
    return [ArticleOut.from_entity(a) for a in service.list(limit=limit, offset=offset)]
```

- [ ] **Step 10: Поправить листинг кандидатов в anthropic_matcher**

В [backend/app/infrastructure/ai/anthropic_matcher.py:36](../../../backend/app/infrastructure/ai/anthropic_matcher.py#L36) заменить строку формирования listing:

```python
            f"{i + 1}. [{c.article.article_code}] {c.article.name}"
```

- [ ] **Step 11: Обновить фейки и существующие тесты**

В [backend/tests/fakes.py](../../../backend/tests/fakes.py) заменить `FakeRepository`:

```python
class FakeRepository(ArticleRepository):
    def __init__(self, candidates: list[ArticleCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self._store: list[TemplateArticle] = []

    def add(self, article: TemplateArticle) -> TemplateArticle:
        stored = TemplateArticle(
            id=len(self._store) + 1,
            parent_id=article.parent_id,
            article_code=article.article_code,
            name=article.name,
            embedding_input=article.embedding_input,
            embedding=article.embedding,
        )
        self._store.append(stored)
        return stored

    def get_by_code(self, code: str) -> TemplateArticle | None:
        return next((a for a in self._store if a.article_code == code), None)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._store[offset : offset + limit]

    def delete(self, article_id: int) -> None:
        self._store = [a for a in self._store if a.id != article_id]

    def search_similar(self, embedding: list[float], top_k: int = 3) -> list[ArticleCandidate]:
        return self._candidates[:top_k]
```

В [backend/tests/test_api.py:25](../../../backend/tests/test_api.py#L25) заменить конструкцию статьи:

```python
            article=TemplateArticle(
                id=1, article_code="A", name="Фундамент", embedding_input="Бетон. Фундамент"
            ),
```

В [backend/tests/test_matching_service.py:11](../../../backend/tests/test_matching_service.py#L11) заменить фабрику:

```python
    return TemplateArticle(
        id=1, article_code=code, name=f"Работа {code}", embedding_input=f"Раздел. Работа {code}"
    )
```

В [backend/tests/test_authz_matrix.py](../../../backend/tests/test_authz_matrix.py) в обоих местах (строки ~61 и ~72) заменить тело запроса:

```python
        json={"article_code": "X", "name": "n"},
```

- [ ] **Step 12: Прогнать весь набор тестов и линт**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: все PASS (старые тесты зелёные на новой модели), ruff чисто.

- [ ] **Step 13: Commit**

```bash
git add backend/app/domain/entities.py backend/app/infrastructure/db/models.py backend/alembic/versions/0002_add_embedding_input.py backend/app/infrastructure/db/article_repository.py backend/app/domain/ports.py backend/app/services/article_service.py backend/app/api/deps.py backend/app/api/schemas.py backend/app/api/routes/articles.py backend/app/infrastructure/ai/anthropic_matcher.py backend/tests/fakes.py backend/tests/test_api.py backend/tests/test_matching_service.py backend/tests/test_authz_matrix.py
git commit -m "refactor(domain): template_articles как дерево (parent_id, embedding_input), убрать section_name"
```

---

### Task 3: TemplateParser — парсинг и санитайзинг файла-шаблона

**Files:**
- Modify: `backend/app/domain/errors.py` (+`TemplateValidationError`)
- Create: `backend/app/services/template_parser.py`
- Test: `backend/tests/test_template_parser.py`

**Interfaces:**
- Produces: `ParsedTemplateRow(article_code: str, name: str, parent_code: str | None, embedding_input: str)`; `ParseResult(rows: list[ParsedTemplateRow], skipped: list[str])`; `TemplateParser().parse(content: bytes) -> ParseResult`. Исключение `TemplateValidationError` (дубликат кода в файле / сирота-родитель).

- [ ] **Step 1: Добавить доменное исключение**

В [backend/app/domain/errors.py](../../../backend/app/domain/errors.py) добавить:

```python
class TemplateValidationError(Exception):
    """Файл-шаблон структурно некорректен (дубликат кода, сирота-родитель)."""
```

- [ ] **Step 2: Написать падающие тесты парсера**

Создать `backend/tests/test_template_parser.py`:

```python
from __future__ import annotations

import io

import pandas as pd
import pytest

from app.domain.errors import TemplateValidationError
from app.services.template_parser import TemplateParser


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _by_code(result) -> dict:
    return {r.article_code: r for r in result.rows}


def test_parses_codes_names_parents_and_enriched_text() -> None:
    result = TemplateParser().parse(
        _xlsx(
            [
                "(1.) Подготовительные работы",
                "(1.4.) Мокап",
                "(1.4.1.) Мокап фасада",
            ]
        )
    )
    rows = _by_code(result)

    assert set(rows) == {"1", "1.4", "1.4.1"}
    assert rows["1"].parent_code is None
    assert rows["1.4"].parent_code == "1"
    assert rows["1.4.1"].parent_code == "1.4"
    assert rows["1.4.1"].name == "Мокап фасада"
    assert (
        rows["1.4.1"].embedding_input == "Подготовительные работы. Мокап. Мокап фасада"
    )
    assert result.skipped == []


def test_recovers_code_with_inner_space() -> None:
    # (6.6 .) -> 6.6, не отбрасывается
    result = TemplateParser().parse(_xlsx(["(6.) Фасады", "(6.6 .) Система обслуживания фасадов"]))
    rows = _by_code(result)
    assert "6.6" in rows
    assert rows["6.6"].parent_code == "6"
    assert result.skipped == []


def test_sanitizes_name_whitespace() -> None:
    result = TemplateParser().parse(_xlsx(["(2.)   Котлован   работы тут "]))
    assert result.rows[0].name == "Котлован работы тут"


def test_skips_unparseable_and_empty_name_rows() -> None:
    result = TemplateParser().parse(
        _xlsx(["(1.) Раздел", "просто текст без кода", "(1.1.)   "])
    )
    assert [r.article_code for r in result.rows] == ["1"]
    assert len(result.skipped) == 2


def test_skips_non_numeric_code_segment() -> None:
    result = TemplateParser().parse(_xlsx(["(1.) Раздел", "(1.x.) Кривой код"]))
    assert [r.article_code for r in result.rows] == ["1"]
    assert result.skipped == ["(1.x.) Кривой код"]


def test_duplicate_code_raises() -> None:
    with pytest.raises(TemplateValidationError):
        TemplateParser().parse(_xlsx(["(1.) Раздел", "(1.) Дубль"]))


def test_orphan_parent_raises() -> None:
    with pytest.raises(TemplateValidationError):
        TemplateParser().parse(_xlsx(["(1.) Раздел", "(2.5.) Без родителя 2"]))
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_template_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.template_parser`.

- [ ] **Step 4: Реализовать TemplateParser**

Создать `backend/app/services/template_parser.py`:

```python
"""Парсер файла-шаблона справочника СМР.

Формат: один столбец, строки '(КОД) Наименование'. Иерархия закодирована в коде
('1' -> '1.4' -> '1.4.1'). Санитайзинг кода: убрать внутренние пробелы и хвостовую точку
(восстанавливает грязь вида '(6.6 .)'); сегменты обязаны быть числовыми. embedding_input —
имена всех предков от корня + собственное, через '. '.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd

from app.domain.errors import TemplateValidationError

_LINE = re.compile(r"^\((.*?)\)\s*(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ParsedTemplateRow:
    article_code: str
    name: str
    parent_code: str | None
    embedding_input: str


@dataclass(frozen=True, slots=True)
class ParseResult:
    rows: list[ParsedTemplateRow]
    skipped: list[str]


class TemplateParser:
    def parse(self, content: bytes) -> ParseResult:
        df = pd.read_excel(io.BytesIO(content), header=None, engine="openpyxl")
        series = df.iloc[:, 0].dropna().astype(str) if not df.empty else []

        skipped: list[str] = []
        name_by_code: dict[str, str] = {}
        order: list[str] = []

        for raw in series:
            cell = raw.strip()
            match = _LINE.match(cell)
            if match is None:
                skipped.append(cell)
                continue
            code = re.sub(r"\s+", "", match.group(1)).strip(".")
            name = re.sub(r"\s+", " ", match.group(2)).strip()
            if not name or not code:
                skipped.append(cell)
                continue
            if not all(seg.isdigit() for seg in code.split(".")):
                skipped.append(cell)
                continue
            if code in name_by_code:
                raise TemplateValidationError(f"Дубликат кода в файле: {code}")
            name_by_code[code] = name
            order.append(code)

        rows = [self._build_row(code, name_by_code) for code in order]
        return ParseResult(rows=rows, skipped=skipped)

    @staticmethod
    def _build_row(code: str, name_by_code: dict[str, str]) -> ParsedTemplateRow:
        segments = code.split(".")
        parent_code = ".".join(segments[:-1]) or None
        if parent_code is not None and parent_code not in name_by_code:
            raise TemplateValidationError(f"Сирота: у кода {code} нет родителя {parent_code}")
        ancestors = [".".join(segments[:i]) for i in range(1, len(segments) + 1)]
        embedding_input = ". ".join(name_by_code[a] for a in ancestors)
        return ParsedTemplateRow(
            article_code=code,
            name=name_by_code[code],
            parent_code=parent_code,
            embedding_input=embedding_input,
        )
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_template_parser.py -v`
Expected: PASS (7 тестов).

- [ ] **Step 6: Линт и commit**

```bash
cd backend; uv run ruff check .
```
```bash
git add backend/app/domain/errors.py backend/app/services/template_parser.py backend/tests/test_template_parser.py
git commit -m "feat(parser): TemplateParser — парсинг и санитайзинг файла-шаблона"
```

---

### Task 4: Чистая логика плана импорта — compute_plan + requires_force

**Files:**
- Modify: `backend/app/domain/entities.py` (+ dataclasses плана)
- Modify: `backend/app/domain/errors.py` (+`DeletionGuardError`)
- Create: `backend/app/services/import_planning.py`
- Test: `backend/tests/test_import_planning.py`

**Interfaces:**
- Produces (в `domain/entities.py`): `ExistingArticle(id: int, article_code: str, embedding_input: str)`; `PlannedInsert(article_code, name, parent_code, embedding_input)`; `PlannedUpdate(id, article_code, name, parent_code, embedding_input, invalidate_embedding)`; `ImportPlan(inserts, updates, delete_ids, delete_codes, unchanged)`; `ImportReport(created, updated, deleted, unchanged, skipped, pending_embeddings, dry_run, force_required)`.
- Produces (в `services/import_planning.py`): `compute_plan(parsed: list[ParsedTemplateRow], existing: list[ExistingArticle]) -> ImportPlan`; `requires_force(plan: ImportPlan, existing_total: int, *, fraction_limit: float = 0.20) -> bool`.

- [ ] **Step 1: Добавить dataclasses плана в domain/entities.py**

В [backend/app/domain/entities.py](../../../backend/app/domain/entities.py) добавить в конец файла:

```python
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
```

- [ ] **Step 2: Добавить DeletionGuardError**

В [backend/app/domain/errors.py](../../../backend/app/domain/errors.py) добавить:

```python
class DeletionGuardError(Exception):
    """Импорт удалил бы слишком много (порог) без явного force."""

    def __init__(self, deleted: int, roots_deleted: int) -> None:
        self.deleted = deleted
        self.roots_deleted = roots_deleted
        super().__init__(
            f"Импорт удалит {deleted} строк (из них корней: {roots_deleted}). "
            "Повторите с force=true, если это намеренно."
        )
```

- [ ] **Step 3: Написать падающие тесты планировщика**

Создать `backend/tests/test_import_planning.py`:

```python
from __future__ import annotations

from app.domain.entities import ExistingArticle
from app.services.import_planning import compute_plan, requires_force
from app.services.template_parser import ParsedTemplateRow


def _p(code: str, name: str, parent: str | None, ei: str) -> ParsedTemplateRow:
    return ParsedTemplateRow(article_code=code, name=name, parent_code=parent, embedding_input=ei)


def test_insert_all_when_db_empty() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    plan = compute_plan(parsed, [])
    assert len(plan.inserts) == 1
    assert plan.updates == []
    assert plan.delete_ids == []
    assert plan.unchanged == 0


def test_unchanged_keeps_embedding() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    existing = [ExistingArticle(id=10, article_code="1", embedding_input="Раздел")]
    plan = compute_plan(parsed, existing)
    assert plan.inserts == []
    assert plan.updates == []
    assert plan.unchanged == 1


def test_update_invalidates_when_embedding_input_changed() -> None:
    parsed = [_p("1.1", "Новое имя", "1", "Раздел. Новое имя")]
    existing = [ExistingArticle(id=5, article_code="1.1", embedding_input="Раздел. Старое имя")]
    plan = compute_plan(parsed, existing)
    assert len(plan.updates) == 1
    assert plan.updates[0].invalidate_embedding is True
    assert plan.updates[0].id == 5


def test_delete_collects_missing_codes() -> None:
    parsed = [_p("1", "Раздел", None, "Раздел")]
    existing = [
        ExistingArticle(id=1, article_code="1", embedding_input="Раздел"),
        ExistingArticle(id=2, article_code="9", embedding_input="Удалить"),
    ]
    plan = compute_plan(parsed, existing)
    assert plan.delete_ids == [2]
    assert plan.delete_codes == ["9"]


def test_requires_force_on_root_deletion() -> None:
    plan = compute_plan(
        [],  # пустой файл -> всё существующее удаляется
        [ExistingArticle(id=1, article_code="1", embedding_input="Раздел верхнего уровня")],
    )
    # удаляется корневой узел "1"
    assert plan.delete_codes == ["1"]
    assert requires_force(plan, existing_total=1) is True


def test_no_force_for_first_import() -> None:
    plan = compute_plan([_p("1", "Раздел", None, "Раздел")], [])
    assert requires_force(plan, existing_total=0) is False


def test_no_force_for_small_leaf_deletion() -> None:
    existing = [ExistingArticle(id=i, article_code=f"1.{i}", embedding_input="x") for i in range(1, 11)]
    parsed = [_p(f"1.{i}", "x", "1", "x") for i in range(1, 10)]  # удаляем 1 из 10 листьев
    plan = compute_plan(parsed, existing)
    assert plan.delete_codes == ["1.10"]
    assert requires_force(plan, existing_total=10) is False
```

- [ ] **Step 4: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_import_planning.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.import_planning`.

- [ ] **Step 5: Реализовать compute_plan / requires_force**

Создать `backend/app/services/import_planning.py`:

```python
"""Чистая логика дельты импорта: insert/update/delete + инвалидация + порог force.

Файл трактуется как полное желаемое состояние (full-replace-by-diff). Удаление защищено
требованием force при сносе корня или большой доли строк (см. requires_force).
"""

from __future__ import annotations

from app.domain.entities import (
    ExistingArticle,
    ImportPlan,
    PlannedInsert,
    PlannedUpdate,
)
from app.services.template_parser import ParsedTemplateRow


def compute_plan(
    parsed: list[ParsedTemplateRow], existing: list[ExistingArticle]
) -> ImportPlan:
    existing_by_code = {e.article_code: e for e in existing}
    parsed_codes = {r.article_code for r in parsed}

    inserts: list[PlannedInsert] = []
    updates: list[PlannedUpdate] = []
    unchanged = 0

    for row in parsed:
        current = existing_by_code.get(row.article_code)
        if current is None:
            inserts.append(
                PlannedInsert(
                    article_code=row.article_code,
                    name=row.name,
                    parent_code=row.parent_code,
                    embedding_input=row.embedding_input,
                )
            )
            continue
        if current.embedding_input == row.embedding_input:
            unchanged += 1
            continue
        updates.append(
            PlannedUpdate(
                id=current.id,
                article_code=row.article_code,
                name=row.name,
                parent_code=row.parent_code,
                embedding_input=row.embedding_input,
                invalidate_embedding=True,
            )
        )

    deletions = [e for e in existing if e.article_code not in parsed_codes]
    return ImportPlan(
        inserts=inserts,
        updates=updates,
        delete_ids=[e.id for e in deletions],
        delete_codes=[e.article_code for e in deletions],
        unchanged=unchanged,
    )


def requires_force(
    plan: ImportPlan, existing_total: int, *, fraction_limit: float = 0.20
) -> bool:
    if existing_total == 0:
        return False
    roots_deleted = sum(1 for code in plan.delete_codes if "." not in code)
    if roots_deleted >= 1:
        return True
    return len(plan.delete_ids) > fraction_limit * existing_total
```

Примечание: `invalidate_embedding` всегда `True` в `updates`, потому что в `updates` попадают только строки с изменившимся `embedding_input` (неизменившиеся идут в `unchanged`). Поле оставлено явным для читаемости плана и на случай будущих частичных обновлений.

- [ ] **Step 6: Запустить тесты — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_import_planning.py -v`
Expected: PASS (7 тестов).

- [ ] **Step 7: Линт и commit**

```bash
cd backend; uv run ruff check .
```
```bash
git add backend/app/domain/entities.py backend/app/domain/errors.py backend/app/services/import_planning.py backend/tests/test_import_planning.py
git commit -m "feat(ingest): чистая логика плана импорта (compute_plan, requires_force)"
```

---

### Task 5: ArticleImportRepository + TemplateIngestService.import_template

**Files:**
- Modify: `backend/app/domain/ports.py` (+`ArticleImportRepository`)
- Create: `backend/app/infrastructure/db/import_repository.py`
- Create: `backend/app/services/template_ingest_service.py`
- Modify: `backend/tests/fakes.py` (+`FakeImportRepository`)
- Test: `backend/tests/test_template_ingest_service.py`

**Interfaces:**
- Consumes: `TemplateParser.parse`, `compute_plan`, `requires_force`, `ImportPlan`, `ImportReport`, `ExistingArticle`, `DeletionGuardError`, `TemplateValidationError`.
- Produces: порт `ArticleImportRepository` с `load_existing() -> list[ExistingArticle]` и `apply_plan(plan: ImportPlan) -> None`. `TemplateIngestService(parser: TemplateParser, repository: ArticleImportRepository)` с `import_template(content: bytes, *, dry_run: bool = False, force: bool = False) -> ImportReport`.

- [ ] **Step 1: Объявить порт ArticleImportRepository**

В [backend/app/domain/ports.py](../../../backend/app/domain/ports.py): расширить импорт сущностей и добавить класс.

```python
from app.domain.entities import (
    ArticleCandidate,
    ExistingArticle,
    ImportPlan,
    TemplateArticle,
    TokenPayload,
    User,
)
```
```python
class ArticleImportRepository(ABC):
    """Снимок справочника и атомарное применение плана импорта."""

    @abstractmethod
    def load_existing(self) -> list[ExistingArticle]: ...

    @abstractmethod
    def apply_plan(self, plan: ImportPlan) -> None: ...
```

- [ ] **Step 2: Написать падающие тесты сервиса импорта**

Создать `backend/tests/test_template_ingest_service.py`:

```python
from __future__ import annotations

import io

import pandas as pd
import pytest

from app.domain.errors import DeletionGuardError, TemplateValidationError
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser
from tests.fakes import FakeImportRepository


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _service(repo: FakeImportRepository) -> TemplateIngestService:
    return TemplateIngestService(parser=TemplateParser(), repository=repo)


def test_first_import_creates_all_pending() -> None:
    repo = FakeImportRepository()
    report = _service(repo).import_template(_xlsx(["(1.) Раздел", "(1.1.) Под"]))
    assert report.created == 2
    assert report.deleted == 0
    assert report.pending_embeddings == 2
    assert {a.article_code for a in repo.rows.values()} == {"1", "1.1"}


def test_reimport_unchanged_keeps_embedding() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел"]))
    repo.set_embedding("1", [0.1, 0.2, 0.3])  # эмулируем работу воркера
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]))
    assert report.unchanged == 1
    assert repo.get("1").embedding == [0.1, 0.2, 0.3]


def test_ancestor_rename_invalidates_descendant() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Старое", "(1.1.) Лист"]))
    repo.set_embedding("1.1", [9.0])
    report = _service(repo).import_template(_xlsx(["(1.) Новое", "(1.1.) Лист"]))
    # корень "1" (сменил имя) + потомок "1.1" (его embedding_input изменился из-за предка)
    assert report.updated == 2
    assert repo.get("1.1").embedding is None


def test_dry_run_writes_nothing() -> None:
    repo = FakeImportRepository()
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), dry_run=True)
    assert report.dry_run is True
    assert report.created == 1
    assert report.force_required is False
    assert repo.rows == {}


def test_dry_run_flags_force_required_without_writing() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    # dry-run импорта, который снёс бы корень "2": предупреждаем, но не пишем и не бросаем
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), dry_run=True)
    assert report.dry_run is True
    assert report.deleted == 1
    assert report.force_required is True
    assert {a.article_code for a in repo.rows.values()} == {"1", "2"}  # ничего не удалено


def test_root_deletion_requires_force() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    with pytest.raises(DeletionGuardError):
        _service(repo).import_template(_xlsx(["(1.) Раздел"]))  # сносит корень "2"


def test_root_deletion_with_force_applies() -> None:
    repo = FakeImportRepository()
    _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.) Второй"]))
    report = _service(repo).import_template(_xlsx(["(1.) Раздел"]), force=True)
    assert report.deleted == 1
    assert set(c for c in (r.article_code for r in repo.rows.values())) == {"1"}


def test_orphan_file_raises() -> None:
    repo = FakeImportRepository()
    with pytest.raises(TemplateValidationError):
        _service(repo).import_template(_xlsx(["(1.) Раздел", "(2.5.) Сирота"]))
```

- [ ] **Step 3: Добавить FakeImportRepository в fakes.py**

В [backend/tests/fakes.py](../../../backend/tests/fakes.py) добавить (и расширить импорт `from app.domain.entities import ...` именами `ExistingArticle`, `ImportPlan`):

```python
class FakeImportRepository(ArticleImportRepository):
    """In-memory справочник для тестов сервиса импорта.

    rows: code -> TemplateArticle (с id, embedding, embedding_input, parent_id).
    """

    def __init__(self) -> None:
        self.rows: dict[str, TemplateArticle] = {}
        self._next_id = 1

    def load_existing(self) -> list[ExistingArticle]:
        return [
            ExistingArticle(id=a.id, article_code=a.article_code, embedding_input=a.embedding_input)
            for a in self.rows.values()
        ]

    def apply_plan(self, plan: ImportPlan) -> None:
        for code in plan.delete_codes:
            self.rows.pop(code, None)
        for ins in plan.inserts:
            self.rows[ins.article_code] = TemplateArticle(
                id=self._next_id,
                parent_id=None,
                article_code=ins.article_code,
                name=ins.name,
                embedding_input=ins.embedding_input,
                embedding=None,
            )
            self._next_id += 1
        for upd in plan.updates:
            self.rows[upd.article_code] = TemplateArticle(
                id=upd.id,
                parent_id=None,
                article_code=upd.article_code,
                name=upd.name,
                embedding_input=upd.embedding_input,
                embedding=None if upd.invalidate_embedding else self.rows[upd.article_code].embedding,
            )

    # помощники для тестов
    def set_embedding(self, code: str, vector: list[float]) -> None:
        a = self.rows[code]
        self.rows[code] = TemplateArticle(
            id=a.id,
            parent_id=a.parent_id,
            article_code=a.article_code,
            name=a.name,
            embedding_input=a.embedding_input,
            embedding=vector,
        )

    def get(self, code: str) -> TemplateArticle:
        return self.rows[code]
```
Добавить `ArticleImportRepository` в импорт портов в начале `fakes.py`:
```python
from app.domain.ports import (
    ArticleImportRepository,
    ArticleRepository,
    Embedder,
    LLMMatcher,
    PasswordHasher,
    TokenService,
    UserRepository,
)
```

- [ ] **Step 4: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_template_ingest_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.template_ingest_service`.

- [ ] **Step 5: Реализовать TemplateIngestService**

Создать `backend/app/services/template_ingest_service.py`:

```python
"""Сценарий импорта справочника: parse -> compute_plan -> (guard) -> apply_plan -> отчёт."""

from __future__ import annotations

from app.domain.entities import ImportPlan, ImportReport
from app.domain.errors import DeletionGuardError
from app.domain.ports import ArticleImportRepository
from app.services.import_planning import compute_plan, requires_force
from app.services.template_parser import ParseResult, TemplateParser


class TemplateIngestService:
    def __init__(self, parser: TemplateParser, repository: ArticleImportRepository) -> None:
        self._parser = parser
        self._repository = repository

    def import_template(
        self, content: bytes, *, dry_run: bool = False, force: bool = False
    ) -> ImportReport:
        parsed: ParseResult = self._parser.parse(content)  # бросает TemplateValidationError
        existing = self._repository.load_existing()
        plan = compute_plan(parsed.rows, existing)
        needs_force = requires_force(plan, existing_total=len(existing))

        # force_required считаем всегда — чтобы dry-run честно предупреждал о боевом 409.
        report = self._report(plan, parsed, dry_run=dry_run, force_required=needs_force)
        if dry_run:
            return report

        if needs_force and not force:
            roots = sum(1 for code in plan.delete_codes if "." not in code)
            raise DeletionGuardError(deleted=len(plan.delete_ids), roots_deleted=roots)

        self._repository.apply_plan(plan)
        return report

    @staticmethod
    def _report(
        plan: ImportPlan, parsed: ParseResult, *, dry_run: bool, force_required: bool
    ) -> ImportReport:
        pending = len(plan.inserts) + len(plan.updates)
        return ImportReport(
            created=len(plan.inserts),
            updated=len(plan.updates),
            deleted=len(plan.delete_ids),
            unchanged=plan.unchanged,
            skipped=list(parsed.skipped),
            pending_embeddings=pending,
            dry_run=dry_run,
            force_required=force_required,
        )
```

- [ ] **Step 6: Запустить тесты сервиса — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_template_ingest_service.py -v`
Expected: PASS (7 тестов).

- [ ] **Step 7: Реализовать SQL-адаптер ArticleImportRepository**

Создать `backend/app/infrastructure/db/import_repository.py`:

```python
"""SQL-реализация ArticleImportRepository: снимок + атомарное применение плана импорта.

apply_plan — две фазы резолва parent_id: сначала пишем строки с parent_id=NULL, затем по
карте code->id проставляем parent_id (порядок вставки не важен). Всё в одной транзакции.
"""

from __future__ import annotations

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domain.entities import ExistingArticle, ImportPlan
from app.domain.ports import ArticleImportRepository
from app.infrastructure.db.models import TemplateArticleModel


class SqlAlchemyArticleImportRepository(ArticleImportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def load_existing(self) -> list[ExistingArticle]:
        stmt = select(
            TemplateArticleModel.id,
            TemplateArticleModel.article_code,
            TemplateArticleModel.embedding_input,
        )
        return [
            ExistingArticle(id=row.id, article_code=row.article_code, embedding_input=row.embedding_input)
            for row in self._session.execute(stmt)
        ]

    def apply_plan(self, plan: ImportPlan) -> None:
        try:
            if plan.delete_ids:
                self._session.execute(
                    delete(TemplateArticleModel).where(TemplateArticleModel.id.in_(plan.delete_ids))
                )
            for ins in plan.inserts:
                self._session.add(
                    TemplateArticleModel(
                        parent_id=None,
                        article_code=ins.article_code,
                        name=ins.name,
                        embedding_input=ins.embedding_input,
                        embedding=None,
                    )
                )
            for upd in plan.updates:
                values: dict = {"name": upd.name, "embedding_input": upd.embedding_input}
                if upd.invalidate_embedding:
                    values["embedding"] = None
                self._session.execute(
                    update(TemplateArticleModel)
                    .where(TemplateArticleModel.id == upd.id)
                    .values(**values)
                )
            self._session.flush()

            id_by_code = {
                code: _id
                for _id, code in self._session.execute(
                    select(TemplateArticleModel.id, TemplateArticleModel.article_code)
                )
            }
            for ins in plan.inserts:
                if ins.parent_code:
                    self._session.execute(
                        update(TemplateArticleModel)
                        .where(TemplateArticleModel.article_code == ins.article_code)
                        .values(parent_id=id_by_code.get(ins.parent_code))
                    )
            for upd in plan.updates:
                self._session.execute(
                    update(TemplateArticleModel)
                    .where(TemplateArticleModel.id == upd.id)
                    .values(parent_id=id_by_code.get(upd.parent_code) if upd.parent_code else None)
                )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
```

> **Примечание (производительность, не блокер):** на первом импорте это ~362 INSERT + ~362 UPDATE (резолв `parent_id`) в одной транзакции; к облачному Neon с per-statement round-trip это может занять секунды. Для разовой админ-операции приемлемо. Если импорт окажется заметно медленным — оптимизировать резолв `parent_id` (один UPDATE…FROM по карте кодов вместо построчного).

- [ ] **Step 8: Прогнать весь набор тестов и линт**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: все PASS, ruff чисто. (SQL-адаптер `import_repository.py` проверяется end-to-end в Task 9.)

- [ ] **Step 9: Commit**

```bash
git add backend/app/domain/ports.py backend/app/infrastructure/db/import_repository.py backend/app/services/template_ingest_service.py backend/tests/fakes.py backend/tests/test_template_ingest_service.py
git commit -m "feat(ingest): TemplateIngestService + ArticleImportRepository (snapshot/apply_plan)"
```

---

### Task 6: API-эндпоинт POST /api/articles/import

**Files:**
- Modify: `backend/app/api/schemas.py` (+`ImportReportOut`)
- Modify: `backend/app/api/deps.py` (+`get_import_repository`, +`get_template_ingest_service`)
- Modify: `backend/app/api/routes/articles.py` (+роут import)
- Test: `backend/tests/test_import_endpoint.py`

**Interfaces:**
- Consumes: `TemplateIngestService.import_template`, `DeletionGuardError`, `TemplateValidationError`, `SqlAlchemyArticleImportRepository`, `TemplateParser`, `require_admin`.
- Produces: `POST /api/articles/import` (multipart `file`, query `dry_run: bool`, `force: bool`), ответ `ImportReportOut`. DI: `get_template_ingest_service() -> TemplateIngestService`.

- [ ] **Step 1: Добавить DTO ImportReportOut**

В [backend/app/api/schemas.py](../../../backend/app/api/schemas.py) добавить (импортнуть `ImportReport` из entities):

```python
class ImportReportOut(BaseModel):
    created: int
    updated: int
    deleted: int
    unchanged: int
    skipped: list[str]
    pending_embeddings: int
    dry_run: bool
    force_required: bool

    @classmethod
    def from_entity(cls, report: ImportReport) -> ImportReportOut:
        return cls(
            created=report.created,
            updated=report.updated,
            deleted=report.deleted,
            unchanged=report.unchanged,
            skipped=report.skipped,
            pending_embeddings=report.pending_embeddings,
            dry_run=report.dry_run,
            force_required=report.force_required,
        )
```

- [ ] **Step 2: Добавить DI в deps.py**

В [backend/app/api/deps.py](../../../backend/app/api/deps.py) добавить импорты и провайдеры:

```python
from app.domain.ports import ArticleImportRepository
from app.infrastructure.db.import_repository import SqlAlchemyArticleImportRepository
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser
```
```python
def get_import_repository(
    session: Session = Depends(get_session),
) -> ArticleImportRepository:
    return SqlAlchemyArticleImportRepository(session)


def get_template_ingest_service(
    repository: ArticleImportRepository = Depends(get_import_repository),
) -> TemplateIngestService:
    return TemplateIngestService(parser=TemplateParser(), repository=repository)
```

- [ ] **Step 3: Написать падающие тесты эндпоинта**

Создать `backend/tests/test_import_endpoint.py`:

```python
from __future__ import annotations

import io

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_template_ingest_service
from app.domain.entities import Role, User
from app.main import app
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser
from tests.fakes import FakeImportRepository

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _admin() -> User:
    return User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)


def _user() -> User:
    return User(id=2, email="user@mr.kz", password_hash="h", role=Role.USER)


def _service_factory(repo: FakeImportRepository):
    def _factory() -> TemplateIngestService:
        return TemplateIngestService(parser=TemplateParser(), repository=repo)

    return _factory


def test_import_creates_and_reports() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел", "(1.1.) Под"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["pending_embeddings"] == 2
    assert body["dry_run"] is False


def test_import_root_deletion_returns_409() -> None:
    repo = FakeImportRepository()
    TemplateIngestService(parser=TemplateParser(), repository=repo).import_template(
        _xlsx(["(1.) Раздел", "(2.) Второй"])
    )
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["detail"]["force_required"] is True


def test_import_invalid_file_returns_400() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел", "(1.) Дубль"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 400


def test_import_requires_admin() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
```

- [ ] **Step 4: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_import_endpoint.py -v`
Expected: FAIL — роут `/api/articles/import` отсутствует (404), тесты не проходят.

- [ ] **Step 5: Реализовать роут import**

В [backend/app/api/routes/articles.py](../../../backend/app/api/routes/articles.py) добавить импорты и роут:

```python
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import (
    get_article_service,
    get_current_user,
    get_template_ingest_service,
    require_admin,
)
from app.api.schemas import ArticleCreate, ArticleOut, ImportReportOut
from app.domain.errors import DeletionGuardError, TemplateValidationError
from app.services.article_service import ArticleService
from app.services.template_ingest_service import TemplateIngestService
```
```python
@router.post("/import", response_model=ImportReportOut, dependencies=[Depends(require_admin)])
async def import_template(
    file: UploadFile = File(...),
    dry_run: bool = False,
    force: bool = False,
    service: TemplateIngestService = Depends(get_template_ingest_service),
) -> ImportReportOut:
    content = await file.read()
    try:
        report = service.import_template(content, dry_run=dry_run, force=force)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DeletionGuardError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "force_required": True, "deleted": exc.deleted},
        ) from exc
    return ImportReportOut.from_entity(report)
```

- [ ] **Step 6: Запустить тесты эндпоинта — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_import_endpoint.py -v`
Expected: PASS (4 теста).

- [ ] **Step 7: Прогнать весь набор + линт, commit**

```bash
cd backend; uv run pytest; uv run ruff check .
```
```bash
git add backend/app/api/schemas.py backend/app/api/deps.py backend/app/api/routes/articles.py backend/tests/test_import_endpoint.py
git commit -m "feat(api): POST /api/articles/import (dry_run/force, 400/409, admin)"
```

---

### Task 7: Защита ручного POST /api/articles (guard на узел-предок и дубликат)

**Files:**
- Modify: `backend/app/domain/ports.py` (`ArticleRepository`: +`has_descendant_codes`)
- Modify: `backend/app/infrastructure/db/article_repository.py` (+`has_descendant_codes`)
- Modify: `backend/app/services/article_service.py` (guard'ы)
- Modify: `backend/app/api/routes/articles.py` (`create_article`: 400/409)
- Modify: `backend/tests/fakes.py` (`FakeRepository.has_descendant_codes`)
- Test: `backend/tests/test_article_service.py`, `backend/tests/test_authz_matrix.py` (расширить)

**Interfaces:**
- Produces: `ArticleRepository.has_descendant_codes(code: str) -> bool` (есть ли строки с `article_code LIKE code || '.%'`). `ArticleService.create` бросает `TemplateValidationError`, если код стал бы предком существующих узлов или содержит нечисловой сегмент, и `DuplicateError`, если код уже есть.

> **Примечание:** `DuplicateError` УЖЕ существует в [backend/app/domain/errors.py:10](../../../backend/app/domain/errors.py#L10) (заведён в auth-слое). Новый шаг для него не нужен — только импортировать. `TemplateValidationError` добавлен в Task 3, отдельный код не требуется.

- [ ] **Step 1: Написать падающие тесты сервиса create**

Создать `backend/tests/test_article_service.py`:

```python
from __future__ import annotations

import pytest

from app.domain.errors import DuplicateError, TemplateValidationError
from app.services.article_service import ArticleService
from tests.fakes import FakeRepository


def test_create_root_sets_embedding_input_to_name() -> None:
    svc = ArticleService(FakeRepository())
    article = svc.create(article_code="1", name="Раздел")
    assert article.embedding_input == "Раздел"
    assert article.parent_id is None
    assert article.embedding is None


def test_create_child_enriches_from_parent() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    child = svc.create(article_code="1.1", name="Лист", parent_code="1")
    assert child.embedding_input == "Раздел. Лист"
    assert child.parent_id == 1


def test_create_duplicate_code_raises() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    with pytest.raises(DuplicateError):
        svc.create(article_code="1", name="Дубль")


def test_create_node_that_would_be_ancestor_raises() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    svc.create(article_code="1.2.3", name="Глубокий лист", parent_code="1")
    # "1.2" стал бы предком уже существующего "1.2.3" — это запрещено (импорт only)
    with pytest.raises(TemplateValidationError):
        svc.create(article_code="1.2", name="Промежуточный", parent_code="1")


def test_create_rejects_non_numeric_code() -> None:
    # нечисловой код уронил бы GET /api/articles (cast в int[]) — отвергаем на входе
    with pytest.raises(TemplateValidationError):
        ArticleService(FakeRepository()).create(article_code="1a", name="Кривой")
```

- [ ] **Step 2: Добавить has_descendant_codes в фейк и порт**

В [backend/tests/fakes.py](../../../backend/tests/fakes.py) в `FakeRepository` добавить:

```python
    def has_descendant_codes(self, code: str) -> bool:
        prefix = f"{code}."
        return any(a.article_code.startswith(prefix) for a in self._store)
```

В [backend/app/domain/ports.py](../../../backend/app/domain/ports.py) в `ArticleRepository` добавить:

```python
    @abstractmethod
    def has_descendant_codes(self, code: str) -> bool: ...
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_article_service.py -v`
Expected: FAIL — `create` не бросает `DuplicateError`/`TemplateValidationError` (или `has_descendant_codes` отсутствует в реальном репозитории импорта — но тут фейк).

- [ ] **Step 4: Добавить guard'ы в ArticleService.create**

В [backend/app/services/article_service.py](../../../backend/app/services/article_service.py) обновить импорты (добавить `import re` в начало файла) и начало `create`:

```python
from app.domain.errors import DuplicateError, TemplateValidationError
```
```python
    def create(
        self, article_code: str, name: str, parent_code: str | None = None
    ) -> TemplateArticle:
        if re.fullmatch(r"\d+(\.\d+)*", article_code) is None:
            raise TemplateValidationError(
                f"Код {article_code} должен состоять из числовых сегментов (напр. 1.4.1)"
            )
        if self._repository.get_by_code(article_code) is not None:
            raise DuplicateError(f"Статья с кодом {article_code} уже существует")
        if self._repository.has_descendant_codes(article_code):
            raise TemplateValidationError(
                f"Код {article_code} стал бы предком существующих статей — "
                "воспользуйтесь импортом справочника"
            )
        parent_id: int | None = None
        embedding_input = name
        if parent_code:
            parent = self._repository.get_by_code(parent_code)
            if parent is None:
                raise ValueError(f"Родитель с кодом {parent_code} не найден")
            parent_id = parent.id
            embedding_input = f"{parent.embedding_input}. {name}"
        article = TemplateArticle(
            article_code=article_code,
            name=name,
            embedding_input=embedding_input,
            parent_id=parent_id,
            embedding=None,
        )
        return self._repository.add(article)
```

- [ ] **Step 5: Реализовать has_descendant_codes в SQL-репозитории**

В [backend/app/infrastructure/db/article_repository.py](../../../backend/app/infrastructure/db/article_repository.py) добавить метод (и `func` уже импортирован):

```python
    def has_descendant_codes(self, code: str) -> bool:
        prefix = code.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + ".%"
        stmt = select(TemplateArticleModel.id).where(
            TemplateArticleModel.article_code.like(prefix, escape="\\")
        ).limit(1)
        return self._session.scalars(stmt).first() is not None
```

- [ ] **Step 6: Обработать ошибки в роуте create_article**

В [backend/app/api/routes/articles.py](../../../backend/app/api/routes/articles.py) обновить `create_article`:

```python
from app.domain.errors import DeletionGuardError, DuplicateError, TemplateValidationError
```
```python
@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def create_article(
    payload: ArticleCreate,
    service: ArticleService = Depends(get_article_service),
) -> ArticleOut:
    try:
        article = service.create(
            article_code=payload.article_code,
            name=payload.name,
            parent_code=payload.parent_code,
        )
    except DuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ArticleOut.from_entity(article)
```

- [ ] **Step 7: Расширить authz-тест на дубликат**

В [backend/tests/test_authz_matrix.py](../../../backend/tests/test_authz_matrix.py) убедиться, что для admin-пути POST `/api/articles` с телом `{"article_code": "X", "name": "n"}` ожидается `201` на пустом репозитории. Если тест использует общий `FakeRepository` без предзаполнения — это уже покрыто Task 2. Доп. правок не требуется, кроме уже сделанных в Task 2 (тело без `section_name`).

- [ ] **Step 8: Прогнать весь набор + линт, commit**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: все PASS, ruff чисто.

```bash
git add backend/app/domain/ports.py backend/app/infrastructure/db/article_repository.py backend/app/services/article_service.py backend/app/api/routes/articles.py backend/tests/fakes.py backend/tests/test_article_service.py
git commit -m "feat(api): guard ручного POST /articles (409 дубликат, 400 узел-предок)"
```

---

### Task 8: Фоновый воркер эмбеддингов (DB-as-queue, CAS)

**Files:**
- Modify: `backend/app/domain/entities.py` (+`PendingEmbedding`)
- Modify: `backend/app/domain/ports.py` (+`EmbeddingQueueRepository`)
- Create: `backend/app/infrastructure/db/embedding_queue_repository.py`
- Create: `backend/app/services/embedding_worker.py`
- Create: `backend/app/scripts/embed_worker.py`
- Modify: `backend/tests/fakes.py` (+`FakeEmbeddingQueueRepository`)
- Modify: `justfile` (+`embed-worker`)
- Test: `backend/tests/test_embedding_worker.py`

**Interfaces:**
- Produces: `PendingEmbedding(id: int, embedding_input: str)`; порт `EmbeddingQueueRepository` с `fetch_pending(limit: int) -> list[PendingEmbedding]` и `save_embedding(article_id: int, embedding_input: str, vector: list[float]) -> bool` (CAS, `True` если записано). Функция `run_once(queue: EmbeddingQueueRepository, embedder: Embedder, batch_size: int = 100) -> int` (число записанных векторов).

- [ ] **Step 1: Добавить PendingEmbedding и порт очереди**

В [backend/app/domain/entities.py](../../../backend/app/domain/entities.py) добавить:

```python
@dataclass(frozen=True, slots=True)
class PendingEmbedding:
    """Строка справочника, ожидающая векторизации."""

    id: int
    embedding_input: str
```

В [backend/app/domain/ports.py](../../../backend/app/domain/ports.py) добавить `PendingEmbedding` в импорт сущностей и класс:

```python
class EmbeddingQueueRepository(ABC):
    """Очередь векторизации = строки template_articles с embedding IS NULL."""

    @abstractmethod
    def fetch_pending(self, limit: int) -> list[PendingEmbedding]: ...

    @abstractmethod
    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        """Compare-and-swap: пишет вектор только если embedding_input не изменился."""
        ...
```

- [ ] **Step 2: Написать падающие тесты воркера**

Создать `backend/tests/test_embedding_worker.py`:

```python
from __future__ import annotations

from app.domain.entities import PendingEmbedding
from app.domain.ports import EmbeddingQueueRepository
from app.services.embedding_worker import run_once
from tests.fakes import FakeEmbedder


class _Queue(EmbeddingQueueRepository):
    def __init__(self, pending: list[PendingEmbedding]) -> None:
        self._pending = list(pending)
        self.saved: dict[int, list[float]] = {}
        self.stale_inputs: set[int] = set()  # id, для которых CAS не сматчится

    def fetch_pending(self, limit: int) -> list[PendingEmbedding]:
        batch = self._pending[:limit]
        self._pending = self._pending[limit:]
        return batch

    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        if article_id in self.stale_inputs:
            return False
        self.saved[article_id] = vector
        return True


def test_run_once_embeds_pending_in_batches() -> None:
    queue = _Queue([PendingEmbedding(id=1, embedding_input="a"), PendingEmbedding(id=2, embedding_input="bb")])
    written = run_once(queue, FakeEmbedder(), batch_size=10)
    assert written == 2
    assert set(queue.saved) == {1, 2}


def test_run_once_cas_skips_stale_row() -> None:
    queue = _Queue([PendingEmbedding(id=1, embedding_input="a"), PendingEmbedding(id=2, embedding_input="b")])
    queue.stale_inputs.add(2)  # импорт сменил текст -> CAS не сматчится
    written = run_once(queue, FakeEmbedder(), batch_size=10)
    assert written == 1
    assert 1 in queue.saved
    assert 2 not in queue.saved


def test_run_once_returns_zero_when_empty() -> None:
    assert run_once(_Queue([]), FakeEmbedder(), batch_size=10) == 0
```

- [ ] **Step 3: Добавить FakeEmbeddingQueueRepository не требуется**

Тест объявляет очередь локально (`_Queue`). Доп. фейка в `fakes.py` не требуется — пропустить (YAGNI). `FakeEmbedder` уже есть.

- [ ] **Step 4: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_embedding_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.embedding_worker`.

- [ ] **Step 5: Реализовать run_once**

Создать `backend/app/services/embedding_worker.py`:

```python
"""Логика одного прохода фонового эмбеддинга. Без БД/SDK — зависит только от портов."""

from __future__ import annotations

from app.domain.ports import Embedder, EmbeddingQueueRepository


def run_once(
    queue: EmbeddingQueueRepository, embedder: Embedder, batch_size: int = 100
) -> int:
    """Векторизует одну пачку ожидающих строк. Возвращает число записанных векторов."""
    pending = queue.fetch_pending(batch_size)
    if not pending:
        return 0
    vectors = embedder.embed_batch([row.embedding_input for row in pending])
    written = 0
    for row, vector in zip(pending, vectors, strict=True):
        if queue.save_embedding(row.id, row.embedding_input, vector):
            written += 1
    return written
```

- [ ] **Step 6: Запустить тесты воркера — убедиться, что проходят**

Run: `cd backend; uv run pytest tests/test_embedding_worker.py -v`
Expected: PASS (3 теста).

- [ ] **Step 7: Реализовать SQL-адаптер очереди**

Создать `backend/app/infrastructure/db/embedding_queue_repository.py`:

```python
"""SQL-реализация очереди эмбеддингов поверх template_articles (embedding IS NULL)."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.entities import PendingEmbedding
from app.domain.ports import EmbeddingQueueRepository
from app.infrastructure.db.models import TemplateArticleModel


class SqlAlchemyEmbeddingQueueRepository(EmbeddingQueueRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def fetch_pending(self, limit: int) -> list[PendingEmbedding]:
        stmt = (
            select(TemplateArticleModel.id, TemplateArticleModel.embedding_input)
            .where(TemplateArticleModel.embedding.is_(None))
            .order_by(TemplateArticleModel.id)
            .limit(limit)
        )
        return [PendingEmbedding(id=row.id, embedding_input=row.embedding_input)
                for row in self._session.execute(stmt)]

    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        stmt = (
            update(TemplateArticleModel)
            .where(
                TemplateArticleModel.id == article_id,
                TemplateArticleModel.embedding_input == embedding_input,
            )
            .values(embedding=vector)
        )
        result = self._session.execute(stmt)
        self._session.commit()
        return result.rowcount > 0
```

> **Примечание:** коммит здесь построчный (на каждый `save_embedding`), а не одной пачкой. Это намеренно: при падении воркера на середине уже записанные векторы сохраняются, остаток остаётся `IS NULL` и подберётся при следующем проходе. `run_once` ничего дополнительно не коммитит.

- [ ] **Step 8: Реализовать CLI-скрипт воркера**

Создать `backend/app/scripts/embed_worker.py`:

```python
"""Фоновый воркер эмбеддингов. Очередь = template_articles с embedding IS NULL.

Запуск: `uv run python -m app.scripts.embed_worker [--once] [--batch-size N]`.
"""

from __future__ import annotations

import argparse
import time

from app.api.deps import get_embedder
from app.infrastructure.db.embedding_queue_repository import SqlAlchemyEmbeddingQueueRepository
from app.infrastructure.db.session import SessionLocal
from app.services.embedding_worker import run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Фоновый эмбеддинг справочника СМР")
    parser.add_argument("--once", action="store_true", help="один проход и выход")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=5.0, help="пауза между проходами, сек")
    args = parser.parse_args()

    embedder = get_embedder()
    while True:
        session = SessionLocal()
        try:
            queue = SqlAlchemyEmbeddingQueueRepository(session)
            written = run_once(queue, embedder, batch_size=args.batch_size)
        finally:
            session.close()

        if args.once:
            print(f"Записано векторов: {written}")
            return
        if written == 0:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
```

- [ ] **Step 9: Добавить рецепт в justfile**

В [justfile](../../../justfile) добавить в конец:

```
# Фоновый воркер эмбеддингов (template_articles с embedding IS NULL). --once для одного прохода.
embed-worker *args:
    cd {{backend}}; uv run python -m app.scripts.embed_worker {{args}}
```

- [ ] **Step 10: Прогнать весь набор + линт, commit**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: все PASS, ruff чисто.

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/infrastructure/db/embedding_queue_repository.py backend/app/services/embedding_worker.py backend/app/scripts/embed_worker.py backend/tests/test_embedding_worker.py justfile
git commit -m "feat(worker): фоновый эмбеддинг (DB-as-queue, CAS-запись)"
```

---

### Task 9: End-to-end смоук-проверка на реальном файле и БД

Проверяет то, что не покрыто юнит-тестами: миграцию `0002`, SQL-адаптеры (`import_repository`, `embedding_queue_repository`, сортировка по коду), реальный вызов OpenRouter. Использует тестовую БД (`TEST_DATABASE_URL` из `backend/.env`) и реальный файл `temp/Шаблон.xlsx`.

**Files:**
- Create: `backend/app/scripts/smoke_import.py` (разовый помощник; можно удалить после проверки)

**Interfaces:**
- Consumes: `SqlAlchemyArticleImportRepository`, `TemplateParser`, `TemplateIngestService`, `SqlAlchemyArticleRepository`.

- [ ] **Step 1: Применить миграции к БД**

Run: `just migrate`
Expected: `alembic upgrade head` без ошибок; `cd backend; uv run alembic current` показывает `0002 (head)`.

- [ ] **Step 2: Проверить autogenerate-чистоту ORM**

Run: `cd backend; uv run alembic check`
Expected: «No new upgrade operations detected» (ORM-модель совпала с применённой схемой). Если шумит на `Vector`/HNSW — это известный долг, зафиксировать в выводе и не падать.

- [ ] **Step 3: Написать разовый смоук-скрипт импорта**

Создать `backend/app/scripts/smoke_import.py`:

```python
"""Разовый смоук: импорт реального temp/Шаблон.xlsx в БД из DATABASE_URL.

Запуск (из backend, PYTHONIOENCODING=utf-8):
    uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx
"""

from __future__ import annotations

import sys

from app.infrastructure.db.import_repository import SqlAlchemyArticleImportRepository
from app.infrastructure.db.session import SessionLocal
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser


def main() -> None:
    path = sys.argv[1]
    with open(path, "rb") as fh:
        content = fh.read()
    session = SessionLocal()
    try:
        service = TemplateIngestService(
            parser=TemplateParser(), repository=SqlAlchemyArticleImportRepository(session)
        )
        report = service.import_template(content, force=True)
    finally:
        session.close()
    print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Запустить импорт реального файла**

Run: `cd backend; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx`
Expected: `ImportReport(created=362, updated=0, deleted=0, unchanged=0, skipped=[], pending_embeddings=362, dry_run=False, force_required=False)`.

- [ ] **Step 5: Запустить воркер на один проход**

Run: `just embed-worker --once --batch-size 100`
Повторить вызов, пока не выведет `Записано векторов: 0` (≈4 прохода по 100).
Expected: суммарно 362 вектора записаны.

- [ ] **Step 6: Проверить состояние БД**

Run:
```bash
cd backend; $env:PYTHONIOENCODING="utf-8"; uv run python -c "from app.infrastructure.db.session import SessionLocal; from sqlalchemy import text; s=SessionLocal(); print('total', s.execute(text('select count(*) from template_articles')).scalar()); print('pending', s.execute(text('select count(*) from template_articles where embedding is null')).scalar()); print('roots', s.execute(text(\"select count(*) from template_articles where parent_id is null\")).scalar()); s.close()"
```
Expected: `total 362`, `pending 0`, `roots 21` (21 раздел верхнего уровня).

- [ ] **Step 7: Проверить идемпотентность повторного импорта**

Run: `cd backend; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx`
Expected: `ImportReport(created=0, updated=0, deleted=0, unchanged=362, pending_embeddings=0, ...)` — повторный импорт ничего не меняет, эмбеддинги сохранены.

- [ ] **Step 8: Удалить смоук-скрипт и зафиксировать результат**

Удалить `backend/app/scripts/smoke_import.py` (разовый помощник).

```bash
git rm backend/app/scripts/smoke_import.py
git commit -m "chore: end-to-end смоук импорта пройден (362 строки, эмбеддинги наполнены)"
```

Если на шагах 4–7 что-то разошлось с ожиданием (число строк, parent_id, CAS) — НЕ удалять скрипт, завести дефект и чинить соответствующий SQL-адаптер до зелёного.

---

## Self-Review

**Spec coverage:**
- Две фазы (синхронный импорт + фоновый воркер) → Tasks 5/6 + Task 8. ✓
- `embedding IS NULL` как очередь → Task 8 (`fetch_pending`). ✓
- `embedding_input` (инвалидация + развязка воркера) → Tasks 3/4/8. ✓
- Миграция 0002 + выравнивание ORM/entity/repo (закрытие долга) → Task 2. ✓
- Парсер/санитайз/обогащённый текст/коды/сироты → Task 3. ✓
- Upsert + защита удаления (preview/dry_run/порог/force) → Tasks 4/5/6. ✓
- CAS-запись воркера → Task 8 (`save_embedding`) + тест. ✓
- Сортировка по коду численно → Task 2 (`_CODE_ORDER`). ✓
- Эмбеддер gemini-embedding-2 @768 via OpenRouter → Task 1. ✓
- `POST /api/articles/import` (admin, dry_run/force, 400/409) → Task 6. ✓
- Ручной `POST /articles` (parent_code, guard 400/409, без синхронного эмбеддинга) → Tasks 2/7. ✓
- `anthropic_matcher` без `section_name` → Task 2. ✓
- `ArticleService` без `Embedder` → Task 2. ✓
- Тесты (parser, ingest, worker, endpoint) → Tasks 3/4/5/6/7/8; SQL/миграция/реальный OpenRouter → Task 9. ✓
- Вне объёма (матчинг, фронт, перекалибровка порога, увод арбитра на OpenRouter) — не планируется. ✓

**Type consistency:** `TemplateArticle` (новая форма) едина в Tasks 2/5/7. `ImportPlan`/`PlannedInsert`/`PlannedUpdate`/`ExistingArticle`/`ImportReport` определены в Task 4, используются в Tasks 5/6 с теми же полями. `ParsedTemplateRow`/`ParseResult` — Task 3, потребляются в Tasks 4/5. Порты `ArticleImportRepository` (Task 5), `EmbeddingQueueRepository` (Task 8), `ArticleRepository.get_by_code`/`has_descendant_codes` (Tasks 2/7) — реализованы в SQL и фейках синхронно. `run_once`/`save_embedding`/`fetch_pending` сигнатуры совпадают между Task 8-тестом, сервисом и адаптером.

**Placeholder scan:** код приведён в каждом шаге; «TBD»/«добавить обработку ошибок» без кода отсутствуют. Один тест в Task 7 (`test_create_ancestor_of_existing_raises`) снабжён явной заменой тела во избежание двусмысленности.
