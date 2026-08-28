# Tree Matching PR 1 — ядро за флагом (без фонда) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить второй движок сопоставления `tree` (LLM по разделу целиком с полным справочником в промпте), переключаемый настройкой `matching_engine`, при default `rag`; фонд решений в этом PR выключен.

**Architecture:** Чистые доменные функции (`domain/tree_matching.py`) режут дерево сметы на чанки, считают контекст предков, валидируют вердикты и превращают их в `NodeMatch`. Новый порт `TreeMatcher` реализуется адаптером OpenRouter. Оркестрация — `TreeMatchingRunner` (`services/tree_matching_service.py`), который `EstimateMatchingService` вызывает вместо стадий classify/embed/match, когда движок `tree`; lock, статусы сметы и summary остаются в `EstimateMatchingService`. Запись — новый CAS `save_node_match_cas` по статусу **и** `review_status`.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, pydantic-settings, httpx, pytest; фронт — TypeScript/React, vitest.

**Spec:** [docs/superpowers/specs/2026-08-27-tree-matching-core-design.md](../specs/2026-08-27-tree-matching-core-design.md) (§3 домен, §4 сервис, §5 инфраструктура, §7.1 `score` nullable, §11 п.1 — границы PR 1).

## Global Constraints

- Направление зависимостей `api → services → domain ← infrastructure`; `domain/` без FastAPI/SQLAlchemy/httpx.
- Все файлы бэка: `from __future__ import annotations`, type hints, ruff (line-length 100). Перед коммитом `uv run ruff check .` из `backend/`.
- Команды бэка только через `uv run` из `backend/` (`cd backend`). Кириллица в stdout → `PYTHONIOENCODING=utf-8`.
- Фронт: `npm run typecheck` (`tsc -b`), eslint, prettier (`printWidth 80`, LF).
- Юнит-тесты не ходят в БД/AI — фейки портов в `backend/tests/fakes.py`.
- **PR 1 — без фонда:** `TreeMatchingRunner` создаётся с `fund_enabled=False` жёстко; `records` пуст, exact-hit не срабатывает, блок прецедентов не рендерится; `matched_fund` для `tree` недостижим.
- `matching_engine` default `rag`. Ничего из RAG-пути не удаляется.
- Логи — `logging.getLogger(__name__)`, `extra` только с неймспейснутыми ключами; AI-вызов через `instrumented_call`.
- Ветка: `feat/tree-matching-core` от `main` (спека лежит на `spec/tree-matching-core` — сначала влить её PR-ом или ребейзнуть ветку фичи поверх неё).

---

## Карта файлов

| Файл | Ответственность |
|---|---|
| `backend/app/domain/entities.py` (modify) | `TreeNode`, `CatalogArticle`, `FundPrecedent`, `SectionMatchRequest`, `NodeVerdict`, `AncestorContext`; `MatchCandidate.score: float \| None` |
| `backend/app/domain/ports.py` (modify) | порт `TreeMatcher`; методы `fetch_tree`, `refresh_tree_node`, `save_node_match_cas` у `EstimateRepository`; `list_catalog` у `ArticleRepository` |
| `backend/app/domain/tree_matching.py` (create) | `resolve_parents`, `effective_ancestor_context`, `estimate_tokens`, `split_sections`, `build_hints`, `validate_verdicts`, `to_node_match`, `neighbors`, коды ошибок |
| `backend/app/domain/decision_fund.py` (modify) | `FUND_KEY_VERSION = 3`, `fund_key_v3` |
| `backend/app/infrastructure/db/estimate_repository.py` (modify) | `fetch_tree`, `refresh_tree_node`, `save_node_match_cas` |
| `backend/app/infrastructure/db/article_repository.py` (modify) | `list_catalog` |
| `backend/app/infrastructure/ai/tree_prompt.py` (create) | системный промпт, сборка user-промпта, парсинг JSON-вердиктов |
| `backend/app/infrastructure/ai/openrouter_tree_matcher.py` (create) | `OpenRouterTreeMatcher` — HTTP, ретраи, `cache_control`, обрезка ответа |
| `backend/app/services/tree_matching_service.py` (create) | `TreeMatchingRunner.run(estimate_id) -> Counter` — обход чанков, CAS, транзиенты |
| `backend/app/services/estimate_matching_service.py` (modify) | ветка `tree` в `match_estimate` |
| `backend/app/core/config.py` (modify) | настройки `matching_engine`, `openrouter_tree_model`, `tree_*` + валидаторы |
| `backend/app/api/deps.py` (modify) | `get_tree_matcher`, wiring в `build_estimate_matching_service` |
| `backend/app/api/schemas.py` (modify) | `MatchCandidateOut.score: float \| None` |
| `backend/tests/fakes.py` (modify) | `FakeTreeMatcher`, `fetch_tree`/`refresh_tree_node`/`save_node_match_cas`/`list_catalog` у фейков |
| `backend/tests/test_tree_matching_domain.py` (create) | юниты домена |
| `backend/tests/test_tree_prompt.py`, `test_openrouter_tree_matcher.py` (create) | промпт/парсер и адаптер |
| `backend/tests/test_tree_matching_service.py` (create) | сервисные тесты через фейки |
| `backend/tests/test_estimate_repo_cas.py` (modify) | зеркало SQL-контракта нового CAS |
| `backend/tests/test_config.py` (modify) | дефолты и валидаторы новых настроек |
| `frontend/src/lib/types.ts`, `lib/api/estimates.ts`, `pages/estimate/ReviewCard.tsx`, `lib/mock/api.ts` (+ тесты) | `score: number \| null` |
| `docs/TECH_DEBT.md`, `docs/PIPELINE.md`, `CLAUDE.md`, `docs/devlog/2026-08-XX-tree-matching-pr1.md` | документация |

---

### Task 1: Сущности, порт и nullable `score`

**Files:**
- Modify: `backend/app/domain/entities.py` (после `class MatchCandidate`, строка ~274; после `class ClassifiableNode`)
- Modify: `backend/app/domain/ports.py` (после `class LLMMatcher`, строка ~99; в `EstimateRepository` после `save_node_match`, строка ~266; в `ArticleRepository` после `ancestor_names_by_ids`, строка ~83)
- Modify: `backend/app/api/schemas.py:173`
- Test: `backend/tests/test_tree_matching_domain.py` (create), `backend/tests/test_estimate_row_payload.py` (modify)

**Interfaces:**
- Produces: dataclasses `TreeNode`, `CatalogArticle`, `FundPrecedent`, `SectionMatchRequest`, `NodeVerdict`, `AncestorContext` (поля — ниже, точно как в спеке §3.1); `SectionMatchResponse`; ABC `TreeMatcher.match_section(req: SectionMatchRequest) -> SectionMatchResponse`; абстрактные методы `EstimateRepository.fetch_tree(estimate_id: int) -> list[TreeNode]`, `refresh_tree_node(node_id: int) -> TreeNode`, `save_node_match_cas(node_id: int, result: NodeMatch, expected_statuses: Sequence[str]) -> bool`; `ArticleRepository.list_catalog() -> list[CatalogArticle]`.

- [ ] **Step 1: Написать падающий тест на сущности и сериализацию `score=None`**

`backend/tests/test_tree_matching_domain.py`:
```python
from __future__ import annotations

from app.domain.entities import (
    AncestorContext,
    CatalogArticle,
    MatchCandidate,
    NodeVerdict,
    SectionMatchRequest,
    TreeNode,
)


def _tn(i: int, depth: int, code: str, name: str = "", status: str = "pending", **kw) -> TreeNode:
    return TreeNode(
        id=i, source_index=i, depth=depth, code=code, name=name or f"n{code}", status=status,
        review_status=kw.get("review_status", "unreviewed"),
        matched_code=kw.get("matched_code"), matched_article_id=kw.get("matched_article_id"),
        final_code=kw.get("final_code"), final_article_id=kw.get("final_article_id"),
    )


def test_tree_entities_construct() -> None:
    n = _tn(1, 1, "1")
    ctx = AncestorContext(trusted_code=None, has_uncertain_barrier=False)
    v = NodeVerdict(node_id=1, kind="article", article_code="1", sure=True, alt_code=None)
    req = SectionMatchRequest(nodes=[n], ancestors=[], hints={}, targets=frozenset({1}),
                              catalog=[CatalogArticle(1, "1", "Раздел", None)], precedents=[])
    assert req.targets == {1} and v.kind == "article" and ctx.trusted_code is None


def test_match_candidate_score_nullable() -> None:
    assert MatchCandidate(id=1, code="1", name="x", score=None).score is None
```

В `backend/tests/test_estimate_row_payload.py` добавить (используя существующие хелперы файла для сборки `StoredEstimateRow` → `EstimateRowOut.from_entity`):
```python
def test_candidate_score_none_serializes_as_null() -> None:
    from app.api.schemas import EstimateRowOut
    from app.domain.entities import MatchCandidate, StoredEstimateRow

    row = StoredEstimateRow(
        id=1, code="1", name="n", parent_code=None, section_type=None, depth=1,
        embedding_input="n", source_index=0, status="needs_review",
        candidates=[MatchCandidate(id=5, code="1.1", name="a", score=None)],
    )
    out = EstimateRowOut.from_entity(row)
    assert out.candidates[0].score is None
    assert out.model_dump()["candidates"][0]["score"] is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd backend; uv run pytest tests/test_tree_matching_domain.py tests/test_estimate_row_payload.py -q`
Expected: `ImportError: cannot import name 'TreeNode'`; тест `score None` — `ValidationError`.

- [ ] **Step 3: Добавить сущности**

В `backend/app/domain/entities.py` изменить `MatchCandidate.score: float` → `score: float | None` и добавить после `ClassifiableNode`/`NodeClassification` блок:
```python
@dataclass(frozen=True, slots=True)
class TreeNode:
    """Строка сметы для tree-движка: контекст + цель. fetch_tree отдаёт в порядке source_index."""

    id: int
    source_index: int
    depth: int
    code: str
    name: str
    status: str
    review_status: str
    matched_code: str | None
    matched_article_id: int | None
    final_code: str | None
    final_article_id: int | None

    def with_result(self, result: NodeMatch) -> TreeNode:
        """Копия узла после успешного CAS — рабочее дерево должно видеть свежий снимок."""
        return replace(
            self, status=str(result.status), matched_code=result.matched_code,
            matched_article_id=result.matched_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogArticle:
    id: int
    code: str
    name: str
    parent_code: str | None


@dataclass(frozen=True, slots=True)
class FundPrecedent:
    name: str
    parent_article_code: str
    article_code: str
    article_name: str
    votes: int
    article_id: int
    key: str


@dataclass(frozen=True, slots=True)
class SectionMatchRequest:
    nodes: list[TreeNode]
    ancestors: list[tuple[TreeNode, tuple[str, bool] | None]]  # (код, trusted) из hint_for; None — прозрачный предок
    hints: dict[int, tuple[str, bool]]
    targets: frozenset[int]
    catalog: list[CatalogArticle]
    precedents: list[FundPrecedent]


@dataclass(frozen=True, slots=True)
class NodeVerdict:
    node_id: int
    kind: str  # "article" | "org" | "none"
    article_code: str | None
    sure: bool
    alt_code: str | None


@dataclass(frozen=True, slots=True)
class AncestorContext:
    trusted_code: str | None
    has_uncertain_barrier: bool


@dataclass(frozen=True, slots=True)
class SectionMatchResponse:
    """Сырой ответ адаптера: словари {"i","code","sure","alt"} валидирует домен (fail-closed)."""

    items: list[dict]
    truncated: bool  # finish_reason == "length" → сервис делит чанк
```
Импорт: `from dataclasses import dataclass, field, replace` (добавить `replace`). Порт ниже объявляется сразу с `SectionMatchResponse` (Task 8 его использует, не меняет). `NodeMatch` объявлен выше `TreeNode` — порядок в файле важен только для аннотаций (файл с `from __future__ import annotations`, поэтому строки-аннотации допустимы).

- [ ] **Step 4: Порт и методы репозиториев**

В `backend/app/domain/ports.py`:
```python
class TreeMatcher(ABC):
    """Сопоставляет раздел сметы целиком (спека tree matching §3.2)."""

    @abstractmethod
    def match_section(self, req: SectionMatchRequest) -> SectionMatchResponse: ...
```
В `EstimateRepository` после `save_node_match`:
```python
    @abstractmethod
    def fetch_tree(self, estimate_id: int) -> list[TreeNode]:
        """Все строки сметы в порядке source_index — рабочее дерево tree-движка."""

    @abstractmethod
    def refresh_tree_node(self, node_id: int) -> TreeNode:
        """Перечитать одну строку (после проигранного CAS)."""

    @abstractmethod
    def save_node_match_cas(
        self, node_id: int, result: NodeMatch, expected_statuses: Sequence[str]
    ) -> bool:
        """UPDATE … WHERE status IN expected AND review_status='unreviewed'. False = гонка."""
```
В `ArticleRepository`:
```python
    @abstractmethod
    def list_catalog(self) -> list[CatalogArticle]:
        """Весь справочник (id, code, name, parent_code) для промпта tree-движка."""
```
Импорты сущностей дополнить. В `backend/app/api/schemas.py:173` — `score: float | None`.

Абстрактные методы сломают фейки (`FakeEstimateRepository`, `FakeRepository`, `FakeArticleRepository`) — добавить минимальные реализации в `backend/tests/fakes.py` **в этой же задаче** (полноценная логика — Task 6):
```python
    # FakeRepository и FakeArticleRepository:
    def list_catalog(self) -> list[CatalogArticle]:
        return [
            CatalogArticle(id=a.id or 0, code=a.article_code, name=a.name, parent_code=None)
            for a in self._store
        ]
```
(`FakeArticleRepository` хранит статьи в своём поле — использовать его; `parent_code` вычислить как `".".join(code.split(".")[:-1]) or None`.)
Для `FakeEstimateRepository` — заглушки `raise NotImplementedError` до Task 6 недопустимы (сломают DI-тесты? нет — методы не вызываются), но реализуем сразу честно в Task 6; здесь достаточно `def fetch_tree(...): return []`, `def refresh_tree_node(...): raise KeyError(node_id)`, `def save_node_match_cas(...): return False` с комментарием `# заполняется в Task 6`.

- [ ] **Step 5: Прогнать тесты**

Run: `cd backend; uv run pytest -q`
Expected: всё зелёное (существующие тесты с `MatchCandidate(score=0.5)` не ломаются — тип расширен).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/api/schemas.py backend/tests/fakes.py backend/tests/test_tree_matching_domain.py backend/tests/test_estimate_row_payload.py
git commit -m "feat(tree): сущности и порт TreeMatcher, score кандидата nullable"
```

---

### Task 2: Домен — родители, контекст предков, ключ фонда, оценка токенов

**Files:**
- Create: `backend/app/domain/tree_matching.py`
- Modify: `backend/app/domain/decision_fund.py`
- Test: `backend/tests/test_tree_matching_domain.py`

**Interfaces:**
- Consumes: `TreeNode`, `AncestorContext` (Task 1); `resolve_ancestor_indices(depths)` из `app/domain/classification.py`; `normalize_cache_key` из `decision_fund.py`.
- Produces: `resolve_parents(nodes: Sequence[TreeNode]) -> list[int | None]`; `effective_ancestor_context(idx: int, nodes: Sequence[TreeNode], parents: Sequence[int | None]) -> AncestorContext`; `estimate_tokens(text: str) -> int`; `TRUSTED_STATUSES = ("confident", "matched_fund")`; `FUND_KEY_VERSION = 3`; `fund_key_v3(node: TreeNode, ctx: AncestorContext) -> str | None`.

- [ ] **Step 1: Тесты**

Добавить в `tests/test_tree_matching_domain.py`:
```python
from app.domain.decision_fund import FUND_KEY_VERSION, fund_key_v3
from app.domain.tree_matching import (
    effective_ancestor_context,
    estimate_tokens,
    resolve_parents,
)


def test_resolve_parents_positional_not_by_code() -> None:
    # коды повторяются между этапами: второй «6.2» — ребёнок второго «6», не первого
    nodes = [_tn(1, 1, "6"), _tn(2, 2, "6.2"), _tn(3, 1, "6"), _tn(4, 2, "6.2"), _tn(5, 4, "6.2.1.1")]
    assert resolve_parents(nodes) == [None, 0, None, 2, 3]  # скачок глубины 2→4: ближайший открытый


def test_context_trusted_stops_at_reviewed_or_confident() -> None:
    nodes = [
        _tn(1, 1, "4", status="confident", matched_code="4"),
        _tn(2, 2, "4.1", status="needs_review", matched_code="4.9"),
        _tn(3, 3, "4.1.1"),
    ]
    p = resolve_parents(nodes)
    assert effective_ancestor_context(2, nodes, p) == ("4", True)  # A→B(needs_review)→C
    nodes2 = [_tn(1, 1, "4", status="needs_review", matched_code="4",
                  review_status="overridden", final_code="5"), _tn(2, 2, "4.1")]
    assert effective_ancestor_context(1, nodes2, resolve_parents(nodes2)) == ("5", False)


def test_context_transparent_statuses_and_root() -> None:
    nodes = [_tn(1, 1, "1", status="excluded"), _tn(2, 2, "1.1", status="no_match"), _tn(3, 3, "1.1.1")]
    p = resolve_parents(nodes)
    assert effective_ancestor_context(2, nodes, p) == (None, False)   # корень — доверенная база
    assert effective_ancestor_context(0, nodes, p) == (None, False)


def test_fund_key_v3_uses_trusted_code_and_none_on_barrier() -> None:
    n = _tn(1, 2, "1.1", name="  Прочее ")
    assert fund_key_v3(n, ("4.2", False)) == "прочее\x1f4.2"
    assert fund_key_v3(n, (None, False)) == "прочее\x1f"
    assert fund_key_v3(n, ("4.2", True)) is None
    assert FUND_KEY_VERSION == 3


def test_estimate_tokens_ceil_div_3() -> None:
    assert estimate_tokens("") == 0 and estimate_tokens("ab") == 1 and estimate_tokens("abcd") == 2
```
(`AncestorContext` — dataclass, сравнение с кортежем не сработает: заменить на `AncestorContext("4", True)` и т.д. — использовать конструктор во всех assert.)

- [ ] **Step 2: Убедиться в падении**

Run: `cd backend; uv run pytest tests/test_tree_matching_domain.py -q`
Expected: `ModuleNotFoundError: app.domain.tree_matching`.

- [ ] **Step 3: Реализация**

`backend/app/domain/tree_matching.py`:
```python
"""Чистая логика tree-движка сопоставления (спека 2026-08-27 §3.3). Без I/O."""

from __future__ import annotations

import math
from collections.abc import Sequence

from app.domain.classification import resolve_ancestor_indices
from app.domain.entities import AncestorContext, TreeNode

TRUSTED_STATUSES = ("confident", "matched_fund")
REVIEWED_STATUSES = ("confirmed", "overridden")
UNCERTAIN_STATUSES = ("needs_review",)


def resolve_parents(nodes: Sequence[TreeNode]) -> list[int | None]:
    """Индекс родителя для каждого узла — позиционно по depth (коды повторяются между этапами)."""
    chains = resolve_ancestor_indices([n.depth for n in nodes])
    return [chain[-1] if chain else None for chain in chains]


def effective_ancestor_context(
    idx: int, nodes: Sequence[TreeNode], parents: Sequence[int | None]
) -> AncestorContext:
    """Ближайший ДОВЕРЕННЫЙ предок и наличие барьера needs_review на пути к нему."""
    barrier = False
    p = parents[idx]
    while p is not None:
        anc = nodes[p]
        if anc.review_status in REVIEWED_STATUSES and anc.final_code:
            return AncestorContext(anc.final_code, barrier)
        if anc.status in TRUSTED_STATUSES and anc.review_status == "unreviewed" and anc.matched_code:
            return AncestorContext(anc.matched_code, barrier)
        if anc.status in UNCERTAIN_STATUSES:
            barrier = True
        p = parents[p]
    return AncestorContext(None, barrier)


def estimate_tokens(text: str) -> int:
    """Консервативная оценка токенов для кириллицы (замер спайка: 6.0k оценка vs 5.6k факт)."""
    return math.ceil(len(text) / 3)
```
В `backend/app/domain/decision_fund.py`:
```python
FUND_KEY_VERSION = 3  # ключ v3: (норм. имя строки, код доверенной статьи предка); отдельно от CRUMB_DERIVATION_VERSION
_KEY_SEP = "\x1f"


def fund_key_v3(node: TreeNode, ctx: AncestorContext) -> str | None:
    """None при барьере: exact-фонд на сомнительном контексте не применяется (спека §6.1)."""
    if ctx.has_uncertain_barrier:
        return None
    return f"{normalize_cache_key(node.name)}{_KEY_SEP}{ctx.trusted_code or ''}"
```
(импорт `TreeNode`, `AncestorContext` из `entities`).

- [ ] **Step 4: Прогнать, ruff, commit**

Run: `cd backend; uv run pytest tests/test_tree_matching_domain.py -q; uv run ruff check .`
```bash
git add backend/app/domain/tree_matching.py backend/app/domain/decision_fund.py backend/tests/test_tree_matching_domain.py
git commit -m "feat(tree): позиционные родители, контекст предков, ключ фонда v3"
```

---

### Task 3: Домен — `split_sections`

**Files:**
- Modify: `backend/app/domain/tree_matching.py`
- Test: `backend/tests/test_tree_matching_domain.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) Chunk(root: int, indices: list[int])` (индексы в `nodes`, по документу; `indices[0]` может быть ≠ `root` только если это чанк-продолжение — см. ниже; проще: каждый чанк начинается со своего корня-поддерева); `split_sections(nodes, parents, *, max_rows: int, budget_tokens: int, row_tokens: Callable[[TreeNode], int]) -> list[Chunk]`; `ROW_TOO_LARGE = "tree_row_too_large"`; `Chunk.oversized: list[int]` — узлы, не влезающие сами по себе.

- [ ] **Step 1: Тесты**

```python
from app.domain.tree_matching import Chunk, split_sections

def _tok(n: TreeNode) -> int:
    return 1

def _chain(depths: list[int]) -> list[TreeNode]:
    return [_tn(i + 1, d, ".".join(["1"] * d)) for i, d in enumerate(depths)]


def test_split_small_section_is_one_chunk() -> None:
    nodes = _chain([1, 2, 2, 3])
    chunks = split_sections(nodes, resolve_parents(nodes), max_rows=10, budget_tokens=100, row_tokens=_tok)
    assert chunks == [Chunk(root=0, indices=[0, 1, 2, 3], oversized=[])]


def test_split_by_children_keeps_parent_chunk_first() -> None:
    # корень + два ребёнка по 3 узла; лимит 4 → шапка = корень + первый ребёнок, второй — отдельно
    nodes = _chain([1, 2, 3, 3, 2, 3, 3])
    chunks = split_sections(nodes, resolve_parents(nodes), max_rows=4, budget_tokens=100, row_tokens=_tok)
    assert [c.indices for c in chunks] == [[0, 1, 2, 3], [4, 5, 6]]
    assert chunks[1].root == 4


def test_split_single_oversized_child_recurses_and_terminates() -> None:
    # цепочка без сиблингов глубже лимита: каждый уровень становится чанком-звеном
    nodes = _chain([1, 2, 3, 4, 5])
    chunks = split_sections(nodes, resolve_parents(nodes), max_rows=2, budget_tokens=100, row_tokens=_tok)
    assert [c.indices for c in chunks] == [[0], [1], [2], [3, 4]]


def test_split_token_budget_and_row_too_large() -> None:
    nodes = _chain([1, 2, 2])
    big = {2: 50}  # _chain: id = индекс + 1 → второй узел (индекс 1)
    chunks = split_sections(nodes, resolve_parents(nodes), max_rows=10, budget_tokens=20,
                            row_tokens=lambda n: big.get(n.id, 1))
    assert chunks[0].indices == [0] and chunks[1].oversized == [1] and chunks[1].indices == [1]
    assert chunks[2].indices == [2]
```

- [ ] **Step 2: Падение** — `ImportError: Chunk`.

- [ ] **Step 3: Реализация**

```python
@dataclass(frozen=True, slots=True)
class Chunk:
    root: int
    indices: list[int]
    oversized: list[int] = field(default_factory=list)  # узлы больше бюджета сами по себе → error


def _children(parents: Sequence[int | None], idx: int) -> list[int]:
    return [i for i, p in enumerate(parents) if p == idx]


def _subtree(parents: Sequence[int | None], root: int, n: int) -> list[int]:
    out = [root]
    for i in range(root + 1, n):
        if _is_descendant(parents, i, root):
            out.append(i)
        elif parents[i] is None or not _is_descendant(parents, i, root):
            # дерево по документу: как только встретили узел вне поддерева — конец
            break
    return out


def _is_descendant(parents: Sequence[int | None], i: int, root: int) -> bool:
    p = parents[i]
    while p is not None:
        if p == root:
            return True
        p = parents[p]
    return False


def split_sections(
    nodes: Sequence[TreeNode],
    parents: Sequence[int | None],
    *,
    max_rows: int,
    budget_tokens: int,
    row_tokens: Callable[[TreeNode], int],
) -> list[Chunk]:
    """Рекурсивное деление по разделам (спека §3.3): родительский чанк всегда раньше дочернего."""
    out: list[Chunk] = []
    n = len(nodes)

    def fits(idxs: list[int]) -> bool:
        return len(idxs) <= max_rows and sum(row_tokens(nodes[i]) for i in idxs) <= budget_tokens

    def split(root: int) -> None:
        sub = _subtree(parents, root, n)
        if fits(sub):
            out.append(Chunk(root=root, indices=sub))
            return
        head = [root]
        oversized = [root] if row_tokens(nodes[root]) > budget_tokens else []
        deferred: list[int] = []
        for child in _children(parents, root):
            child_sub = _subtree(parents, child, n)
            if not deferred and fits(head + child_sub):
                head = head + child_sub
            else:
                deferred.append(child)
        out.append(Chunk(root=root, indices=head, oversized=oversized))
        for child in deferred:
            split(child)

    for root in (i for i, p in enumerate(parents) if p is None):
        split(root)
    return out
```
Импорты: `from collections.abc import Callable, Sequence`, `from dataclasses import dataclass, field`. Упростить `_subtree`: цикл с `break` при первом не-потомке (документ упорядочен, поддерево непрерывно).

- [ ] **Step 4: Прогнать, ruff, commit**

```bash
git add backend/app/domain/tree_matching.py backend/tests/test_tree_matching_domain.py
git commit -m "feat(tree): рекурсивное деление сметы на чанки разделов"
```

---

### Task 4: Домен — подсказки, валидация вердиктов, `to_node_match`, соседи

**Files:**
- Modify: `backend/app/domain/tree_matching.py`
- Test: `backend/tests/test_tree_matching_domain.py`

**Interfaces:**
- Produces:
  - `hint_for(node: TreeNode) -> tuple[str, bool] | None` — **единственное** место, где статус строки превращается в подсказку промпта: `confirmed/overridden` → `(final_code, True)`; `confident/matched_fund` **и** `review_status == "unreviewed"` → `(matched_code, True)`; `needs_review` и `unreviewed` → `(matched_code, False)`; `rejected`, `excluded`, `no_match`, `error`, `pending` → `None`. Те же правила доверия, что в `effective_ancestor_context`.
  - `build_hints(chunk_indices: Sequence[int], nodes: Sequence[TreeNode], targets: Collection[int]) -> dict[int, tuple[str, bool]]` — `hint_for` по не-целям с непустым результатом (ключ — `node.id`); целям подсказок нет.
  - `Validated = tuple[NodeVerdict | None, tuple[str, ...]]`; флаги-константы `F_MALFORMED="malformed"`, `F_INCONSISTENT="inconsistent"`, `F_UNKNOWN_CODE="unknown_code"`, `F_OUTSIDE_PARENT="outside_parent"`, `F_MISSING="missing"`.
  - `validate_verdicts(raw: Sequence[object], targets: Collection[int], catalog_codes: Collection[str], ctx_of: Callable[[int], AncestorContext]) -> dict[int, Validated]` — `raw` — список словарей из парсера (`{"i","code","sure","alt"}`) **или** `NodeVerdict`; на выходе — по каждой цели.
  - `validate_one(item: object | None, node_id: int, catalog_codes, ctx: AncestorContext) -> Validated` — то же для одной цели (используется сервисом при обходе сверху вниз).
  - `to_node_match(v: Validated, ctx: AncestorContext, catalog: Mapping[str, CatalogArticle], *, candidates_limit: int = 5) -> NodeMatch`.
  - `neighbors(catalog: Mapping[str, CatalogArticle], code: str, alt_code: str | None, limit: int) -> list[MatchCandidate]`; `children_of(catalog, code) -> list[CatalogArticle]`.
  - `in_subtree(code: str, anc: str) -> bool`.
  - Коды `match_error`: `ERR_MISSING = "tree_missing_verdict"`.

- [ ] **Step 1: Тесты**

```python
from app.domain.entities import CatalogArticle, NodeMatch
from app.domain.tree_matching import (
    F_INCONSISTENT, F_MISSING, F_OUTSIDE_PARENT, F_UNKNOWN_CODE,
    build_hints, neighbors, to_node_match, validate_one, validate_verdicts,
)

CAT = {c.code: c for c in [
    CatalogArticle(1, "4", "Конструктив", None), CatalogArticle(2, "4.2", "Надземная", "4"),
    CatalogArticle(3, "4.2.1", "Гориз 1-й", "4.2"), CatalogArticle(4, "4.2.2", "Верт 1-й", "4.2"),
    CatalogArticle(5, "4.2.3", "Гориз проч", "4.2"), CatalogArticle(6, "9", "Лифты", None),
]}
TRUSTED = AncestorContext("4.2", False)
ROOT = AncestorContext(None, False)
BARRIER = AncestorContext("4.2", True)


def test_hint_for_trust_rules() -> None:
    from app.domain.tree_matching import hint_for
    assert hint_for(_tn(1, 1, "4", status="confident", matched_code="4")) == ("4", True)
    assert hint_for(_tn(1, 1, "4", status="needs_review", matched_code="4", review_status="overridden",
                        final_code="5", final_article_id=5)) == ("5", True)
    assert hint_for(_tn(1, 1, "4", status="needs_review", matched_code="4")) == ("4", False)
    # confident, но оператор отверг → старый код НЕ показывать как [уже: …]
    assert hint_for(_tn(1, 1, "4", status="confident", matched_code="4", review_status="rejected")) is None
    for st in ("excluded", "no_match", "error", "pending"):
        assert hint_for(_tn(1, 1, "4", status=st, matched_code="4")) is None


def test_build_hints_only_for_non_targets() -> None:
    nodes = [_tn(1, 1, "4", status="confident", matched_code="4"),
             _tn(2, 2, "4.1", status="needs_review", matched_code="4.2"),
             _tn(3, 3, "4.1.1", status="excluded"), _tn(4, 3, "4.1.2")]
    assert build_hints([0, 1, 2, 3], nodes, targets={4}) == {1: ("4", True), 2: ("4.2", False)}


def test_validate_flags() -> None:
    codes = set(CAT)
    assert validate_one({"i": 1, "code": "4.2.1", "sure": True, "alt": "4.2.3"}, 1, codes, TRUSTED)[1] == ()
    assert F_UNKNOWN_CODE in validate_one({"i": 1, "code": "77", "sure": True, "alt": None}, 1, codes, TRUSTED)[1]
    assert F_INCONSISTENT in validate_one({"i": 1, "code": None, "sure": True, "alt": None}, 1, codes, TRUSTED)[1]
    assert F_INCONSISTENT in validate_one({"i": 1, "code": "4.2.1", "sure": True, "alt": None, "kind": "org"}, 1, codes, TRUSTED)[1]
    assert F_OUTSIDE_PARENT in validate_one({"i": 1, "code": "9", "sure": True, "alt": None}, 1, codes, TRUSTED)[1]
    assert validate_one({"i": 1, "code": "9", "sure": True, "alt": None}, 1, codes, ROOT)[1] == ()  # корень: нет проверки
    assert validate_one({"i": 1, "code": "4", "sure": True, "alt": None}, 1, codes, TRUSTED)[1] == ()  # роллап вверх допустим
    assert validate_one(None, 1, codes, TRUSTED) == (None, (F_MISSING,))
    v, flags = validate_one({"i": 1, "code": "4.2.1", "sure": "yes", "alt": "4.2.1"}, 1, codes, TRUSTED)
    assert "malformed" in flags


def test_validate_many_ignores_foreign_and_duplicates() -> None:
    raw = [{"i": 9, "code": "4", "sure": True}, {"i": 1, "code": "4.2.1", "sure": True},
           {"i": 1, "code": "4.2.2", "sure": True}]
    out = validate_verdicts(raw, targets={1, 2}, catalog_codes=set(CAT), ctx_of=lambda i: TRUSTED)
    assert out[1][0].article_code == "4.2.1" and out[2] == (None, (F_MISSING,))
    assert 9 not in out


def test_to_node_match_matrix() -> None:
    ok = validate_one({"i": 1, "code": "4.2.1", "sure": True, "alt": "4.2.3"}, 1, set(CAT), TRUSTED)
    m = to_node_match(ok, TRUSTED, CAT)
    assert m.status == "confident" and m.matched_code == "4.2.1" and m.matched_id == 3
    assert [c.code for c in m.candidates][:2] == ["4.2.1", "4.2.3"] and all(c.score is None for c in m.candidates)
    assert to_node_match(ok, BARRIER, CAT).status == "needs_review"          # барьер гасит sure
    unsure = validate_one({"i": 1, "code": "4.2.1", "sure": False, "alt": None}, 1, set(CAT), TRUSTED)
    assert to_node_match(unsure, TRUSTED, CAT).status == "needs_review"
    org = validate_one({"i": 1, "code": "org", "sure": True, "alt": None}, 1, set(CAT), TRUSTED)
    assert to_node_match(org, TRUSTED, CAT).status == "excluded"
    none = validate_one({"i": 1, "code": "none", "sure": True, "alt": None}, 1, set(CAT), TRUSTED)
    assert to_node_match(none, TRUSTED, CAT).status == "no_match"
    unk = validate_one({"i": 1, "code": "77", "sure": True, "alt": None}, 1, set(CAT), TRUSTED)
    m = to_node_match(unk, TRUSTED, CAT)
    assert m.status == "needs_review" and m.matched_code is None
    assert {c.code for c in m.candidates} == {"4.2", "4.2.1", "4.2.2", "4.2.3"}  # дети trusted + сама
    miss = to_node_match((None, (F_MISSING,)), TRUSTED, CAT)
    assert miss.status == "error" and miss.match_error == "tree_missing_verdict"


def test_neighbors_order_and_limit() -> None:
    c = neighbors(CAT, "4.2.1", "4.2.3", limit=5)
    assert [x.code for x in c] == ["4.2.1", "4.2.3", "4.2.2", "4.2"]  # выбранная, альт, сёстры, родитель
```

- [ ] **Step 2: Падение** — `ImportError`.

- [ ] **Step 3: Реализация**

```python
F_MALFORMED = "malformed"
F_INCONSISTENT = "inconsistent"
F_UNKNOWN_CODE = "unknown_code"
F_OUTSIDE_PARENT = "outside_parent"
F_MISSING = "missing"
ERR_MISSING = "tree_missing_verdict"
_KINDS = ("article", "org", "none")
Validated = tuple[NodeVerdict | None, tuple[str, ...]]


def in_subtree(code: str, anc: str) -> bool:
    return code == anc or code.startswith(anc + ".")


def hint_for(node: TreeNode) -> tuple[str, bool] | None:
    """Подсказка промпта по строке: (код, trusted). Правила доверия = effective_ancestor_context."""
    if node.review_status in REVIEWED_STATUSES and node.final_code:
        return (node.final_code, True)
    if node.review_status != "unreviewed":
        return None  # rejected: старый AI-код не показываем
    if node.status in TRUSTED_STATUSES and node.matched_code:
        return (node.matched_code, True)
    if node.status in UNCERTAIN_STATUSES and node.matched_code:
        return (node.matched_code, False)
    return None


def build_hints(
    chunk_indices: Sequence[int], nodes: Sequence[TreeNode], targets: Collection[int]
) -> dict[int, tuple[str, bool]]:
    hints: dict[int, tuple[str, bool]] = {}
    for i in chunk_indices:
        n = nodes[i]
        if n.id in targets:
            continue
        h = hint_for(n)
        if h is not None:
            hints[n.id] = h
    return hints


def _coerce(item: object, node_id: int) -> tuple[NodeVerdict | None, tuple[str, ...]]:
    """dict из парсера или NodeVerdict → NodeVerdict; ошибки типов → malformed."""
    if isinstance(item, NodeVerdict):
        return item, ()
    if not isinstance(item, dict):
        return None, (F_MALFORMED,)
    code = item.get("code")
    sure = item.get("sure")
    alt = item.get("alt")
    kind = item.get("kind")
    if code in ("org", "none"):
        kind, code = code, None
    elif kind is None:
        kind = "article"
    if kind not in _KINDS or not isinstance(sure, bool) or not (code is None or isinstance(code, str)) \
            or not (alt is None or isinstance(alt, str)):
        return None, (F_MALFORMED,)
    return NodeVerdict(node_id=node_id, kind=kind, article_code=code, sure=sure, alt_code=alt), ()


def validate_one(
    item: object | None, node_id: int, catalog_codes: Collection[str], ctx: AncestorContext
) -> Validated:
    if item is None:
        return None, (F_MISSING,)
    v, flags = _coerce(item, node_id)
    if v is None:
        return None, flags
    flags_l = list(flags)
    if (v.kind == "article") != (v.article_code is not None):
        flags_l.append(F_INCONSISTENT)
    elif v.article_code is not None and v.article_code not in catalog_codes:
        flags_l.append(F_UNKNOWN_CODE)
    elif v.article_code is not None and ctx.trusted_code is not None \
            and not in_subtree(v.article_code, ctx.trusted_code) \
            and not in_subtree(ctx.trusted_code, v.article_code):
        flags_l.append(F_OUTSIDE_PARENT)
    alt = v.alt_code if v.alt_code in catalog_codes and v.alt_code != v.article_code else None
    if alt != v.alt_code:
        v = replace(v, alt_code=alt)
    return v, tuple(flags_l)


def validate_verdicts(
    raw: Sequence[object], targets: Collection[int], catalog_codes: Collection[str],
    ctx_of: Callable[[int], AncestorContext],
) -> dict[int, Validated]:
    first: dict[int, object] = {}
    for item in raw:
        nid = item.node_id if isinstance(item, NodeVerdict) else (item.get("i") if isinstance(item, dict) else None)
        if not isinstance(nid, int) or nid not in targets:
            continue
        if nid in first:
            logger.warning("tree: дубликат вердикта для узла %s — взят первый", nid)
            continue
        first[nid] = item
    return {t: validate_one(first.get(t), t, catalog_codes, ctx_of(t)) for t in targets}


def children_of(catalog: Mapping[str, CatalogArticle], code: str) -> list[CatalogArticle]:
    return [a for a in catalog.values() if a.parent_code == code]


def _cand(a: CatalogArticle) -> MatchCandidate:
    return MatchCandidate(id=a.id, code=a.code, name=a.name, score=None)


def neighbors(
    catalog: Mapping[str, CatalogArticle], code: str, alt_code: str | None, limit: int
) -> list[MatchCandidate]:
    chosen = catalog[code]
    order: list[CatalogArticle] = [chosen]
    if alt_code and alt_code in catalog:
        order.append(catalog[alt_code])
    if chosen.parent_code:
        order += [s for s in children_of(catalog, chosen.parent_code) if s not in order]
        order.append(catalog[chosen.parent_code]) if chosen.parent_code in catalog else None
    seen: set[str] = set()
    out = []
    for a in order:
        if a.code not in seen:
            seen.add(a.code)
            out.append(_cand(a))
    return out[:limit]


def to_node_match(
    v: Validated, ctx: AncestorContext, catalog: Mapping[str, CatalogArticle], *, candidates_limit: int = 5
) -> NodeMatch:
    verdict, flags = v
    if F_MISSING in flags:
        return NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_MISSING)
    if verdict is None or F_MALFORMED in flags or F_INCONSISTENT in flags or F_UNKNOWN_CODE in flags:
        cands = []
        if ctx.trusted_code and ctx.trusted_code in catalog:
            cands = [_cand(catalog[ctx.trusted_code])] + [_cand(a) for a in children_of(catalog, ctx.trusted_code)]
        return NodeMatch(EstimateRowStatus.NEEDS_REVIEW, candidates=cands[:candidates_limit])
    if verdict.kind == "org":
        return NodeMatch(EstimateRowStatus.EXCLUDED)
    if verdict.kind == "none":
        return NodeMatch(EstimateRowStatus.NO_MATCH)
    art = catalog[verdict.article_code]  # type: ignore[index]  # unknown_code отсечён выше
    cands = neighbors(catalog, art.code, verdict.alt_code, candidates_limit)
    status = (
        EstimateRowStatus.CONFIDENT
        if verdict.sure and not flags and not ctx.has_uncertain_barrier
        else EstimateRowStatus.NEEDS_REVIEW
    )
    return NodeMatch(status, matched_id=art.id, matched_code=art.code, matched_name=art.name,
                     score=None, candidates=cands)
```
Импорты: `logging`, `Collection`, `Mapping`, `replace`, `EstimateRowStatus`, `MatchCandidate`, `NodeMatch`, `NodeVerdict`, `CatalogArticle`. `logger = logging.getLogger(__name__)`. Убрать тернарник с побочным эффектом у `order.append(...)` — записать обычным `if`.

- [ ] **Step 4: Прогнать, ruff, commit**

```bash
git add backend/app/domain/tree_matching.py backend/tests/test_tree_matching_domain.py
git commit -m "feat(tree): валидация вердиктов, маппинг в NodeMatch, структурные кандидаты"
```

---

### Task 5: Настройки движка

**Files:**
- Modify: `backend/app/core/config.py` (после `match_top_k`, строка ~28; валидатор после `match_top_k` проверки, строка ~107)
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings.matching_engine: str = "rag"`, `openrouter_tree_model: str = "anthropic/claude-sonnet-5"`, `tree_reasoning_effort: str = "low"`, `tree_context_window: int = 200_000`, `tree_chunk_rows: int = 120`, `tree_min_chunk_rows: int = 10`, `tree_output_reserve_per_row: int = 48`, `tree_precedents_budget: int = 2_000`.

- [ ] **Step 1: Тесты**

```python
def test_tree_engine_defaults() -> None:
    from app.core.config import Settings

    s = Settings()  # env из conftest
    assert s.matching_engine == "rag"
    assert s.openrouter_tree_model == "anthropic/claude-sonnet-5"
    assert s.tree_reasoning_effort == "low"
    assert (s.tree_context_window, s.tree_chunk_rows, s.tree_min_chunk_rows) == (200_000, 120, 10)
    assert (s.tree_output_reserve_per_row, s.tree_precedents_budget) == (48, 2_000)


@pytest.mark.parametrize("env,value", [
    ("MATCHING_ENGINE", "vector"), ("TREE_CONTEXT_WINDOW", "0"), ("TREE_CHUNK_ROWS", "0"),
    ("TREE_MIN_CHUNK_ROWS", "500"), ("OPENROUTER_TREE_MODEL", "  "),
])
def test_tree_engine_validation(monkeypatch: pytest.MonkeyPatch, env: str, value: str) -> None:
    from app.core.config import Settings

    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
```

- [ ] **Step 2: Падение** — `AttributeError: matching_engine` / валидация не срабатывает.

- [ ] **Step 3: Реализация**

В `Settings` после `match_top_k`:
```python
    # Движок сопоставления (спека tree matching 2026-08-27): "rag" (текущий) | "tree".
    matching_engine: str = "rag"
    openrouter_tree_model: str = "anthropic/claude-sonnet-5"
    tree_reasoning_effort: str = "low"     # без ограничения Sonnet 5 давал ×3 completion-токенов
    tree_context_window: int = 200_000     # окно модели, задаётся явно
    tree_chunk_rows: int = 120
    tree_min_chunk_rows: int = 10
    tree_output_reserve_per_row: int = 48
    tree_precedents_budget: int = 2_000
```
В валидаторе (рядом с проверкой `match_top_k`):
```python
        if self.matching_engine not in ("rag", "tree"):
            raise ValueError("MATCHING_ENGINE должен быть 'rag' или 'tree'")
        if not self.openrouter_tree_model.strip():
            raise ValueError("OPENROUTER_TREE_MODEL не может быть пустым")
        if self.tree_context_window <= 0 or self.tree_chunk_rows <= 0:
            raise ValueError("TREE_CONTEXT_WINDOW и TREE_CHUNK_ROWS должны быть > 0")
        if not 1 <= self.tree_min_chunk_rows <= self.tree_chunk_rows:
            raise ValueError("TREE_MIN_CHUNK_ROWS должен быть в [1, TREE_CHUNK_ROWS]")
        if self.tree_output_reserve_per_row <= 0 or self.tree_precedents_budget < 0:
            raise ValueError("TREE_OUTPUT_RESERVE_PER_ROW > 0, TREE_PRECEDENTS_BUDGET >= 0")
```

- [ ] **Step 4: Прогнать, commit**

Run: `cd backend; uv run pytest tests/test_config.py -q`
```bash
git add backend/app/core/config.py backend/tests/test_config.py
git commit -m "feat(tree): настройки matching_engine и tree_*"
```

---

### Task 6: Репозитории — `fetch_tree`, `refresh_tree_node`, `save_node_match_cas`, `list_catalog` (SQLAlchemy + фейки)

**Files:**
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (после `save_node_match`, строка ~346)
- Modify: `backend/app/infrastructure/db/article_repository.py` (после `ancestor_names_by_ids`)
- Modify: `backend/tests/fakes.py` (`FakeEstimateRepository.create` — узлы получают `code/name/depth/source_index`; методы; `FakeArticleRepository.list_catalog`)
- Test: `backend/tests/test_estimate_repo_cas.py` (зеркало контракта через фейк), `backend/tests/test_estimate_lock_integration.py`-стиль интеграционный тест в новом `backend/tests/test_tree_repository_integration.py` (skip без `TEST_DATABASE_URL`)

**Interfaces:**
- Consumes: сигнатуры из Task 1.
- Produces: реализации; фейк хранит в `self.nodes[nid]` дополнительно `code`, `name`, `depth`, `source_index`.

- [ ] **Step 1: Тесты фейка (зеркало SQL-контракта)**

В `tests/test_estimate_repo_cas.py`:
```python
def test_save_node_match_cas_requires_expected_status_and_unreviewed() -> None:
    from app.domain.entities import EstimateRowStatus, NodeMatch
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    n1, n2 = (r.id for r in est.rows)
    res = NodeMatch(EstimateRowStatus.CONFIDENT, matched_id=1, matched_code="1", matched_name="x")
    assert repo.save_node_match_cas(n1, res, ("pending",)) is True
    assert repo.save_node_match_cas(n1, res, ("pending",)) is False       # уже confident
    assert repo.save_node_match_cas(n1, res, ("pending", "confident")) is True
    repo.save_review_decision(n2, review_status="confirmed", final_article_id=1, final_code="1", final_name="x")
    assert repo.save_node_match_cas(n2, res, ("pending",)) is False       # ревью


def test_fetch_tree_and_refresh() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1"), _node("1.1")])
    tree = repo.fetch_tree(est.id)
    assert [t.code for t in tree] == ["1", "1.1"] and tree[0].depth == 1 and tree[1].depth == 2
    repo.save_review_decision(tree[1].id, review_status="overridden", final_article_id=7, final_code="7", final_name="z")
    fresh = repo.refresh_tree_node(tree[1].id)
    assert fresh.final_code == "7" and fresh.final_article_id == 7 and fresh.review_status == "overridden"
```
(`_node` в этом файле должен задавать `depth` = число сегментов и `source_index` по порядку — проверить существующий хелпер, при необходимости передавать явно.)

- [ ] **Step 2: Падение.**

- [ ] **Step 3: Фейк**

В `FakeEstimateRepository.create` добавить в словарь узла: `"code": n.code, "name": n.name, "depth": n.depth, "source_index": n.source_index`. Методы:
```python
    def _tree_node(self, n: dict) -> TreeNode:
        return TreeNode(
            id=n["id"], source_index=n["source_index"], depth=n["depth"], code=n["code"],
            name=n["name"], status=n["status"], review_status=n["review_status"],
            matched_code=n["matched_code"], matched_article_id=n["matched_article_id"],
            final_code=n["final_code"], final_article_id=n["final_article_id"],
        )

    def fetch_tree(self, estimate_id: int) -> list[TreeNode]:
        rows = sorted(
            (n for n in self.nodes.values() if n["estimate_id"] == estimate_id),
            key=lambda n: n["source_index"],
        )
        return [self._tree_node(n) for n in rows]

    def refresh_tree_node(self, node_id: int) -> TreeNode:
        return self._tree_node(self.nodes[node_id])

    def save_node_match_cas(
        self, node_id: int, result: NodeMatch, expected_statuses: Sequence[str]
    ) -> bool:
        n = self.nodes[node_id]
        if n["review_status"] != "unreviewed" or n["status"] not in expected_statuses:
            return False
        self.save_node_match(node_id, result)
        return True
```
`FakeArticleRepository.list_catalog` — из своего хранилища; `parent_code = ".".join(code.split(".")[:-1]) or None`.

- [ ] **Step 4: SQLAlchemy**

`estimate_repository.py` — выбирать **только нужные колонки** (полная модель тянет `embedding`: ~3 КБ на строку, на 3 000 строк ~9 МБ):
```python
_TREE_COLUMNS = (
    EstimateRowModel.id, EstimateRowModel.source_index, EstimateRowModel.depth,
    EstimateRowModel.code, EstimateRowModel.name, EstimateRowModel.status,
    EstimateRowModel.review_status, EstimateRowModel.matched_code,
    EstimateRowModel.matched_article_id, EstimateRowModel.final_code,
    EstimateRowModel.final_article_id,
)


def _row_to_tree_node(r) -> TreeNode:  # r — sqlalchemy Row с колонками _TREE_COLUMNS
    return TreeNode(
        id=r.id, source_index=r.source_index, depth=r.depth, code=r.code, name=r.name,
        status=r.status, review_status=r.review_status, matched_code=r.matched_code,
        matched_article_id=r.matched_article_id, final_code=r.final_code,
        final_article_id=r.final_article_id,
    )


class SqlAlchemyEstimateRepository(EstimateRepository):
    ...
    def fetch_tree(self, estimate_id: int) -> list[TreeNode]:
        stmt = (
            select(*_TREE_COLUMNS)
            .where(EstimateRowModel.estimate_id == estimate_id)
            .order_by(EstimateRowModel.source_index)
        )
        return [_row_to_tree_node(r) for r in self._session.execute(stmt)]

    def refresh_tree_node(self, node_id: int) -> TreeNode:
        # чужой коммит (ревью оператора) — SELECT идёт в БД, кэш сессии не участвует (колонки, не ORM)
        r = self._session.execute(
            select(*_TREE_COLUMNS).where(EstimateRowModel.id == node_id)
        ).one_or_none()
        if r is None:
            raise KeyError(node_id)
        return _row_to_tree_node(r)

    def save_node_match_cas(
        self, node_id: int, result: NodeMatch, expected_statuses: Sequence[str]
    ) -> bool:
        res = self._session.execute(
            update(EstimateRowModel)
            .where(
                EstimateRowModel.id == node_id,
                EstimateRowModel.status.in_(tuple(expected_statuses)),
                EstimateRowModel.review_status == "unreviewed",
            )
            .values(**self._match_values(result))
        )
        self._session.commit()
        return res.rowcount > 0
```
`article_repository.py`:
```python
    def list_catalog(self) -> list[CatalogArticle]:
        rows = self._session.execute(
            select(TemplateArticleModel.id, TemplateArticleModel.article_code,
                   TemplateArticleModel.name, TemplateArticleModel.parent_id).order_by(_CODE_ORDER)
        ).all()
        code_by_id = {r.id: r.article_code for r in rows}
        return [
            CatalogArticle(id=r.id, code=r.article_code, name=r.name,
                           parent_code=code_by_id.get(r.parent_id) if r.parent_id else None)
            for r in rows
        ]
```

- [ ] **Step 5: Интеграционный тест (skip без `TEST_DATABASE_URL`)**

`tests/test_tree_repository_integration.py` по образцу `test_decision_fund_repository_integration.py`: создать смету с двумя строками, `save_node_match_cas` → `True`, повтор с неподходящим `expected` → `False`, `save_review_decision` + CAS → `False`; `fetch_tree` порядок по `source_index`; `list_catalog` отдаёт `parent_code` по `parent_id`. Чистка в `finally`.

- [ ] **Step 6: Прогнать всё, ruff, commit**

```bash
git add backend/app/infrastructure/db/estimate_repository.py backend/app/infrastructure/db/article_repository.py backend/tests/fakes.py backend/tests/test_estimate_repo_cas.py backend/tests/test_tree_repository_integration.py
git commit -m "feat(tree): fetch_tree/refresh/save_node_match_cas и list_catalog"
```

---

### Task 7: Промпт и парсер ответа

**Files:**
- Create: `backend/app/infrastructure/ai/tree_prompt.py`
- Test: `backend/tests/test_tree_prompt.py`

**Interfaces:**
- Produces: `SYSTEM_PROMPT: str`; `render_catalog(catalog: Sequence[CatalogArticle]) -> str`; `render_precedents(precedents) -> str` (пустая строка при пустом списке); `render_ancestors(ancestors) -> str`; `render_fragment(req: SectionMatchRequest) -> str`; `build_user_prompt(req) -> str`; `parse_verdicts(text: str) -> list[dict] | None` (`None` — JSON не разобран).

- [ ] **Step 1: Тесты**

```python
from app.domain.entities import CatalogArticle, SectionMatchRequest
from app.infrastructure.ai.tree_prompt import (
    SYSTEM_PROMPT, build_user_prompt, parse_verdicts, render_catalog,
)


def test_render_catalog_indents_by_depth() -> None:
    cat = [CatalogArticle(1, "4", "Конструктив", None), CatalogArticle(2, "4.2", "Надземная", "4")]
    assert render_catalog(cat) == "(4) Конструктив\n  (4.2) Надземная"


def test_user_prompt_has_sections_hints_and_explicit_targets() -> None:
    nodes = [_tn(1, 1, "6", name="Фасады"), _tn(2, 2, "6.1", name="1 Этап"),
             _tn(3, 3, "6.1.1", name="Прочее"), _tn(4, 3, "6.1.2", name="Каркас", status="excluded"),
             _tn(5, 3, "6.1.3", name="Снято", status="confident", matched_code="6", review_status="rejected")]
    req = SectionMatchRequest(nodes=nodes, ancestors=[], hints={2: ("6", True), 3: ("6.99", False)},
                              targets=frozenset({1}), catalog=[CatalogArticle(1, "6", "Фасады", None)],
                              precedents=[])
    p = build_user_prompt(req)
    assert "СПРАВОЧНИК:" in p and "ФРАГМЕНТ" in p and "ПРЕЦЕДЕНТЫ" not in p and "КОНТЕКСТ" not in p
    assert "[цель] 1 | 6 | Фасады" in p and "  2 | 6.1 | 1 Этап  [уже: 6]" in p
    assert "[предположительно: 6.99]" in p
    # не-цели без кода (excluded, rejected) помечены как контекст — модель по ним не отвечает
    assert "[контекст] 4 | 6.1.2 | Каркас" in p and "[контекст] 5 | 6.1.3 | Снято" in p
    assert "ЦЕЛИ (ответить только по ним): 1" in p
    assert "СПРАВОЧНИК" not in build_user_prompt(req, include_catalog=False)


def test_render_ancestors_shows_trust() -> None:
    from app.infrastructure.ai.tree_prompt import render_ancestors
    a = _tn(1, 1, "4", name="Конструктив"); b = _tn(2, 2, "4.1", name="Этап"); c = _tn(3, 3, "4.1.1", name="Плиты")
    out = render_ancestors([(a, ("4", True)), (b, None), (c, ("4.2", False))])
    assert "4 | Конструктив -> 4" in out and "4.1 | Этап -> ?" in out and "4.1.1 | Плиты -> 4.2 (предположительно)" in out


def test_system_prompt_pins_format_rules() -> None:
    for token in ('"sure"', '"alt"', "org", "none", "X.99", "[уже:", "[цель]", "[контекст]"):
        assert token in SYSTEM_PROMPT


def test_parse_verdicts() -> None:
    assert parse_verdicts('```json\n[{"i": 1, "code": "4.2", "sure": true, "alt": null}]\n```') == [
        {"i": 1, "code": "4.2", "sure": True, "alt": None}]
    assert parse_verdicts("нет массива") is None
    assert parse_verdicts('[{"i": 1, "code": "4.2", "sure": true') is None   # обрезан
    assert parse_verdicts('{"a": 1}') is None                                # не массив
    # две пары скобок в тексте: берётся первый ДЕКОДИРУЕМЫЙ массив, а не жадный срез
    assert parse_verdicts('Список [см. раздел 4] ниже: [{"i": 1, "code": "4", "sure": false, "alt": null}] конец') == [
        {"i": 1, "code": "4", "sure": False, "alt": None}]
```

- [ ] **Step 2: Падение.**

- [ ] **Step 3: Реализация**

```python
"""Промпт tree-движка и разбор ответа (спека 2026-08-27 §5.1). Единая семантика для провайдеров."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from app.domain.entities import CatalogArticle, FundPrecedent, SectionMatchRequest, TreeNode

SYSTEM_PROMPT = (
    "Ты — эксперт по строительным сметам. Тебе дают ИЕРАРХИЧЕСКИЙ справочник статей СМР "
    "(код и наименование, вложенность по коду) и ФРАГМЕНТ сметы — раздел с его подстроками, "
    "с отступами по вложенности. Задача: каждой строке-цели назначить код статьи справочника.\n"
    "Правила:\n"
    "1. Учитывай структуру: статья строки, как правило, лежит внутри статьи её родителя "
    "(или совпадает с ней), а соседние строки часто идут в том же порядке, что статьи справочника.\n"
    "2. Если строка — ТОЛЬКО организационный каркас (этап, очередь, корпус, секция, ЖК/БЦ, "
    "'1 Этап ЖК', '2 Этап БЦ' и т.п.) без обозначения работы — ответ \"org\". Если же строка "
    "называет вид работ или дисциплину, пусть даже с хвостом этапа ('Механические системы 1 Этап ЖК', "
    "'Устройство кровли', заголовок раздела) — это НЕ org: дай ей статью-раздел справочника. "
    "Строки-корпуса ВНУТРИ работы ('Корпус № 1; 6' под 'Гидроизоляция плиты') — это разбивка "
    "работы: дай им статью родителя.\n"
    "2а. Строка 'Прочее' внутри раздела — это 'Прочее (...)' ЭТОГО раздела (код вида X.99), "
    "а не корневое.\n"
    "3. Если смета дробит работу мельче справочника — дай детям статью, которой соответствует "
    "ближайший подходящий предок (роллап).\n"
    "4. Если работа реальная, но статьи для неё в справочнике нет — \"none\". "
    "Не выбирай 'Прочее' лишь потому, что не уверен.\n"
    "5. Отвечай ТОЛЬКО по строкам с пометкой [цель] (их id перечислены в блоке ЦЕЛИ). "
    "Строки [контекст] и строки с [уже: код] — только опора: по ним не отвечать. "
    "Пометка [предположительно: код] — неподтверждённая догадка, опирайся на неё осторожно.\n"
    "6. Блок ПРЕЦЕДЕНТЫ (если есть) — как операторы решали такие же строки раньше; "
    "при совпадении контекста следуй им.\n"
    "7. Поле \"sure\": true — только если уверен без оговорок; иначе false и укажи в \"alt\" "
    "второй по вероятности код (или null).\n"
    "Ответ — СТРОГО JSON-массив объектов "
    "{\"i\": <номер строки>, \"code\": \"<код|org|none>\", \"sure\": true|false, \"alt\": \"<код>\"|null} "
    "для КАЖДОЙ строки [цель], без преамбулы и markdown."
)


def render_catalog(catalog: Sequence[CatalogArticle]) -> str:
    return "\n".join(f"{'  ' * a.code.count('.')}({a.code}) {a.name}" for a in catalog)


def render_precedents(precedents: Sequence[FundPrecedent]) -> str:
    if not precedents:
        return ""
    lines = [
        f"{p.name} | в разделе ({p.parent_article_code or '—'}) → ({p.article_code}) {p.article_name} — {p.votes} решений"
        for p in precedents
    ]
    return "ПРЕЦЕДЕНТЫ (решения операторов по таким же строкам):\n" + "\n".join(lines) + "\n\n"


def render_ancestors(ancestors: Sequence[tuple[TreeNode, tuple[str, bool] | None]]) -> str:
    if not ancestors:
        return ""
    lines = []
    for n, hint in ancestors:
        if hint is None:
            shown = "?"
        else:
            code, trusted = hint
            shown = code if trusted else f"{code} (предположительно)"
        lines.append(f"  {n.code} | {n.name} -> {shown}")
    return "КОНТЕКСТ (предки фрагмента и их статьи):\n" + "\n".join(lines) + "\n\n"


def render_fragment(req: SectionMatchRequest) -> str:
    base = req.nodes[0].depth
    lines = []
    for n in req.nodes:
        indent = "  " * (n.depth - base)
        if n.id in req.targets:
            lines.append(f"{indent}[цель] {n.id} | {n.code} | {n.name}")
            continue
        hint = req.hints.get(n.id)
        if hint is None:
            lines.append(f"{indent}[контекст] {n.id} | {n.code} | {n.name}")
        else:
            code, trusted = hint
            tag = f"[уже: {code}]" if trusted else f"[предположительно: {code}]"
            lines.append(f"{indent}{n.id} | {n.code} | {n.name}  {tag}")
    return "\n".join(lines)


def build_user_prompt(req: SectionMatchRequest, *, include_catalog: bool = True) -> str:
    catalog = f"СПРАВОЧНИК:\n{render_catalog(req.catalog)}\n\n" if include_catalog else ""
    targets = ", ".join(str(n.id) for n in req.nodes if n.id in req.targets)
    return (
        f"{catalog}{render_precedents(req.precedents)}{render_ancestors(req.ancestors)}"
        f"ФРАГМЕНТ СМЕТЫ (номер | код раздела | наименование):\n{render_fragment(req)}\n\n"
        f"ЦЕЛИ (ответить только по ним): {targets}"
    )


_DECODER = json.JSONDecoder()


def parse_verdicts(text: str) -> list[dict] | None:
    """Первый ДЕКОДИРУЕМЫЙ JSON-массив словарей в тексте (не жадный срез: «[см. раздел 4]» пропускается)."""
    pos = text.find("[")
    while pos != -1:
        try:
            data, _ = _DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("[", pos + 1)
            continue
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return data
        pos = text.find("[", pos + 1)
    return None
```

- [ ] **Step 4: Прогнать, ruff, commit**

```bash
git add backend/app/infrastructure/ai/tree_prompt.py backend/tests/test_tree_prompt.py
git commit -m "feat(tree): промпт по разделу и разбор JSON-вердиктов"
```

---

### Task 8: Адаптер `OpenRouterTreeMatcher`

**Files:**
- Create: `backend/app/infrastructure/ai/openrouter_tree_matcher.py`
- Test: `backend/tests/test_openrouter_tree_matcher.py`

**Interfaces:**
- Consumes: `SYSTEM_PROMPT`, `build_user_prompt`, `parse_verdicts` (Task 7); `instrumented_call`, `_is_transient`-логика (скопировать из `openrouter_matcher.py` — общая функция вынесена не будет, YAGNI до второго провайдера).
- Produces: `OpenRouterTreeMatcher(api_key, base_url="https://openrouter.ai/api/v1", model="anthropic/claude-sonnet-5", *, reasoning_effort="low", output_reserve_per_row=48, client=None, timeout_s=300.0, retry_budget=3)` реализует `TreeMatcher.match_section -> SectionMatchResponse` (Task 1): адаптер отдаёт **сырые словари** `{"i","code","sure","alt"}` — валидирует домен (fail-closed). Невалидный JSON при `stop` → `items=[]`, `truncated=False` → все цели `missing`; `finish_reason == "length"` → `truncated=True`.

- [ ] **Step 1: Тесты** (`_FakeClient`/`_FakeResponse` как в `test_openrouter_matcher.py`)

```python
def _req() -> SectionMatchRequest:
    nodes = [_tn(1, 1, "4", name="Конструктив"), _tn(2, 2, "4.1", name="Плита")]
    return SectionMatchRequest(nodes=nodes, ancestors=[], hints={}, targets=frozenset({1, 2}),
                               catalog=[CatalogArticle(1, "4", "Конструктив", None)], precedents=[])


def _ok(text: str, finish: str = "stop") -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


def test_sends_cached_system_block_reasoning_and_max_tokens() -> None:
    client = _FakeClient(data=_ok('[{"i":1,"code":"4","sure":true,"alt":null}]'))
    m = OpenRouterTreeMatcher(api_key="k", client=client, output_reserve_per_row=48)
    resp = m.match_section(_req())
    assert resp.items == [{"i": 1, "code": "4", "sure": True, "alt": None}] and not resp.truncated
    body = client.calls[0]["json"]
    assert body["temperature"] == 0 and body["reasoning"] == {"effort": "low"}
    assert body["max_tokens"] == 2 * 48 + 512
    sys_msg = body["messages"][0]
    assert sys_msg["role"] == "system"
    assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "СПРАВОЧНИК" in sys_msg["content"][0]["text"]        # справочник — в кэшируемом префиксе
    assert "ФРАГМЕНТ" in body["messages"][1]["content"]


def test_truncated_response_flagged() -> None:
    client = _FakeClient(data=_ok('[{"i":1,"code":"4","sure":tr', finish="length"))
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.truncated is True and resp.items == []


def test_invalid_json_on_stop_gives_empty_items() -> None:
    client = _FakeClient(data=_ok("извините, не могу"))
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.items == [] and resp.truncated is False


def test_transport_error_exhausts_to_transient() -> None:
    client = _FakeClient(exc=httpx.ConnectError("boom"))
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=2)
    with patch("app.infrastructure.retry.time.sleep"):
        with pytest.raises(TransientError):
            m.match_section(_req())
```

- [ ] **Step 2: Падение.**

- [ ] **Step 3: Реализация**

```python
"""TreeMatcher через OpenRouter chat/completions (спека §5.1)."""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import SectionMatchRequest, SectionMatchResponse
from app.domain.ports import TreeMatcher
from app.infrastructure.ai._instrumented import instrumented_call
from app.infrastructure.ai.tree_prompt import SYSTEM_PROMPT, build_user_prompt, parse_verdicts, render_catalog

logger = logging.getLogger(__name__)
_REFERER = "https://github.com/zhukovvlad/ciw-tenders"
_TITLE = "CIW Tree Matcher"
_OUTPUT_MARGIN = 512


class _BodyError(Exception):
    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, _BodyError) and exc.transient


class OpenRouterTreeMatcher(TreeMatcher):
    def __init__(
        self, api_key: str, base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-sonnet-5", *, reasoning_effort: str = "low",
        output_reserve_per_row: int = 48, client: httpx.Client | None = None,
        timeout_s: float = 300.0, retry_budget: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._effort = reasoning_effort
        self._reserve = output_reserve_per_row
        self._budget = retry_budget
        self._client = client or httpx.Client(timeout=timeout_s)

    def match_section(self, req: SectionMatchRequest) -> SectionMatchResponse:
        # справочник — в system-блоке с cache_control: одинаков для всех чанков сметы
        system_text = f"{SYSTEM_PROMPT}\n\nСПРАВОЧНИК:\n{render_catalog(req.catalog)}"
        user_text = build_user_prompt(req, include_catalog=False)
        max_tokens = len(req.targets) * self._reserve + _OUTPUT_MARGIN
        return instrumented_call(
            provider="openrouter", model=self._model,
            fn=lambda: self._call(system_text, user_text, max_tokens),
            budget=self._budget, classify=_is_transient,
        )
```
```python
    def _call(self, system_text: str, user_text: str, max_tokens: int) -> SectionMatchResponse:
        resp = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json",
                     "HTTP-Referer": _REFERER, "X-Title": _TITLE},
            json={
                "model": self._model, "temperature": 0, "max_tokens": max_tokens,
                "reasoning": {"effort": self._effort},
                "messages": [
                    {"role": "system",
                     "content": [{"type": "text", "text": system_text,
                                  "cache_control": {"type": "ephemeral"}}]},
                    {"role": "user", "content": user_text},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if (error := data.get("error")) is not None:
            code = error.get("code")
            transient = code == 429 or (isinstance(code, int) and code >= 500)
            raise _BodyError(f"OpenRouter error (code={code}): {error.get('message', '')}", transient=transient)
        choices = data.get("choices")
        if not choices:
            raise _BodyError("OpenRouter: ответ без choices", transient=True)
        try:
            content = choices[0]["message"]["content"] or ""
            finish = choices[0].get("finish_reason")
        except (KeyError, IndexError, TypeError) as exc:
            raise _BodyError(f"OpenRouter: неожиданная структура ответа: {exc}", transient=False) from exc
        if finish == "length":
            logger.warning("tree: ответ обрезан по max_tokens=%d", max_tokens, extra={"model": self._model})
            return SectionMatchResponse(items=[], truncated=True)
        items = parse_verdicts(content)
        if items is None:
            logger.warning("tree: нечитаемый JSON от модели (%d символов)", len(content))
            return SectionMatchResponse(items=[], truncated=False)
        return SectionMatchResponse(items=items, truncated=False)
```

- [ ] **Step 4: Прогнать, ruff, commit**

```bash
git add backend/app/domain/entities.py backend/app/domain/ports.py backend/app/infrastructure/ai/openrouter_tree_matcher.py backend/app/infrastructure/ai/tree_prompt.py backend/tests/test_openrouter_tree_matcher.py backend/tests/test_tree_prompt.py
git commit -m "feat(tree): адаптер OpenRouterTreeMatcher с кэшем префикса и детекцией обрезки"
```

---

### Task 9: `TreeMatchingRunner` — обход чанков

**Files:**
- Create: `backend/app/services/tree_matching_service.py`
- Modify: `backend/tests/fakes.py` — `FakeTreeMatcher`
- Test: `backend/tests/test_tree_matching_service.py`

**Interfaces:**
- Consumes: всё из Tasks 2–4, 6, 8.
- Produces:
```python
class TreeMatchingRunner:
    def __init__(self, *, matcher: TreeMatcher, estimates: EstimateRepository,
                 articles: ArticleRepository, chunk_rows: int, min_chunk_rows: int,
                 context_window: int, output_reserve_per_row: int,
                 fund_enabled: bool = False) -> None: ...
    def run(self, estimate_id: int) -> Counter[EstimateRowStatus]: ...
class CatalogTooLargeError(DomainError)  # code="catalog_too_large"
class CatalogEmptyError(DomainError)     # code="catalog_empty"
```
`fund_enabled=True` в PR 1 → `NotImplementedError("фонд v3 — PR 3")` в конструкторе.

`FakeTreeMatcher(responses: list[SectionMatchResponse | Exception])` — отдаёт по очереди, пишет `self.requests: list[SectionMatchRequest]`; альтернативно `verdict_fn: Callable[[SectionMatchRequest], list[dict]]`.

- [ ] **Step 1: Тесты**

```python
from collections import Counter
from app.domain.entities import CatalogArticle, EstimateNode, NewEstimate, SectionMatchResponse
from app.domain.errors import TransientError
from app.domain.tree_matching import estimate_tokens
from app.services.tree_matching_service import CatalogEmptyError, TreeMatchingRunner
from tests.fakes import FakeArticleRepository, FakeEstimateRepository, FakeTreeMatcher

CAT = [("4", "Конструктив"), ("4.2", "Надземная"), ("4.2.1", "Гориз 1-й"), ("4.2.2", "Верт 1-й"),
       ("4.99", "Прочее (конструктив)"), ("9", "Лифты"), ("9.99", "Прочее лифты")]


def _articles() -> FakeArticleRepository:
    art = FakeArticleRepository()
    for i, (code, name) in enumerate(CAT, start=1):
        art.add_article(id=i, code=code, name=name)  # parent_id для list_catalog фейка не нужен: parent_code выводится из кода
    return art


def _node(code: str, name: str, si: int) -> EstimateNode:
    return EstimateNode(code, name, None, "СМР", name, si, code.count(".") + 1)


def _runner(repo, art, matcher, **kw) -> TreeMatchingRunner:
    return TreeMatchingRunner(matcher=matcher, estimates=repo, articles=art, chunk_rows=kw.get("chunk_rows", 120),
                              min_chunk_rows=10, context_window=200_000, output_reserve_per_row=48)


def by_name(mapping: dict[str, dict]):
    """verdict_fn: имя строки → сырой вердикт (i подставляется по id узла)."""
    def fn(req):
        return [{"i": n.id, **mapping[n.name]} for n in req.nodes if n.id in req.targets and n.name in mapping]
    return fn


def test_happy_path_writes_statuses_and_uses_parent_context_within_chunk() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [
        _node("4", "Конструктив", 0), _node("4.1", "1 Этап", 1), _node("4.1.1", "Гориз 1-й", 2),
        _node("4.1.2", "Прочее", 3), _node("9", "Лифты", 4), _node("9.1", "Прочее", 5)])
    matcher = FakeTreeMatcher(verdict_fn=by_name({
        "Конструктив": {"code": "4", "sure": True, "alt": None}, "1 Этап": {"code": "org", "sure": True, "alt": None},
        "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": "4.2.2"}, "Прочее": {"code": "9.99", "sure": True, "alt": None},
        "Лифты": {"code": "9", "sure": True, "alt": None}}))
    counts = _runner(repo, art, matcher).run(est.id)
    rows = {n["name"]: n for n in repo.nodes.values()}
    assert rows["Конструктив"]["status"] == "confident" and rows["1 Этап"]["status"] == "excluded"
    assert rows["Гориз 1-й"]["status"] == "confident" and rows["Гориз 1-й"]["candidates"][1]["code"] == "4.2.2"
    # «Прочее» под «Конструктив» получило 9.99 → вне поддерева доверенного родителя 4 → needs_review
    prochee = [n for n in repo.nodes.values() if n["name"] == "Прочее"]
    assert {n["status"] for n in prochee} == {"needs_review", "confident"}
    assert counts[EstimateRowStatus.CONFIDENT] == 4 and len(matcher.requests) == 2  # два корня — два вызова


def test_non_targets_are_context_only_and_not_overwritten() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1)])
    root = est.rows[0].id
    repo.nodes[root].update(status="confident", matched_code="4", matched_article_id=1)
    matcher = FakeTreeMatcher(verdict_fn=by_name({"Конструктив": {"code": "9", "sure": True, "alt": None},
                                                  "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": None}}))
    _runner(repo, art, matcher).run(est.id)
    assert repo.nodes[root]["matched_code"] == "4"                       # не перезаписан
    assert matcher.requests[0].targets == {est.rows[1].id}
    assert matcher.requests[0].hints[root] == ("4", True)                 # виден как [уже: 4]


def test_parent_chunk_verdict_feeds_child_chunk_context() -> None:
    # лимит 2 строки: корень+первый ребёнок — чанк 1, второй ребёнок — чанк 2 с ancestors из свежего дерева
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1),
                                                     _node("4.2", "Верт 1-й", 2)])
    matcher = FakeTreeMatcher(verdict_fn=by_name({"Конструктив": {"code": "4", "sure": True, "alt": None},
                                                  "Гориз 1-й": {"code": "4.2.1", "sure": True, "alt": None},
                                                  "Верт 1-й": {"code": "9", "sure": True, "alt": None}}))
    _runner(repo, art, matcher, chunk_rows=2).run(est.id)
    assert len(matcher.requests) == 2
    assert matcher.requests[1].ancestors[0][1] == ("4", True)             # предок — из чанка 1, доверенный
    assert repo.nodes[est.rows[2].id]["status"] == "needs_review"        # 9 вне поддерева 4 → флаг


def test_transient_marks_remaining_and_descendant_chunks_error() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1),
                                                     _node("4.2", "Верт 1-й", 2), _node("9", "Лифты", 3)])
    repo.nodes[est.rows[1].id]["status"] = "no_match"                     # ретрай терминального no_match
    matcher = FakeTreeMatcher(responses=[TransientError("boom"),
                                         SectionMatchResponse(items=[{"i": est.rows[3].id, "code": "9", "sure": True, "alt": None}], truncated=False)])
    counts = _runner(repo, art, matcher, chunk_rows=2).run(est.id)
    st = {n["name"]: n for n in repo.nodes.values()}
    assert st["Конструктив"]["status"] == "error" and st["Конструктив"]["match_error"].startswith("tree_transient")
    assert st["Гориз 1-й"]["status"] == "error"                           # no_match не остался терминальным
    assert st["Верт 1-й"]["match_error"] == "tree_ancestor_failed"       # дочерний чанк упавшего поддерева
    assert st["Лифты"]["status"] == "confident"                           # сиблинг-раздел не пострадал
    assert counts[EstimateRowStatus.ERROR] == 3


def test_truncated_response_splits_chunk_then_errors_below_min() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1),
                                                     _node("4.2", "Верт 1-й", 2)])
    ok = lambda ids: SectionMatchResponse(items=[{"i": i, "code": "4", "sure": True, "alt": None} for i in ids], truncated=False)
    trunc = SectionMatchResponse(items=[], truncated=True)
    r0, r1, r2 = (r.id for r in est.rows)
    matcher = FakeTreeMatcher(responses=[trunc, ok([r0, r1]), ok([r2])])
    # chunk_rows=4: первый вызов — все 3 строки; обрезка → half=2 → чанки [корень+первый ребёнок], [второй]
    runner = TreeMatchingRunner(matcher=matcher, estimates=repo, articles=art, chunk_rows=4, min_chunk_rows=2,
                                context_window=200_000, output_reserve_per_row=48)
    runner.run(est.id)
    assert len(matcher.requests) == 3 and all(n["status"] == "confident" for n in repo.nodes.values())
    assert [sorted(n.id for n in r.nodes) for r in matcher.requests] == [[r0, r1, r2], [r0, r1], [r2]]
    # ниже минимума → error
    repo2, matcher2 = FakeEstimateRepository(), FakeTreeMatcher(responses=[trunc])
    est2 = repo2.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    TreeMatchingRunner(matcher=matcher2, estimates=repo2, articles=art, chunk_rows=10, min_chunk_rows=10,
                       context_window=200_000, output_reserve_per_row=48).run(est2.id)
    assert repo2.nodes[est2.rows[0].id]["match_error"] == "tree_output_truncated"


def test_lost_cas_refreshes_parent_before_children() -> None:
    repo, art = FakeEstimateRepository(), _articles()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0), _node("4.1", "Гориз 1-й", 1)])
    root, child = (r.id for r in est.rows)

    def fn(req):
        # «оператор» успевает переопределить корень между вызовом и записью
        repo.save_review_decision(root, review_status="overridden", final_article_id=6, final_code="9", final_name="Лифты")
        return [{"i": root, "code": "4", "sure": True, "alt": None}, {"i": child, "code": "4.2.1", "sure": True, "alt": None}]
    _runner(repo, art, FakeTreeMatcher(verdict_fn=fn)).run(est.id)
    assert repo.nodes[root]["final_code"] == "9"                          # ревью не затёрто
    assert repo.nodes[child]["status"] == "needs_review"                  # 4.2.1 вне поддерева свежего 9


def test_budget_respects_window_and_shrinks_with_output_reserve() -> None:
    # 10 узлов-сиблингов под корнем, имена по 30 символов (~10 токенов + 8 формат + reserve).
    repo, art = FakeEstimateRepository(), _articles()
    nodes = [_node("4", "Конструктив", 0)] + [_node(f"4.{k}", "x" * 30, k) for k in range(1, 11)]
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), nodes)
    fn = lambda req: [{"i": n.id, "code": "4", "sure": True, "alt": None} for n in req.nodes if n.id in req.targets]
    # каталог ~7 статей (~60 токенов); окно подобрано так, что бюджет строк ≈ 300 токенов
    window = int((1_500 + 60 + 600 + 512 + 300) / 0.8)
    m1 = FakeTreeMatcher(verdict_fn=fn)
    TreeMatchingRunner(matcher=m1, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=1,
                       context_window=window, output_reserve_per_row=1).run(est.id)
    est2 = repo.create(NewEstimate(1, "b.xlsx", "k"), nodes)
    m2 = FakeTreeMatcher(verdict_fn=fn)
    TreeMatchingRunner(matcher=m2, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=1,
                       context_window=window, output_reserve_per_row=40).run(est2.id)
    # инвариант: каждый чанк укладывается в бюджет с учётом резерва ответа
    for m, reserve in ((m1, 1), (m2, 40)):
        for req in m.requests:
            cost = sum(estimate_tokens(f"{n.id} | {n.code} | {n.name}") + 8 + reserve for n in req.nodes)
            assert cost <= 300
    # больший резерв ответа → чанки мельче → вызовов больше
    assert len(m2.requests) > len(m1.requests) >= 1
    assert all(n["status"] == "confident" for n in repo.nodes.values())


def test_empty_catalog_raises() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("4", "Конструктив", 0)])
    with pytest.raises(CatalogEmptyError):
        _runner(repo, FakeArticleRepository(), FakeTreeMatcher(responses=[])).run(est.id)


def test_fund_enabled_not_implemented_in_pr1() -> None:
    with pytest.raises(NotImplementedError):
        TreeMatchingRunner(matcher=FakeTreeMatcher(responses=[]), estimates=FakeEstimateRepository(),
                           articles=_articles(), chunk_rows=1, min_chunk_rows=1, context_window=1,
                           output_reserve_per_row=1, fund_enabled=True)
```

- [ ] **Step 2: `FakeTreeMatcher`** в `tests/fakes.py`:
```python
class FakeTreeMatcher(TreeMatcher):
    def __init__(self, responses: list[SectionMatchResponse | Exception] | None = None,
                 verdict_fn: Callable[[SectionMatchRequest], list[dict]] | None = None) -> None:
        self._responses = list(responses or [])
        self._fn = verdict_fn
        self.requests: list[SectionMatchRequest] = []

    def match_section(self, req: SectionMatchRequest) -> SectionMatchResponse:
        self.requests.append(req)
        if self._fn is not None:
            return SectionMatchResponse(items=self._fn(req), truncated=False)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
```

- [ ] **Step 3: Падение** — `ModuleNotFoundError`.

- [ ] **Step 4: Реализация `TreeMatchingRunner`**

```python
"""Оркестрация tree-движка: чанки → LLM → валидация → CAS (спека 2026-08-27 §4)."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence

from app.domain.entities import (
    AncestorContext, CatalogArticle, EstimateRowStatus, NodeMatch, SectionMatchRequest, TreeNode,
)
from app.domain.errors import DomainError, TransientError
from app.domain.ports import ArticleRepository, EstimateRepository, TreeMatcher
from app.domain.tree_matching import (
    Chunk, build_hints, effective_ancestor_context, estimate_tokens, hint_for, resolve_parents,
    split_sections, to_node_match, validate_one,
)

logger = logging.getLogger(__name__)

EXPECTED = ("pending", "error", "no_match")
ERR_TRANSIENT = "tree_transient"
ERR_ANCESTOR_FAILED = "tree_ancestor_failed"
ERR_TRUNCATED = "tree_output_truncated"
ERR_ROW_TOO_LARGE = "tree_row_too_large"
_CATALOG_SHARE = 0.25
_CONTEXT_SHARE = 0.80
_SYSTEM_PROMPT_RESERVE = 1_500   # системный промпт + заголовки блоков (факт спайка ~900)
_ANCESTORS_RESERVE = 600         # путь предков чанка (глубина ≤ 6 × ~100 токенов)
_OUTPUT_MARGIN = 512             # = запас адаптера в max_tokens
_ROW_FORMAT_TOKENS = 8           # «[цель] id | код | » + перенос
```
**Примечание о зависимости:** сервис не должен импортировать `infrastructure` — импорт `tree_prompt` выше **убрать**. Бюджет оценивается по **данным**, не по тексту промпта, консервативно (инвариант спеки §5.2):

```text
_SYSTEM_PROMPT_RESERVE + catalog_tokens + _ANCESTORS_RESERVE + Σ_rows(row_text + _ROW_FORMAT_TOKENS + output_reserve_per_row) + _OUTPUT_MARGIN ≤ 0.8 × window
```
где `catalog_tokens = Σ estimate_tokens("  "·depth + f"({code}) {name}")` (с отступами), а `output_reserve_per_row` входит в стоимость **каждой** строки чанка (любая может быть целью → оценка сверху; `max_tokens` адаптера = targets × reserve + margin ≤ этой оценки).

```python
class CatalogEmptyError(DomainError):
    code = "catalog_empty"


class CatalogTooLargeError(DomainError):
    code = "catalog_too_large"


class TreeMatchingRunner:
    def __init__(self, *, matcher: TreeMatcher, estimates: EstimateRepository, articles: ArticleRepository,
                 chunk_rows: int, min_chunk_rows: int, context_window: int, output_reserve_per_row: int,
                 fund_enabled: bool = False) -> None:
        if fund_enabled:
            raise NotImplementedError("фонд v3 для tree-движка — PR 3 спеки")
        self._matcher = matcher
        self._estimates = estimates
        self._articles = articles
        self._chunk_rows = chunk_rows
        self._min_rows = min_chunk_rows
        self._window = context_window
        self._reserve = output_reserve_per_row

    def run(self, estimate_id: int) -> Counter[EstimateRowStatus]:
        catalog_list = self._articles.list_catalog()
        if not catalog_list:
            raise CatalogEmptyError("справочник пуст")
        catalog_tokens = sum(estimate_tokens(f"({a.code}) {a.name}") for a in catalog_list)
        if catalog_tokens > _CATALOG_SHARE * self._window:
            raise CatalogTooLargeError(f"справочник ~{catalog_tokens} токенов > 25% окна {self._window}")
        catalog = {a.code: a for a in catalog_list}
        tree = list(self._estimates.fetch_tree(estimate_id))
        parents = resolve_parents(tree)
        counts: Counter[EstimateRowStatus] = Counter()
        failed_roots: set[int] = set()
        # Бюджет чанка (спека §5.2, консервативно): system + catalog + ancestors + rows + targets×reserve
        # + margin ≤ 0.8×window. Каждая строка чанка учитывается как ПОТЕНЦИАЛЬНАЯ цель (reserve
        # входит в её стоимость) — реальное число целей ≤ числа строк, оценка сверху.
        row_budget = (
            int(_CONTEXT_SHARE * self._window)
            - _SYSTEM_PROMPT_RESERVE - catalog_tokens - _ANCESTORS_RESERVE - _OUTPUT_MARGIN
        )
        if row_budget <= 0:
            raise CatalogTooLargeError(f"после справочника (~{catalog_tokens}) на смету не остаётся бюджета")
        row_tokens = self._row_cost  # estimate_tokens(строка) + формат + output_reserve_per_row

        def is_target(i: int) -> bool:
            return tree[i].status in EXPECTED and tree[i].review_status == "unreviewed"

        def commit(i: int, result: NodeMatch) -> None:
            ok = self._estimates.save_node_match_cas(tree[i].id, result, EXPECTED)
            tree[i] = tree[i].with_result(result) if ok else self._estimates.refresh_tree_node(tree[i].id)
            if ok:
                counts[result.status] += 1

        def ctx(i: int) -> AncestorContext:
            return effective_ancestor_context(i, tree, parents)

        def in_failed(i: int) -> bool:
            p: int | None = i
            while p is not None:
                if p in failed_roots:
                    return True
                p = parents[p]
            return False

        def process(chunk: Chunk, max_rows: int) -> None:
            targets = [i for i in chunk.indices if is_target(i)]
            for i in chunk.oversized:
                if i in targets:
                    commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_ROW_TOO_LARGE))
            targets = [i for i in targets if i not in chunk.oversized]
            if not targets:
                return
            if in_failed(chunk.root):
                for i in targets:
                    commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_ANCESTOR_FAILED))
                return
            # PR 1: pre-call фонд выключен (fund_enabled=False) — контекст считается сразу под вызов
            target_ids = frozenset(tree[i].id for i in targets)
            req = SectionMatchRequest(
                nodes=[tree[i] for i in chunk.indices],
                ancestors=self._ancestors(chunk.root, tree, parents),
                hints=build_hints(chunk.indices, tree, target_ids),
                targets=target_ids, catalog=catalog_list, precedents=[],
            )
            try:
                resp = self._matcher.match_section(req)
            except TransientError as exc:
                failed_roots.add(chunk.root)
                for i in targets:
                    commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=f"{ERR_TRANSIENT}: {exc}"))
                return
            if resp.truncated:
                half = max_rows // 2
                if half < self._min_rows or len(chunk.indices) <= self._min_rows:
                    for i in targets:
                        commit(i, NodeMatch(EstimateRowStatus.ERROR, match_error=ERR_TRUNCATED))
                    return
                sub = split_sections([tree[i] for i in chunk.indices], _reindex(parents, chunk.indices),
                                     max_rows=half, budget_tokens=row_budget, row_tokens=row_tokens)
                for c in sub:
                    process(_map_back(c, chunk.indices), half)
                return
            by_id = {}
            for item in resp.items:
                nid = item.get("i") if isinstance(item, dict) else None
                if isinstance(nid, int) and nid in target_ids and nid not in by_id:
                    by_id[nid] = item
                elif isinstance(nid, int) and nid in by_id:
                    logger.warning("tree: дубликат вердикта для узла %s — взят первый", nid)
            for i in targets:                                  # сверху вниз: контекст по принятым вердиктам
                c = ctx(i)
                v = validate_one(by_id.get(tree[i].id), tree[i].id, catalog.keys(), c)
                commit(i, to_node_match(v, c, catalog))

        for chunk in split_sections(tree, parents, max_rows=self._chunk_rows, budget_tokens=row_budget,
                                    row_tokens=row_tokens):
            process(chunk, self._chunk_rows)
        return counts

    @staticmethod
    def _ancestors(
        root: int, tree: Sequence[TreeNode], parents: Sequence[int | None]
    ) -> list[tuple[TreeNode, tuple[str, bool] | None]]:
        """Путь предков чанка с подсказками hint_for — те же правила доверия, что у контекста."""
        path: list[tuple[TreeNode, tuple[str, bool] | None]] = []
        p = parents[root]
        while p is not None:
            path.append((tree[p], hint_for(tree[p])))
            p = parents[p]
        return list(reversed(path))

    def _row_cost(self, n: TreeNode) -> int:
        """Стоимость строки в бюджете чанка: текст + формат + резерв ответа (строка = потенциальная цель)."""
        return estimate_tokens(f"{n.id} | {n.code} | {n.name}") + _ROW_FORMAT_TOKENS + self._reserve


def _reindex(parents: Sequence[int | None], indices: Sequence[int]) -> list[int | None]:
    pos = {g: k for k, g in enumerate(indices)}
    return [pos.get(parents[g]) if parents[g] is not None else None for g in indices]


def _map_back(c: Chunk, indices: Sequence[int]) -> Chunk:
    return Chunk(root=indices[c.root], indices=[indices[k] for k in c.indices], oversized=[indices[k] for k in c.oversized])
```
`catalog_tokens` считать как `sum(estimate_tokens("  " * a.code.count(".") + f"({a.code}) {a.name}") for a in catalog_list)`. Дедуп вердиктов сделан до вызова (в `by_id`), поэтому `validate_verdicts` из Task 4 сервису не нужна (остаётся для харнесса/тестов). `catalog.keys()` — `Collection[str]`.

- [ ] **Step 5: Прогнать, ruff, commit**

Run: `cd backend; uv run pytest tests/test_tree_matching_service.py -q; uv run ruff check .`
```bash
git add backend/app/services/tree_matching_service.py backend/tests/fakes.py backend/tests/test_tree_matching_service.py
git commit -m "feat(tree): TreeMatchingRunner — обход чанков, CAS, транзиенты, обрезка"
```

---

### Task 10: Ветка `tree` в `EstimateMatchingService` и DI

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py` (конструктор строка ~53; `match_estimate` строки ~72–120; `_log_summary`)
- Modify: `backend/app/api/deps.py` (`build_estimate_matching_service`, строка ~181; новый `get_tree_matcher`)
- Modify: `backend/app/infrastructure/tasks/tasks.py:24-35` (`run_match` — `blocked` на `CatalogEmptyError`/`CatalogTooLargeError`)
- Test: `backend/tests/test_estimate_matching_service.py`, `backend/tests/test_llm_matcher_factory.py` (или новый `test_deps_tree.py`)

**Interfaces:**
- Consumes: `TreeMatchingRunner` (Task 9), `Settings` (Task 5).
- Produces: `EstimateMatchingService(..., tree: TreeMatchingRunner | None = None)`; при `tree is not None` `match_estimate` вызывает `self._tree.run(estimate_id)` вместо classify/fund/embed/gate/match; `CatalogEmptyError`/`CatalogTooLargeError` → `set_status(BLOCKED, detail, code)` и **не** ре-рейз (в отличие от `DictionaryNotReadyError` — ретраить нечего, каталог меняет админ). `deps.get_tree_matcher() -> TreeMatcher` (`lru_cache`), `build_estimate_matching_service` собирает `tree` при `settings.matching_engine == "tree"`.

- [ ] **Step 1: Тесты**

В `tests/test_estimate_matching_service.py`:
```python
def test_tree_engine_bypasses_classifier_embedder_and_gate() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeArticleRepository()
    art.add_article(id=1, code="1", name="Раздел 1")
    classifier = FakeWorkTypeClassifier(default=WorkClass.WORK)
    embedder = _Embedder()
    matcher = FakeTreeMatcher(verdict_fn=lambda req: [{"i": n.id, "code": "1", "sure": True, "alt": None} for n in req.nodes])
    runner = TreeMatchingRunner(matcher=matcher, estimates=repo, articles=art, chunk_rows=120, min_chunk_rows=10,
                                context_window=200_000, output_reserve_per_row=48)
    svc = EstimateMatchingService(matcher=MatchingService(art, embedder=None, llm_matcher=FakeLLMMatcher()),
                                  embedder=embedder, estimates=repo, articles=art, classifier=classifier,
                                  fund=FakeDecisionFundRepository(), tree=runner)
    svc.match_estimate(est.id)
    assert repo.statuses[est.id] == "ready" and classifier.calls == [] and embedder.batches == []
    assert next(iter(repo.nodes.values()))["status"] == "confident"


def test_tree_engine_empty_catalog_blocks_without_raise() -> None:
    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = FakeArticleRepository()
    runner = TreeMatchingRunner(matcher=FakeTreeMatcher(responses=[]), estimates=repo, articles=art, chunk_rows=120,
                                min_chunk_rows=10, context_window=200_000, output_reserve_per_row=48)
    svc = EstimateMatchingService(matcher=MatchingService(art, embedder=None, llm_matcher=FakeLLMMatcher()),
                                  embedder=_Embedder(), estimates=repo, articles=art,
                                  classifier=FakeWorkTypeClassifier(), fund=FakeDecisionFundRepository(), tree=runner)
    svc.match_estimate(est.id)
    assert repo.statuses[est.id] == "blocked" and repo.codes[est.id] == "catalog_empty"
    assert est.id not in repo._locks
```
Тест DI (`tests/test_deps_tree.py`):
```python
def test_build_service_uses_tree_when_engine_tree(monkeypatch) -> None:
    from app.api import deps
    from app.core.config import get_settings
    monkeypatch.setenv("MATCHING_ENGINE", "tree")
    get_settings.cache_clear(); deps.get_tree_matcher.cache_clear()
    try:
        svc = deps.build_estimate_matching_service(session=MagicMock())
        assert svc._tree is not None
    finally:
        get_settings.cache_clear()
```
(проверить, как соседние тесты `deps` подменяют сессию — следовать их образцу.)

- [ ] **Step 2: Падение.**

- [ ] **Step 3: Реализация**

`estimate_matching_service.py` — конструктор: параметр `tree: TreeMatchingRunner | None = None`, `self._tree = tree`. В `match_estimate` после `set_status(RUNNING)`:
```python
            if self._tree is not None:
                try:
                    counts = self._tree.run(estimate_id)
                except (CatalogEmptyError, CatalogTooLargeError) as exc:
                    self._estimates.set_status(estimate_id, EstimateStatus.BLOCKED, detail=str(exc), code=exc.code)
                    self._log_summary(estimate_id, counts, excluded, fund_hits, start)
                    return
                excluded = counts.pop(EstimateRowStatus.EXCLUDED, 0)
            else:
                excluded = self._classify_nodes(estimate_id)
                ... (существующее тело до counts = self._match_nodes(estimate_id))
```
Финализация (`errors/unfinished → partial_error иначе ready`) и summary — общие. Импорт `TreeMatchingRunner`, ошибок — из `app.services.tree_matching_service` (services→services допустимо).

`deps.py`:
```python
@lru_cache
def get_tree_matcher() -> TreeMatcher:
    s = get_settings()
    return OpenRouterTreeMatcher(
        api_key=s.openrouter_api_key, base_url=s.openrouter_base_url, model=s.openrouter_tree_model,
        reasoning_effort=s.tree_reasoning_effort, output_reserve_per_row=s.tree_output_reserve_per_row,
        timeout_s=max(s.ai_call_timeout_s, 300.0), retry_budget=s.transient_retry_budget,
    )
```
В `build_estimate_matching_service`:
```python
    tree = None
    if settings.matching_engine == "tree":
        tree = TreeMatchingRunner(
            matcher=get_tree_matcher(), estimates=estimates, articles=articles,
            chunk_rows=settings.tree_chunk_rows, min_chunk_rows=settings.tree_min_chunk_rows,
            context_window=settings.tree_context_window,
            output_reserve_per_row=settings.tree_output_reserve_per_row, fund_enabled=False,
        )
    return EstimateMatchingService(..., tree=tree)
```
`tasks.run_match` — без изменений (ошибки каталога гасятся в сервисе).

- [ ] **Step 4: Полный сьют, ruff, commit**

Run: `cd backend; uv run pytest -q; uv run ruff check .`
```bash
git add backend/app/services/estimate_matching_service.py backend/app/api/deps.py backend/tests/test_estimate_matching_service.py backend/tests/test_deps_tree.py
git commit -m "feat(tree): ветка matching_engine=tree в EstimateMatchingService и DI"
```

---

### Task 11: Фронт — `score: number | null`

**Files:**
- Modify: `frontend/src/lib/types.ts:19,31`, `frontend/src/lib/api/estimates.ts:28,108,118`, `frontend/src/pages/estimate/ReviewCard.tsx:227-231,289-291`, `frontend/src/lib/mock/api.ts:80`
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

- [ ] **Step 1: Тест**

```tsx
// хелперы row(...) и renderCard(...) уже объявлены в начале ReviewCard.test.tsx
describe("ReviewCard: score null (tree-движок)", () => {
  it("не рендерит score строки и кандидата, когда он null", () => {
    const r = row(7, 3, "needs_review", {
      score: null,
      matched_code: "4.2.1",
      candidates: [
        { id: 5, article_code: "4.2.1", name: "Гориз", score: null, breadcrumb: [] },
        { id: 6, article_code: "4.2.3", name: "Гориз проч", score: null, breadcrumb: [] },
      ],
    })
    renderCard(r)
    expect(screen.queryByText("0.00")).toBeNull()
    expect(screen.getByText("Гориз")).toBeInTheDocument()
    expect(screen.getByText("Гориз проч")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Падение** — `tsc`: `Type 'null' is not assignable to type 'number'`.

- [ ] **Step 3: Реализация**

`types.ts`: `Candidate.score: number | null`, `MatchRow.score: number | null`. `api/estimates.ts`: `RowDto.candidates[].score: number | null`; маппинг `score: r.score ?? null` (вместо `?? 0`) и `score: c.score`. `ReviewCard.tsx`:
```tsx
{row.status !== "matched_fund" && row.score !== null && (
  <span className="font-mono text-xs text-muted-foreground">{row.score.toFixed(2)}</span>
)}
…
{c.score !== null && (
  <span className="font-mono text-xs text-muted-foreground">{c.score.toFixed(2)}</span>
)}
```
`mock/api.ts:80`: `row.score === null ? "" : row.score.toFixed(2)` внутри существующего тернарника. Прогнать `npm run typecheck` — починить остальные места, которые подсветит `tsc` (`useReviewQueue`, `ReviewGrid`, фикстуры) тем же образом.

- [ ] **Step 4: Прогон и commit**

Run: `cd frontend; npm run typecheck; npm run lint; npm run test`
```bash
git add frontend/src
git commit -m "feat(review): score кандидата и строки nullable — tree-движок не даёт косинуса"
```

---

### Task 12: Документация

**Files:**
- Modify: `docs/PIPELINE.md` (раздел 6 — абзац «Движок `tree` (за флагом)» со ссылкой на спеку), `CLAUDE.md` (строка правила «Сопоставление: …» — добавить: «`MATCHING_ENGINE=tree` включает структурный движок — см. спеку»), `docs/TECH_DEBT.md` (новые записи: параллелизм разделов; provenance контекста; `validate_verdicts` без прод-потребителя; пересмотр gold), `docs/devlog/2026-08-XX-tree-matching-pr1.md`.

- [ ] **Step 1: Написать devlog** по структуре `docs/devlog/README.md`: что сделано, файлы, решения (сервис оценивает бюджет по данным, не по промпту; `SectionMatchResponse` с сырыми словарями — валидация в домене; фонд выключен), что осталось (PR 2–4), как включить локально (`MATCHING_ENGINE=tree` в `backend/.env`, `just dev-back` + Celery).
- [ ] **Step 2: Обновить PIPELINE/CLAUDE/TECH_DEBT.**
- [ ] **Step 3: Commit**

```bash
git add docs CLAUDE.md
git commit -m "docs: tree matching PR 1 — devlog, PIPELINE, TECH_DEBT"
```

---

## Self-Review

**Spec coverage (§ спеки → задача):** §3.1 сущности → T1 (+`SectionMatchResponse` T8); §3.2 порт/репозитории → T1, T6; §3.3 `resolve_parents`/контекст → T2; `split_sections` → T3; `build_hints`/`validate`/`to_node_match`/`neighbors` → T4; `fund_key_v3`/`FUND_KEY_VERSION` → T2 (используется в PR 3); §4 сервис (контекст≠цели, рабочее дерево, сверху вниз, транзиент → error, `failed_roots`, обрезка) → T9, T10; §5.1 адаптер (cache_control, reasoning, max_tokens, length/JSON) → T7, T8; §5.2 бюджет (каталог ≤25%, чанк ≤80%, `row_too_large`) → T9; §5.3 конфиг → T5; §7.1 `score` nullable → T1, T11; §11 п.1 фонд выключен → T9 (`NotImplementedError`), T10 (`fund_enabled=False`). Вне PR 1 (по спеке): §6 фонд, §7.2–7.3 `dependents_hint`, §8 харнесс, §9 гейт.

**Type consistency:** `TreeMatcher.match_section -> SectionMatchResponse` объявлен в T1 и используется T8/T9 без изменений; `save_node_match_cas(node_id, result, expected_statuses) -> bool` одинаково в T1/T6/T9; `Chunk(root, indices, oversized)` T3/T9; `validate_one(item, node_id, catalog_codes, ctx)` T4/T9; `AncestorContext(trusted_code, has_uncertain_barrier)` везде через конструктор.

**Placeholders:** нет. Сигнатуры `FakeArticleRepository.add_article(*, id, code, name, parent_id=None)` и хелперы `row()/renderCard()` из `ReviewCard.test.tsx` подставлены фактические.

**Ревью плана (Codex, 2026-08-28) — учтено:** бюджет чанка включает резерв ответа на каждую строку, путь предков и margin (T9, инвариант §5.2, тест `test_budget_respects_window_and_shrinks_with_output_reserve`); цели помечены `[цель]`, не-цели без кода — `[контекст]`, блок `ЦЕЛИ` (T7); единый `hint_for` для подсказок и пути предков с правилами доверия, `rejected` не показывается как `[уже: …]` (T4, T9); тесты oversized (`big={2:50}`) и обрезки (`chunk_rows=4`) исправлены; `select` только по колонкам (T6); `parse_verdicts` через `JSONDecoder.raw_decode` (T7).
