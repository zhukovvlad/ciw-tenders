# Этап 2 / PR-A: бэк-контракт карточки и контракт excluded-узлов — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Бэкенд отдаёт всё, что нужно карточке решения (полный `breadcrumb` строки, крошки статей справочника у кандидатов/рекомендации/поиска, `source_index`, `match_error`), а текущая таблица ревью перестаёт врать про excluded/pending-строки (приглушение, честные лейблы, клавиатура мимо них).

**Architecture:** Полная UI-крошка строки — позиционный пересчёт (`resolve_ancestor_indices` по `depth` в порядке `source_index`), считается в DTO-слое; страж-тест верифицирует резолв org-free-проекцией через доменную `build_embedding_input` (единый источник правды — НЕ реимплементировать фильтр/нормализацию/схлопывание). Крошки статей — новый порт `ArticleRepository.ancestor_names_by_ids` поверх чистого обходчика дерева `domain/catalog_tree.py` (его же использует фейк). Фронт: расширение типов до полного множества статусов бэка + Optional-защитный маппинг DTO с merge-ом `prev` (PATCH-ответ крошек не несёт).

**Tech Stack:** FastAPI + SQLAlchemy (бэк), React + TS strict + shadcn/ui (фронт), pytest / vitest.

**Спека:** [docs/superpowers/specs/2026-07-03-ux-stage2-review-screen-design.md](../specs/2026-07-03-ux-stage2-review-screen-design.md) §2 (+§1 таблица решений). Роадмап: [2026-07-02-ux-roadmap-design.md](../specs/2026-07-02-ux-roadmap-design.md) §4.2e.

## Global Constraints

- Ветка: `feat/ux-stage2-pr-a-contract` ОТ `docs/ux-stage2-spec` (спека этапа 2 есть только там).
- Бэк: только `uv run` из `backend/`; ruff line-length 100; `from __future__ import annotations`; type hints обязательны; юнит-тесты НЕ ходят в реальную БД/AI (фейки портов + `app.dependency_overrides`); Clean Architecture `api → services → domain ← infrastructure` — новая возможность внешнего слоя начинается с порта в `domain/ports.py`.
- Фронт: **shadcn-first** (новая разметка из shadcn-примитивов; `src/components/ui/` не править); импорты `@/`; TS strict + `erasableSyntaxOnly` (без enum/parameter properties); Prettier `printWidth 80`, LF; typecheck = `npm run typecheck` (это `tsc -b`; `tsc --noEmit` без `-b` ничего не проверяет).
- Редьюсер `reviewState` (initReview/reviewReducer/decisionFor/progress) НЕ менять — правится только `statusLabel` (Task 7). `requiresDecision` уже позитивный (PR #20) — не трогать.
- PowerShell 5.1: `;` вместо `&&`; для кириллицы в stdout Python — `PYTHONIOENCODING=utf-8`. Бэкенд-порт 8260. Файлы в LF.
- Conventional Commits, по одному коммиту на задачу.
- Обязательные ручные гейты (Task 8) выполняет контролёр — сабагентам их не исполнять и не пропускать.

---

### Task 1: Бэк — `match_error` в сущности + `source_index`/`match_error` в DTO строки

**Files:**
- Modify: `backend/app/domain/entities.py` (класс `StoredEstimateRow`, ~строка 214)
- Modify: `backend/app/infrastructure/db/estimate_repository.py` (маппинг строки в `_to_entity`)
- Modify: `backend/app/api/schemas.py` (`EstimateRowOut`, ~строка 165)
- Modify: `backend/tests/fakes.py` (построение `StoredEstimateRow` в `FakeEstimateRepository`)
- Test: `backend/tests/test_estimate_row_payload.py` (новый)

**Interfaces:**
- Consumes: `StoredEstimateRow` (id/code/name/depth/embedding_input/source_index/status/... — entities.py:214), `EstimateRowModel.match_error` (models.py:127 — колонка уже есть).
- Produces: `StoredEstimateRow.match_error: str | None = None`; `EstimateRowOut.source_index: int`, `EstimateRowOut.match_error: str | None = None` — Task 5 расширяет `from_entity` дальше, Task 6 читает поля на фронте.

- [ ] **Step 1: Написать падающий тест**

Создай `backend/tests/test_estimate_row_payload.py`:

```python
from __future__ import annotations

from app.api.schemas import EstimateRowOut
from app.domain.entities import StoredEstimateRow


def _row(**overrides: object) -> StoredEstimateRow:
    fields: dict = {
        "id": 7, "code": "2.4.2", "name": "Устройство приямков",
        "parent_code": "2.4", "section_type": None, "depth": 3,
        "embedding_input": "Конструктив. Подземная часть. Устройство приямков",
        "source_index": 12, "status": "error",
    }
    fields.update(overrides)
    return StoredEstimateRow(**fields)


def test_row_out_carries_source_index_and_match_error() -> None:
    out = EstimateRowOut.from_entity(_row(match_error="таймаут LLM-арбитра"))
    assert out.source_index == 12
    assert out.match_error == "таймаут LLM-арбитра"


def test_match_error_defaults_to_none() -> None:
    assert EstimateRowOut.from_entity(_row()).match_error is None
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_row_payload.py -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'match_error'`.

- [ ] **Step 3: Реализация**

`entities.py`, в `StoredEstimateRow` после поля `score: float | None = None` добавь:

```python
    match_error: str | None = None  # текст ошибки матчинга (status="error") — для карточки ревью
```

`schemas.py`, в `EstimateRowOut` после `status: str` добавь поля, и проброс в `from_entity`:

```python
    source_index: int = 0
    match_error: str | None = None
```

В `from_entity` добавь в вызов `cls(...)`: `source_index=r.source_index, match_error=r.match_error,`.

`estimate_repository.py`: найди в `_to_entity` построение `StoredEstimateRow(...)` (grep `StoredEstimateRow(`) и добавь `match_error=<переменная строки>.match_error,` рядом с маппингом `score` (точное имя переменной цикла сверь по месту — код фактический, не выдумывай).

`tests/fakes.py`: найди построение `StoredEstimateRow(...)` в `FakeEstimateRepository` (grep). Добавь проброс `match_error=n.get("match_error"),` из node-словаря (тем же паттерном, что соседние опциональные поля; если словари построения именуются иначе — присмотрись к фактическому коду и повтори его стиль).

- [ ] **Step 4: Тесты зелёные + полный прогон**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_row_payload.py -v; uv run pytest -q`
Expected: новый файл PASS; полный прогон — без новых падений (база: 383 passed / 3 skipped).

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(estimates): source_index и match_error в контракте строки сметы"
```

---

### Task 2: Бэк — доменный `full_breadcrumbs` (полная цепочка предков)

**Files:**
- Modify: `backend/app/domain/classification.py` (рядом с `resolve_ancestor_indices`, ~строка 115)
- Test: `backend/tests/test_full_breadcrumbs.py` (новый)

**Interfaces:**
- Consumes: `resolve_ancestor_indices(depths: Sequence[int]) -> list[list[int]]` (classification.py:115).
- Produces: `full_breadcrumbs(items: Sequence[tuple[int, str]]) -> list[list[str]]` — Task 3 (страж) и Task 5 (DTO) зовут её.

- [ ] **Step 1: Падающий тест**

Создай `backend/tests/test_full_breadcrumbs.py`:

```python
from __future__ import annotations

from app.domain.classification import full_breadcrumbs


def test_nested_chain_full_names() -> None:
    items = [(1, "Раздел"), (2, "Подраздел"), (3, "Работа")]
    assert full_breadcrumbs(items) == [[], ["Раздел"], ["Раздел", "Подраздел"]]


def test_org_ancestors_not_filtered() -> None:
    # Полная цепочка — org-узлы ВКЛЮЧЕНЫ (крошка зеркалит документ, не вход эмбеддера)
    items = [(1, "1 Этап ЖК (орг)"), (2, "Работа")]
    assert full_breadcrumbs(items) == [[], ["1 Этап ЖК (орг)"]]


def test_duplicate_codes_resolved_positionally() -> None:
    # Два узла глубины 1 — ребёнок цепляется к БЛИЖАЙШЕМУ сверху
    items = [(1, "Первый"), (1, "Второй"), (2, "Дитя второго")]
    assert full_breadcrumbs(items)[2] == ["Второй"]


def test_skipped_level_drops_from_chain() -> None:
    items = [(1, "Корень"), (3, "Сразу глубина 3")]
    assert full_breadcrumbs(items)[1] == ["Корень"]
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_full_breadcrumbs.py -v`
Expected: FAIL — `ImportError: cannot import name 'full_breadcrumbs'`.

- [ ] **Step 3: Реализация**

В `classification.py`, сразу после `resolve_ancestor_indices`:

```python
def full_breadcrumbs(items: Sequence[tuple[int, str]]) -> list[list[str]]:
    """items — (depth, name) узлов В ПОРЯДКЕ документа (source_index).

    Для каждого узла — имена предков root→parent ПОЛНОЙ цепочкой: без org-фильтра,
    без нормализации, без схлопывания. Это отображение для оператора (крошка зеркалит
    документ, каким он виден в Excel), а НЕ вход эмбеддера — вход строит
    build_embedding_input (org-free), не смешивать (спека этапа 2, §1).
    """
    chains = resolve_ancestor_indices([depth for depth, _ in items])
    return [[items[j][1] for j in chain] for chain in chains]
```

`Sequence` уже импортирован в модуле (используется в `resolve_ancestor_indices`) — сверь и при отсутствии добавь из `collections.abc`.

- [ ] **Step 4: Зелёные + ruff**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_full_breadcrumbs.py -v; uv run ruff check .`
Expected: 4 passed; ruff чист.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(domain): full_breadcrumbs — полная цепочка предков для UI-крошки"
```

---

### Task 3: Бэк — страж-проекция breadcrumb ↔ embedding_input

**Files:**
- Test: `backend/tests/test_breadcrumb_guard.py` (новый; production-код НЕ меняется)

**Interfaces:**
- Consumes: `resolve_ancestor_indices`, `build_embedding_input(self_name, ancestors: list[tuple[str, WorkClass]], *, self_class) -> str` и `WorkClass` (все — `app/domain/classification.py`), `StoredEstimateRow`.
- Produces: функцию-хелпер `assert_breadcrumb_matches_crumb(rows)` внутри тест-файла — Task 8 переиспользует её логику в ручной сверке на dev-БД.

**Суть (спека §2a):** страж верифицирует позиционный резолв предков (машинерию, где жил баг дублей кодов) против того, что реально записал классификатор в `embedding_input`. Проекция НЕ реимплементируется — переиспользуется доменная `build_embedding_input` (она же нормализует пробелы, схлопывает последовательные дубли и выбрасывает собственное имя «спасённого» org-листа). Класс предка восстанавливается прокси-правилом «`status == "excluded"` ⇔ ORG» (спасённый org-лист — всегда лист, предком не бывает); собственный класс узла из статуса не восстановим → допускаются оба варианта (`self_class ∈ {WORK, ORG}`).

- [ ] **Step 1: Написать тест целиком (фикстуры с РУКОПИСНЫМИ embedding_input — не строить их той же функцией, иначе тавтология)**

Создай `backend/tests/test_breadcrumb_guard.py`:

```python
from __future__ import annotations

from collections.abc import Sequence

from app.domain.classification import (
    WorkClass,
    build_embedding_input,
    resolve_ancestor_indices,
)
from app.domain.entities import StoredEstimateRow

# ПРЕДОХРАНИТЕЛЬ: этот страж верифицирует ПОЗИЦИОННЫЙ РЕЗОЛВ ПРЕДКОВ (машинерию,
# где жил баг дублей кодов) через org-free-проекцию против embedding_input,
# записанного классификатором. При изменении формата embedding_input (например,
# unit/quantity из таблицы решений роадмапа) — править ПРОЕКЦИЮ/СРАВНЕНИЕ здесь,
# а НЕ full_breadcrumbs и НЕ UI-крошку: полная цепочка для человека не обязана
# следовать за входом эмбеддера (спека этапа 2, §2a).
#
# Прокси «status == 'excluded' ⇔ предок ORG»: спасённый org-лист (ORG-класс,
# excluded=False) — всегда лист и предком не бывает. Если org-классификация
# влияла на крошку, не оставив следа в статусе, страж упадёт — это полезная
# находка о конвейере крошки, не поломка стража.
#
# Excluded-строки В инварианте сознательно (проверено на пайплайне и живых
# данных, 2026-07-03): save_node_classifications пишет embedding_input
# БЕЗУСЛОВНО всем строкам прохода, включая excluded (estimate_repository.py,
# .values(embedding_input=r.embedding_input)); в dev-БД у org-заголовков сметы
# 16 лежит org-free крошка БЕЗ собственного имени (self_class=ORG), например
# у узла «2 Этап БЦ» — «Возведение несущих конструкций здания». Вне инварианта
# только pending (сырой парсерный join до классификации).


def _row(
    id: int, code: str, name: str, depth: int, si: int, status: str, crumb: str
) -> StoredEstimateRow:
    return StoredEstimateRow(
        id=id, code=code, name=name, parent_code=None, section_type=None,
        depth=depth, embedding_input=crumb, source_index=si, status=status,
    )


def assert_breadcrumb_matches_crumb(rows: Sequence[StoredEstimateRow]) -> None:
    """Для каждой классифицированной строки: org-free-проекция полной цепочки
    == embedding_input. pending-строки вне инварианта (их крошка — сырой
    парсерный join до классификации)."""
    ordered = sorted(rows, key=lambda r: r.source_index)
    chains = resolve_ancestor_indices([r.depth for r in ordered])
    for i, row in enumerate(ordered):
        if row.status == "pending":
            continue
        ancestors = [
            (
                ordered[j].name,
                WorkClass.ORG if ordered[j].status == "excluded" else WorkClass.WORK,
            )
            for j in chains[i]
        ]
        variants = {
            build_embedding_input(row.name, ancestors, self_class=WorkClass.WORK),
            build_embedding_input(row.name, ancestors, self_class=WorkClass.ORG),
        }
        assert row.embedding_input in variants, (
            f"строка id={row.id} code={row.code}: crumb={row.embedding_input!r} "
            f"не совпал ни с одной проекцией {variants!r}"
        )


def test_plain_nested_chain() -> None:
    rows = [
        _row(1, "2", "Конструктив", 1, 0, "excluded", ""),
        _row(2, "2.4", "Подземная часть", 2, 1, "confident", "Подземная часть"),
        _row(3, "2.4.2", "Устройство приямков", 3, 2, "needs_review",
             "Подземная часть. Устройство приямков"),
    ]
    # org-предок «Конструктив» (excluded) выброшен из проекции — рукописные
    # crumb-ы отражают то, что записал бы классификатор
    assert_breadcrumb_matches_crumb(rows)


def test_rescued_org_leaf_crumb_without_own_name() -> None:
    # спасённый org-лист: kept (не excluded), но своё имя в крошке выброшено
    rows = [
        _row(1, "4", "Ж/Б конструкции", 1, 0, "confident", "Ж/Б конструкции"),
        _row(2, "4.1", "1 Этап ЖК", 2, 1, "needs_review", "Ж/Б конструкции"),
    ]
    assert_breadcrumb_matches_crumb(rows)


def test_whitespace_normalized_and_repeats_collapsed() -> None:
    rows = [
        _row(1, "1", "Кровля", 1, 0, "confident", "Кровля"),
        _row(2, "1.1", "Кровля", 2, 1, "confident", "Кровля"),  # дубль схлопнут
        _row(3, "1.1.1", "Работа  с\xa0пробелами", 3, 2, "needs_review",
             "Кровля. Работа с пробелами"),
    ]
    assert_breadcrumb_matches_crumb(rows)


def test_pending_rows_skipped() -> None:
    rows = [_row(1, "1", "Что угодно", 1, 0, "pending", "сырой парсерный вид")]
    assert_breadcrumb_matches_crumb(rows)  # не падает — pending вне инварианта


def test_guard_actually_bites() -> None:
    # самопроверка стража: сломанный crumb должен падать
    rows = [_row(1, "1", "Работа", 1, 0, "confident", "Совсем другое")]
    try:
        assert_breadcrumb_matches_crumb(rows)
    except AssertionError:
        return
    raise AssertionError("страж не заметил расхождение")
```

- [ ] **Step 2: Прогнать**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_breadcrumb_guard.py -v`
Expected: 5 passed СРАЗУ (страж проверяет существующее поведение; production-код в этой задаче не меняется). Если какой-то тест упал — СТОП: не подгоняй фикстуру «чтобы прошло», а разберись, что именно классификатор пишет иначе, и доложи в отчёте (вероятная находка о конвейере крошки — см. предохранитель).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_breadcrumb_guard.py
git commit -m "test(estimates): страж-проекция — позиционный резолв против embedding_input"
```

---

### Task 4: Бэк — крошки статей: доменный обходчик + порт + реализация + фейк

**Files:**
- Create: `backend/app/domain/catalog_tree.py`
- Modify: `backend/app/domain/ports.py` (класс `ArticleRepository`, ~строка 39)
- Modify: `backend/app/infrastructure/db/article_repository.py`
- Modify: `backend/app/services/article_service.py`
- Modify: `backend/tests/fakes.py` (`FakeArticleRepository`, ~строка 114)
- Test: `backend/tests/test_catalog_tree.py` (новый)

**Interfaces:**
- Consumes: `TemplateArticle` (entities.py:26 — `article_code`, `name`, `parent_id`, `id`), `TemplateArticleModel` (models.py:32 — `parent_id` есть).
- Produces:
  - `app.domain.catalog_tree.ancestor_names_by_ids(nodes: Mapping[int, tuple[str, int | None]], article_ids: Sequence[int]) -> dict[int, list[str]]`
  - порт `ArticleRepository.ancestor_names_by_ids(article_ids: Sequence[int]) -> dict[int, list[str]]`
  - `ArticleService.ancestor_names_by_ids(...)` — passthrough; Task 5 зовёт из роутов.

- [ ] **Step 1: Падающий тест доменного обходчика**

Создай `backend/tests/test_catalog_tree.py`:

```python
from __future__ import annotations

from app.domain.catalog_tree import ancestor_names_by_ids

# id -> (name, parent_id)
_NODES = {
    1: ("03 Фундаменты и основания", None),
    2: ("03.0 Устройство фундаментов", 1),
    3: ("03.04 Фундаменты под оборудование", 2),
    4: ("Сирота с битым parent_id", 99),
}


def test_chain_root_to_parent() -> None:
    assert ancestor_names_by_ids(_NODES, [3]) == {
        3: ["03 Фундаменты и основания", "03.0 Устройство фундаментов"]
    }


def test_root_has_empty_chain() -> None:
    assert ancestor_names_by_ids(_NODES, [1]) == {1: []}


def test_unknown_id_omitted() -> None:
    assert ancestor_names_by_ids(_NODES, [777]) == {}


def test_broken_parent_link_stops_walk() -> None:
    assert ancestor_names_by_ids(_NODES, [4]) == {4: []}


def test_cycle_guard() -> None:
    cyc = {1: ("A", 2), 2: ("B", 1)}
    out = ancestor_names_by_ids(cyc, [1])
    assert 1 in out and len(out[1]) <= 20  # не зависает, обход ограничен
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_catalog_tree.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.catalog_tree'`.

- [ ] **Step 3: Реализация**

Создай `backend/app/domain/catalog_tree.py`:

```python
"""Чистый обход дерева справочника (parent_id) — крошки статей для UI.

Живёт в домене: и SQL-репозиторий, и фейк тестов зовут ЭТУ функцию —
логика обхода существует в одном месте.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_MAX_DEPTH = 20  # защита от цикла parent_id (реальное дерево — 2-3 уровня)


def ancestor_names_by_ids(
    nodes: Mapping[int, tuple[str, int | None]],
    article_ids: Sequence[int],
) -> dict[int, list[str]]:
    """Имена предков root→parent (без самой статьи) для каждого запрошенного id.

    nodes — карта id -> (name, parent_id). Неизвестные id опускаются из ответа;
    битая parent-ссылка обрывает цепочку (возвращаем то, что успели собрать).
    """
    out: dict[int, list[str]] = {}
    for aid in article_ids:
        node = nodes.get(aid)
        if node is None:
            continue
        chain: list[str] = []
        cur = node[1]
        while cur is not None and len(chain) < _MAX_DEPTH:
            parent = nodes.get(cur)
            if parent is None:
                break
            chain.append(parent[0])
            cur = parent[1]
        out[aid] = list(reversed(chain))
    return out
```

`ports.py`, в `ArticleRepository` после `list_all` добавь:

```python
    @abstractmethod
    def ancestor_names_by_ids(self, article_ids: Sequence[int]) -> dict[int, list[str]]:
        """Имена предков root→parent (без самой статьи) для каждого id;
        неизвестные id опускаются. Для крошек справочника в UI ревью."""
```

(`Sequence` — сверь импорты модуля, при отсутствии добавь из `collections.abc`.)

`infrastructure/db/article_repository.py` — в классе репозитория:

```python
    def ancestor_names_by_ids(self, article_ids: Sequence[int]) -> dict[int, list[str]]:
        if not article_ids:
            return {}
        rows = self._session.execute(
            select(
                TemplateArticleModel.id,
                TemplateArticleModel.name,
                TemplateArticleModel.parent_id,
            )
        ).all()
        nodes = {r.id: (r.name, r.parent_id) for r in rows}
        return ancestor_names_by_ids(nodes, article_ids)
```

(импорт `from app.domain.catalog_tree import ancestor_names_by_ids`; имена session-атрибута и стиль select сверь по соседним методам файла. 362 статьи — грузим карту целиком, это дешевле рекурсивных запросов.)

`services/article_service.py`:

```python
    def ancestor_names_by_ids(self, article_ids: Sequence[int]) -> dict[int, list[str]]:
        return self._repository.ancestor_names_by_ids(article_ids)
```

`tests/fakes.py`, `FakeArticleRepository` (хранилище фейка — `self.rows: dict[str, TemplateArticle]`, fakes.py:118 — проверено):
- хелперу `add_article` добавь параметр `parent_id: int | None = None` и проброс в `TemplateArticle(...)`;
- добавь метод:

```python
    def ancestor_names_by_ids(self, article_ids: Sequence[int]) -> dict[int, list[str]]:
        nodes = {
            a.id: (a.name, a.parent_id)
            for a in self.rows.values()
            if a.id is not None
        }
        return catalog_tree.ancestor_names_by_ids(nodes, article_ids)
```

(импортируй `from app.domain import catalog_tree`; `Sequence` — по импортам файла.)

- [ ] **Step 4: Зелёные + полный прогон**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_catalog_tree.py -v; uv run pytest -q; uv run ruff check .`
Expected: 5 passed; полный прогон без новых падений; ruff чист.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(articles): порт ancestor_names_by_ids — крошки статей из дерева parent_id"
```

---

### Task 5: Бэк — breadcrumb в payload: строка, рекомендация, кандидаты, поиск

**Files:**
- Modify: `backend/app/api/schemas.py` (`MatchCandidateOut`:158, `EstimateRowOut`:165, `EstimateDetailOut`, `ArticleSearchOut`:79)
- Modify: `backend/app/api/routes/estimates.py` (роут `get_estimate`:139)
- Modify: `backend/app/api/routes/articles.py` (роут `search_articles`:38)
- Test: `backend/tests/test_estimate_row_payload.py` (дополнить), `backend/tests/test_estimate_routes.py` (дополнить)

**Interfaces:**
- Consumes: `full_breadcrumbs` (Task 2), `ArticleService.ancestor_names_by_ids` (Task 4), DI `get_article_service` (`api/deps.py:212`).
- Produces (контракт для фронта, Task 6):
  - `EstimateRowOut.breadcrumb: list[str] = []` — полная цепочка предков строки;
  - `EstimateRowOut.matched_breadcrumb: list[str] = []` — крошка статьи рекомендации (по `matched_article_id`);
  - `EstimateRowOut.final_breadcrumb: list[str] = []` — крошка статьи РЕШЕНИЯ (по `final_article_id`): оператор мог выбрать статью через поиск, вне кандидатов — без этого поля после F5 крошка решения недоступна нигде (PR-B: карточка решённой строки);
  - `MatchCandidateOut.breadcrumb: list[str] = []`;
  - `ArticleSearchOut.breadcrumb: list[str] = []`;
  - PATCH `/estimates/{id}/rows/{row}/review` возвращает строку БЕЗ крошек (дефолтные `[]`) — фронт мержит из prev (Task 6). Это договорной Optional-контракт.

- [ ] **Step 1: Падающие DTO-тесты**

Дополни `backend/tests/test_estimate_row_payload.py`:

```python
from app.api.schemas import EstimateDetailOut
from app.domain.entities import Estimate, MatchCandidate
from datetime import UTC, datetime


def _estimate(rows: list[StoredEstimateRow]) -> Estimate:
    return Estimate(
        id=1, user_id=1, filename="t.xlsx", status="ready",
        created_at=datetime(2026, 1, 1, tzinfo=UTC), rows=rows,
    )


def test_detail_rows_get_full_breadcrumb() -> None:
    rows = [
        _row(id=1, code="2", name="Конструктив", depth=1, source_index=0,
             status="excluded"),
        _row(id=2, code="2.4", name="Подземная часть", depth=2, source_index=1,
             status="confident"),
        _row(id=3, code="2.4.2", name="Приямки", depth=3, source_index=2,
             status="needs_review"),
    ]
    out = EstimateDetailOut.from_entity(_estimate(rows))
    by_id = {r.id: r for r in out.rows}
    # ПОЛНАЯ цепочка: excluded-предок «Конструктив» ВКЛЮЧЁН (UI-крошка ≠ вход эмбеддера)
    assert by_id[3].breadcrumb == ["Конструктив", "Подземная часть"]
    assert by_id[1].breadcrumb == []


def test_candidate_matched_and_final_breadcrumbs_from_article_crumbs() -> None:
    row = _row(
        id=5, code="1.1", name="Работа", depth=2, source_index=1,
        status="needs_review", matched_article_id=3,
        final_article_id=9,  # выбор оператора ЧЕРЕЗ ПОИСК — статьи нет в кандидатах
        candidates=[MatchCandidate(id=3, code="03.04", name="Фунд. под обор.", score=0.7)],
    )
    root = _row(id=4, code="1", name="Раздел", depth=1, source_index=0,
                status="confident")
    crumbs = {3: ["03 Фундаменты и основания"], 9: ["08 Отделочные работы"]}
    out = EstimateDetailOut.from_entity(_estimate([root, row]), article_crumbs=crumbs)
    target = next(r for r in out.rows if r.id == 5)
    assert target.matched_breadcrumb == ["03 Фундаменты и основания"]
    assert target.candidates[0].breadcrumb == ["03 Фундаменты и основания"]
    assert target.final_breadcrumb == ["08 Отделочные работы"]


def test_row_out_without_maps_defaults_to_empty() -> None:
    out = EstimateRowOut.from_entity(_row())
    assert out.breadcrumb == [] and out.matched_breadcrumb == []
```

Сверь сигнатуру `_row`-хелпера из Task 1 (он принимает overrides — используй именованные аргументы как выше; `Estimate` — сверь фактические обязательные поля конструктора по `entities.py` и дополни `_estimate` при необходимости, это механика).

- [ ] **Step 2: Убедиться, что падают**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_row_payload.py -v`
Expected: новые тесты FAIL (`unexpected keyword argument 'article_crumbs'` / нет поля `breadcrumb`).

- [ ] **Step 3: Реализация DTO**

`schemas.py`:

- `MatchCandidateOut` — добавь `breadcrumb: list[str] = []`.
- `EstimateRowOut` — добавь `breadcrumb: list[str] = []`, `matched_breadcrumb: list[str] = []` и `final_breadcrumb: list[str] = []`; расширь `from_entity`:

```python
    @classmethod
    def from_entity(
        cls,
        r: StoredEstimateRow,
        *,
        breadcrumb: list[str] | None = None,
        article_crumbs: Mapping[int, list[str]] | None = None,
    ) -> EstimateRowOut:
        crumbs = article_crumbs or {}
        return cls(
            ...,  # существующие поля БЕЗ изменений (включая source_index/match_error из Task 1)
            breadcrumb=breadcrumb or [],
            matched_breadcrumb=(
                crumbs.get(r.matched_article_id, []) if r.matched_article_id else []
            ),
            final_breadcrumb=(
                crumbs.get(r.final_article_id, []) if r.final_article_id else []
            ),
            candidates=[
                MatchCandidateOut(
                    id=c.id, code=c.code, name=c.name, score=c.score,
                    breadcrumb=crumbs.get(c.id, []) if c.id else [],
                )
                for c in r.candidates
            ],
        )
```

(`Mapping` — из `collections.abc`; `...` в примере — маркер «существующие поля не трогай», в реальном коде перечисли их как есть.)

- `EstimateDetailOut.from_entity` — расширь:

```python
    @classmethod
    def from_entity(
        cls, e: Estimate, *, article_crumbs: Mapping[int, list[str]] | None = None
    ) -> EstimateDetailOut:
        ordered = sorted(e.rows, key=lambda r: r.source_index)
        chains = full_breadcrumbs([(r.depth, r.name) for r in ordered])
        crumb_by_id = {r.id: c for r, c in zip(ordered, chains, strict=True)}
        rows = [
            EstimateRowOut.from_entity(
                r, breadcrumb=crumb_by_id[r.id], article_crumbs=article_crumbs
            )
            for r in e.rows
        ]
        return cls(...)  # остальные поля как сейчас, rows=rows
```

(импорт `from app.domain.classification import full_breadcrumbs` — api → domain разрешено.)

- `ArticleSearchOut` — добавь `breadcrumb: list[str] = []`.

- [ ] **Step 4: Роуты**

`routes/estimates.py`, роут `get_estimate`: добавь зависимость `article_service: ArticleService = Depends(get_article_service)` (импорты по образцу `routes/articles.py`) и перед возвратом:

```python
    ids = sorted(
        {r.matched_article_id for r in est.rows if r.matched_article_id}
        | {r.final_article_id for r in est.rows if r.final_article_id}
        | {c.id for r in est.rows for c in r.candidates if c.id}
    )
    crumbs = article_service.ancestor_names_by_ids(ids) if ids else {}
    return EstimateDetailOut.from_entity(est, article_crumbs=crumbs)
```

Роут `review_row` (PATCH) НЕ трогаем — возвращает строку с дефолтными `[]` (контракт см. Interfaces).

`routes/articles.py`, роут `search_articles`:

```python
    hits = service.search(q.strip(), limit=limit)
    crumbs = service.ancestor_names_by_ids([a.id for a in hits if a.id is not None])
    return [
        ArticleSearchOut(
            id=a.id or 0, code=a.article_code, name=a.name,
            breadcrumb=crumbs.get(a.id or 0, []),
        )
        for a in hits
    ]
```

**ВАЖНО — совместимость роут-тестов:** роут `get_estimate` получил новую зависимость →
в `backend/tests/test_estimate_routes.py` хелпер `_client(...)` (строка ~68) должен по умолчанию
переопределять и её, иначе ВСЕ существующие detail-тесты попытаются построить реальный сервис:

```python
    from app.api.deps import get_article_service
    from app.services.article_service import ArticleService
    from tests.fakes import FakeArticleRepository
    # в _client, рядом с остальными overrides (article_repo — новый параметр
    # с дефолтом None → свежий пустой фейк):
    repo_articles = article_repo or FakeArticleRepository()
    app.dependency_overrides[get_article_service] = lambda: ArticleService(repo_articles)
```

(сверь фактическую сигнатуру конструктора `ArticleService` по `services/article_service.py` —
если он принимает больше зависимостей, собери его так, как это делают тесты статей: grep
`ArticleService(` по tests/.)

- [ ] **Step 5: Роут-тесты**

Дополни `backend/tests/test_estimate_routes.py` (используются существующие хелперы файла:
`_client(repo, storage, ...)`, `Row`, `seed_estimate_with_rows` из `tests.fakes`;
`FakeArticleRepository.add_article` теперь принимает `parent_id` — Task 4):

```python
def test_detail_exposes_row_and_candidate_breadcrumbs() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    articles = FakeArticleRepository()
    articles.add_article(id=1, code="03", name="03 Фундаменты и основания")
    articles.add_article(id=3, code="03.04", name="Фунд. под оборудование", parent_id=1)
    # засей смету: родитель (depth=1) + работа (depth=2) с кандидатом id=3 и
    # matched_article_id=3 — точную форму Row/seed_estimate_with_rows сверь по
    # fakes.py и соседним тестам файла (поля depth/source_index/candidates)
    est_id = seed_estimate_with_rows(repo, ...)  # ← развернуть по фактической сигнатуре
    client = _client(repo, storage, article_repo=articles)
    body = client.get(f"/api/estimates/{est_id}").json()
    child = next(r for r in body["rows"] if r["code"] == "1.1")
    assert child["breadcrumb"] == ["Раздел"]  # имя родительской строки сметы
    assert child["matched_breadcrumb"] == ["03 Фундаменты и основания"]
    assert child["candidates"][0]["breadcrumb"] == ["03 Фундаменты и основания"]
```

Строка `est_id = seed_estimate_with_rows(repo, ...)` — единственное место, где нужно свериться
с фактической сигнатурой хелпера (`grep -n "def seed_estimate_with_rows" tests/fakes.py`) и
формой `Row`; если хелпер не даёт задать candidates/matched — засей через методы фейка, как это
делают соседние ревью-тесты (grep `candidates` по test_estimate_routes.py / test_estimate_detail_review.py).

Тест поиска — в файл, где уже тестируется `/api/articles/search` (grep `articles/search` по
tests/; если тестов роута поиска нет — добавь рядом с прочими articles-роут-тестами):

```python
def test_search_exposes_article_breadcrumb() -> None:
    # override get_article_service фейком с деревом из двух статей (как выше);
    # GET /api/articles/search?q=фунд → у хита id=3:
    #   hit["breadcrumb"] == ["03 Фундаменты и основания"]
    # у root-хита id=1: breadcrumb == []
```

(разверни по паттерну overrides того файла — это механика, форма ассертов задана выше).

- [ ] **Step 6: Зелёные + полный прогон**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_row_payload.py tests/test_estimate_routes.py -v; uv run pytest -q; uv run ruff check .`
Expected: PASS; полный прогон без новых падений; ruff чист.

- [ ] **Step 7: Commit**

```bash
git add backend
git commit -m "feat(estimates): breadcrumb строки/рекомендации/кандидатов/поиска в payload"
```

---

### Task 6: Фронт — типы полного множества статусов + api-слой с крошками

**Files:**
- Modify: `frontend/src/lib/types.ts` (`MatchStatus`, `MatchRow`, `Candidate`)
- Modify: `frontend/src/lib/api/estimates.ts` (`RowDto`, `rowFromDto`:58, `patchRowReview`:~195)
- Modify: `frontend/src/lib/api/articles.ts` (`searchArticles`:36)
- Modify: `frontend/src/lib/mock/fixtures.ts` (+ все тестовые литералы `MatchRow`, которые сломает компилятор)
- Modify: `frontend/src/lib/reviewState.test.ts` (снять casts `as unknown as` из пин-теста PR #20)
- Modify: `frontend/src/pages/estimate/EstimatePage.tsx` (передать prev в `patchRowReview`)
- Test: `frontend/src/lib/api/estimates.test.ts`, `frontend/src/lib/api/articles.test.ts` (дополнить)

**Interfaces:**
- Consumes: контракт Task 5 (`breadcrumb`/`matched_breadcrumb`/`match_error`/`source_index` в RowDto; `breadcrumb` в кандидатах и результатах поиска; PATCH-ответ крошек НЕ несёт).
- Produces:
  - `MatchStatus = "pending" | "excluded" | "confident" | "needs_review" | "no_match" | "error" | "matched_fund"`;
  - `MatchRow` += `sourceIndex: number`, `breadcrumb: string[]`, `matchedBreadcrumb: string[]`, `finalBreadcrumb: string[]`, `matchError: string | null`;
  - `Candidate` += `breadcrumb: string[]`;
  - `rowFromDto(r: RowDto, prev?: MatchRow): MatchRow` — merge-семантика;
  - `patchRowReview(estimateId: number, rowId: number, action: "confirm" | "pick" | "reject", articleId?: number, prev?: MatchRow)` — фактическая сигнатура (estimates.ts:190) + новый хвостовой prev.
  - Task 7 и PR-B строятся на этих типах.

- [ ] **Step 1: Падающие тесты api-слоя**

В `frontend/src/lib/api/estimates.test.ts` (мокинг — `vi.spyOn(client, ...)`, стиль файла):

```tsx
it("rowFromDto мапит sourceIndex/breadcrumb/matchError и крошки кандидатов", () => {
  const dto = {
    ...BASE_ROW_DTO, // сверь имя базовой фикстуры RowDto в файле; нет — собери литерал
    source_index: 12,
    breadcrumb: ["Конструктив", "Подземная часть"],
    matched_breadcrumb: ["03 Фундаменты"],
    match_error: null,
    candidates: [
      { id: 3, code: "03.04", name: "Фунд.", score: 0.7, breadcrumb: ["03 Фундаменты"] },
    ],
  }
  const row = rowFromDto(dto)
  expect(row.sourceIndex).toBe(12)
  expect(row.breadcrumb).toEqual(["Конструктив", "Подземная часть"])
  expect(row.matchedBreadcrumb).toEqual(["03 Фундаменты"])
  expect(row.candidates[0].breadcrumb).toEqual(["03 Фундаменты"])
})

it("rowFromDto: PATCH-ответ без крошек наследует их из prev", () => {
  const prev = rowFromDto({
    ...BASE_ROW_DTO,
    source_index: 12,
    breadcrumb: ["Конструктив"],
    matched_breadcrumb: ["03 Фундаменты"],
    candidates: [
      { id: 3, code: "03.04", name: "Фунд.", score: 0.7, breadcrumb: ["03 Фундаменты"] },
    ],
  })
  const afterPatch = rowFromDto(
    { ...BASE_ROW_DTO, review_status: "confirmed",
      breadcrumb: [], // PATCH-ответ: дефолтные пустые крошки — merge обязан взять prev
      matched_breadcrumb: [],
      candidates: [{ id: 3, code: "03.04", name: "Фунд.", score: 0.7 }] },
    prev
  )
  expect(afterPatch.breadcrumb).toEqual(["Конструктив"])
  expect(afterPatch.sourceIndex).toBe(12)
  expect(afterPatch.matchedBreadcrumb).toEqual(["03 Фундаменты"])
  expect(afterPatch.candidates[0].breadcrumb).toEqual(["03 Фундаменты"])
})
```

В `articles.test.ts`: `searchArticles` мапит `breadcrumb` из ответа (`?? []` для старого бэка).

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/lib/api`
Expected: FAIL (нет полей).

- [ ] **Step 3: Реализация**

`types.ts`:

```ts
export type MatchStatus =
  | "pending" // матчинг ещё не завершён
  | "excluded" // орг-заголовок: контекст, НЕ решается в ревью
  | "confident"
  | "needs_review"
  | "no_match"
  | "error"
  | "matched_fund"
```

`MatchRow` — добавь после `source_name`:

```ts
  sourceIndex: number // порядок исходного документа (полоса контекста, PR-B)
  breadcrumb: string[] // ПОЛНАЯ цепочка предков (включая org) — крошка карточки
  matchError: string | null // текст ошибки для status="error"
```

после `matched_article_id`: `matchedBreadcrumb: string[]`; после `final_article_id`:
`finalBreadcrumb: string[] // крошка статьи решения (выбор из поиска ≠ кандидаты)`.
В `Candidate` — `breadcrumb: string[]`.

`estimates.ts`: в `RowDto` добавь опциональные (защитно, как соседние):

```ts
  source_index?: number
  breadcrumb?: string[]
  matched_breadcrumb?: string[]
  final_breadcrumb?: string[]
  match_error?: string | null
```

и в типе кандидата RowDto — `breadcrumb?: string[]`. `rowFromDto`:

```ts
export function rowFromDto(r: RowDto, prev?: MatchRow): MatchRow {
  const prevCandCrumbs = new Map(
    (prev?.candidates ?? []).map((c) => [c.article_code, c.breadcrumb])
  )
  return {
    // ...существующие поля как сейчас...
    sourceIndex: r.source_index ?? prev?.sourceIndex ?? 0,
    // ВАЖНО: merge через ПРОВЕРКУ ДЛИНЫ, не через ?? — PATCH-ответ несёт
    // breadcrumb: [] (дефолт DTO), и `??` затёр бы крошку prev пустым массивом
    breadcrumb:
      r.breadcrumb && r.breadcrumb.length > 0
        ? r.breadcrumb
        : (prev?.breadcrumb ?? []),
    matchedBreadcrumb:
      r.matched_breadcrumb && r.matched_breadcrumb.length > 0
        ? r.matched_breadcrumb
        : (prev?.matchedBreadcrumb ?? []),
    finalBreadcrumb:
      r.final_breadcrumb && r.final_breadcrumb.length > 0
        ? r.final_breadcrumb
        : (prev?.finalBreadcrumb ?? []),
    matchError: r.match_error ?? prev?.matchError ?? null,
    candidates: r.candidates.map(
      (c): Candidate => ({
        id: c.id,
        article_code: c.code,
        name: c.name,
        score: c.score,
        breadcrumb:
          c.breadcrumb && c.breadcrumb.length > 0
            ? c.breadcrumb
            : (prevCandCrumbs.get(c.code) ?? []),
      })
    ),
  }
}
```

`patchRowReview` — добавь параметр `prev?: MatchRow`, верни `rowFromDto(dto, prev)`. В `EstimatePage.tsx` в `handleReview` передай prev: `state.rows.find((r) => r.row_number === rowNumber)` (сверь фактические имена в функции).

`articles.ts` `searchArticles`: тип ответа `{ id: number; code: string; name: string; breadcrumb?: string[] }[]`, маппинг `breadcrumb: h.breadcrumb ?? []`.

`lib/mock/fixtures.ts` и все литералы `MatchRow`/`Candidate` в тестах: компилятор потребует новые обязательные поля — добавь механически (`sourceIndex: <порядковый>`, `breadcrumb: []`, `matchedBreadcrumb: []`, `finalBreadcrumb: []`, `matchError: null`, `breadcrumb: []` у кандидатов). Прогони `npm run typecheck` и чини по списку ошибок.

`reviewState.test.ts`: пин-тест excluded/pending из PR #20 использует `"excluded" as unknown as MatchRow["status"]` с комментарием-ссылкой на TECH_DEBT — теперь литералы легальны: убери casts и комментарий про TECH_DEBT (пункт гасится этим PR).

- [ ] **Step 4: Всё зелёное**

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS, 0 ошибок. Прогони также `npx prettier --check "src/**/*.{ts,tsx}"` и `npx eslint src` — чисто.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(front): полное множество статусов строки + крошки в api-слое (merge prev на PATCH)"
```

---

### Task 7: Фронт — excluded/pending в таблице: приглушение, честные лейблы, клавиатура мимо

**Files:**
- Modify: `frontend/src/lib/reviewState.ts` (`statusLabel`:173)
- Modify: `frontend/src/pages/estimate/ReviewRow.tsx` (муты/нераскрываемость/Badge)
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx` (queue:71-74)
- Test: `frontend/src/lib/reviewState.test.ts`, `frontend/src/pages/estimate/ReviewRow.test.tsx`, `frontend/src/pages/estimate/ReviewScreen.test.tsx`

**Interfaces:**
- Consumes: `requiresDecision` (позитивное перечисление, PR #20), типы Task 6, shadcn `Badge` (`@/components/ui/badge` — уже в проекте).
- Produces: контракт excluded на текущей таблице (спека §2b). Шапка «N строк СМР» сознательно не трогается (переписывается в PR-B) — счёт включает excluded, это известная косметика.

- [ ] **Step 1: Падающие тесты**

`reviewState.test.ts`:

```ts
it("statusLabel: excluded → «Контекст», pending → «В обработке»", () => {
  const ex = { ...base(), status: "excluded" as const }
  const pd = { ...base(), status: "pending" as const }
  expect(statusLabel(ex, { kind: "pending" })).toBe("Контекст")
  expect(statusLabel(pd, { kind: "pending" })).toBe("В обработке")
})
```

(хелпер `base()` в файле уже есть — сверь имя.)

`ReviewRow.test.tsx` (фикстуры/рендер — по образцу существующих тестов файла, обёртка таблицей как там):

```tsx
it("excluded-строка приглушена, не раскрывается и помечена «Контекст»", async () => {
  const row = { ...CONFIDENT_ROW, status: "excluded" as const } // сверь имя фикстуры
  render(...) // по паттерну файла, onToggle: vi.fn()
  const tr = screen.getByText(row.source_name).closest("tr")!
  expect(tr.className).toContain("opacity-60")
  expect(screen.getByText("Контекст")).toBeInTheDocument()
  await userEvent.click(tr)
  expect(onToggle).not.toHaveBeenCalled()
})
```

`ReviewScreen.test.tsx` — локальная обёртка с кастомными строками (существующий `Wrap` завязан
на `MOCK_ROWS` — не трогай его, добавь рядом):

```tsx
function WrapRows({ rows }: { rows: MatchRow[] }) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("смета.xlsx", rows)
  )
  return (
    <MemoryRouter>
      <ReviewScreen
        state={state}
        dispatch={dispatch}
        onExport={vi.fn()}
        onComplete={vi.fn()}
      />
    </MemoryRouter>
  )
}

it("клавиатура пропускает excluded и фонд-хиты: активна первая спорная", () => {
  const rows: MatchRow[] = [
    { ...MOCK_ROWS[0], row_number: 1, source_name: "Орг-заголовок",
      status: "excluded" },
    { ...MOCK_ROWS[0], row_number: 2, source_name: "Фонд-хит",
      status: "matched_fund", matched_code: "01.01", matched_name: "Статья" },
    { ...MOCK_ROWS[0], row_number: 3, source_name: "Спорная работа",
      status: "needs_review" },
  ]
  render(<WrapRows rows={rows} />)
  // авто-активная строка очереди раскрыта; это должна быть СПОРНАЯ, а не excluded/фонд
  const spornaya = screen.getByText("Спорная работа").closest("tr")!
  expect(spornaya).toHaveAttribute("data-state", "open")
  const org = screen.getByText("Орг-заголовок").closest("tr")!
  expect(org).toHaveAttribute("data-state", "closed")
})
```

(база `MOCK_ROWS[0]` — сверь, что это MatchRow-объект; поля-оверрайды выше делают статус
детерминированным. `data-state` уже выставляется в `ReviewRow` — см. tsx.)

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/lib/reviewState.test.ts src/pages/estimate/ReviewRow.test.tsx src/pages/estimate/ReviewScreen.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Реализация**

`reviewState.ts` `statusLabel` — первым делом, ДО проверок `d.kind` (у контекстных строк decision вечно pending — сначала статус):

```ts
  if (row.status === "excluded") return "Контекст"
  if (row.status === "pending") return "В обработке"
```

`ReviewRow.tsx`:

```ts
  const contextRow = row.status === "excluded" || row.status === "pending"
  // контекстные строки не решаются в ревью (спека этапа 2 §2b) — не раскрываем
  const expandable = !contextRow
```

(замени текущее `const expandable = true`; комментарий editable-confident-rows обнови — правило теперь «раскрываемо всё, КРОМЕ контекстных»).

- `<tr>`: к className при `contextRow` добавь `" opacity-60"` (и не добавляй `cursor-pointer`).
- Ячейка статьи: при `contextRow` рендери `<span className="text-muted-foreground">—</span>` (веткой ДО существующих).
- Ячейка score: пустая и для контекстных (`row.status !== "no_match" && row.status !== "matched_fund" && !contextRow`).
- Ячейка статуса: при `contextRow` — shadcn Badge (`import { Badge } from "@/components/ui/badge"`):

```tsx
{contextRow ? <Badge variant="outline">{label}</Badge> : (<>{/* текущий рендер */}</>)}
```

- **Exhaustive-контракт статусов (спека §2b «новый статус бэка ловится компиляцией»):**
  перетипируй карту тонов (ReviewRow.tsx:21) с `Record<string, string>` на
  `Record<MatchStatus, string>` и заполни ВСЕ семь ключей (для `excluded`/`pending` —
  `"text-muted-foreground"`). Теперь добавление статуса в `MatchStatus` без строки в карте —
  ошибка компиляции. Обращение `statusTone[row.status]` становится всегда определённым —
  убери `?? ""` (иначе eslint отметит бессмысленный nullish).

`ReviewScreen.tsx` (строки 69-74) — очередь от `requiresDecision`:

```ts
  // Очередь навигации = СПОРНЫЕ строки из видимого набора (requiresDecision —
  // позитивное зеркало бэкового _REVIEWABLE): excluded/pending/фонд-хиты
  // клавиатура обходит (спека этапа 2 §2b)
  const queue = useMemo(() => rows.filter(requiresDecision), [rows])
```

(импортируй `requiresDecision` из `@/lib/reviewState` — он уже экспортируется.)

- [ ] **Step 4: Всё зелёное**

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS. Если упали существующие тесты, опиравшиеся на «фонд-хит в очереди» — обнови их ожидания под новую семантику (queue = только спорные) и явно отметь это в отчёте.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(review): контракт excluded — приглушение, лейблы Контекст/В обработке, клавиатура мимо"
```

---

### Task 8: Финализация — полный прогон, ручные гейты, TECH_DEBT, devlog

**Files:**
- Modify: `docs/TECH_DEBT.md` (пункт «🟢 Этап 1 UX-роадмапа: полировка из ревью» — гашение подпунктов (4)–(5))
- Create: `docs/devlog/2026-07-03-ux-stage2-pr-a-contract.md` (формат — по соседям в docs/devlog/)

**Ручные гейты этой задачи выполняет КОНТРОЛЁР (сабагентам не исполнять):**

- [ ] **Step 1: Полная верификация**

Run (из корня): `just lint; just test; cd frontend; npm run typecheck; npm run build`
Expected: всё зелёное (бэк-база: 383+нов. passed / 3 skipped; фронт 141+нов.), сборка ок.

- [ ] **Step 2 (КОНТРОЛЁР): ручная сверка breadcrumb на живой dev-БД**

Скриптом через `uv run python`: загрузить строки сметы 16 (294 строки, 12 excluded, дубли кодов) из `DATABASE_URL`, прогнать логику `assert_breadcrumb_matches_crumb` из `tests/test_breadcrumb_guard.py` на реальных данных; отдельно — `GET /api/estimates/16` и глазами сверить `breadcrumb` у 2-3 глубоких строк с деревом в Excel-выгрузке/БД. Расхождения НЕ подгонять — фиксировать как находку (предохранитель стража).

- [ ] **Step 3 (КОНТРОЛЁР): браузерная проверка контракта excluded**

На живых dev-серверах (8260/5173): открыть смету с excluded-строками (16) → excluded приглушены с бейджем «Контекст», не раскрываются кликом; хоткей-навигация (Enter/цифры) не встаёт на них и на фонд-хиты; поиск в раскрытой спорной строке показывает крошки статей.

- [ ] **Step 4: TECH_DEBT + devlog**

- В пункте «Этап 1 UX-роадмапа: полировка из ревью»: подпункты (4) (тип `MatchStatus`) и (5) (очередь/statusLabel) — погашены этим PR: убери их из «Что»/«Почему»/«Как чинить», оставив (2)–(3); если пункт опустел бы — перенеси остаток и пометь погашенное датой по конвенции файла.
- Devlog: что сделано (ссылка на спеку этапа 2 §2), контракт payload (breadcrumb строки — полная цепочка; крошки статей; source_index/match_error; PATCH без крошек — merge prev), контракт excluded, страж-проекция (и результат сверки на dev-БД). Отложенное — не сюда, а в TECH_DEBT.

- [ ] **Step 5: Commit**

```bash
git add docs
git commit -m "docs: devlog PR-A этапа 2 + гашение TECH_DEBT (тип MatchStatus, очередь хоткеев)"
```

---

## Самопроверка покрытия спеки (§2 + §1)

| Требование спеки | Задача |
|---|---|
| `source_index` в payload | 1 |
| `match_error` в payload | 1 |
| `breadcrumb` строки — полная цепочка, позиционный пересчёт | 2, 5 |
| Страж-проекция (переиспользование `build_embedding_input`, прокси excluded⇔ORG, предохранитель) | 3 |
| Крошки кандидатов/рекомендации/поиска из дерева `parent_id`, fallback без `id` | 4, 5 |
| Крошка финального решения (`final_breadcrumb` — выбор через поиск вне кандидатов) | 5, 6 |
| `MatchStatus` полное множество + exhaustive-развилки | 6, 7 |
| Очередь хоткеев = `requiresDecision` | 7 |
| Приглушение + лейблы «Контекст»/«В обработке», нераскрываемость | 7 |
| PATCH-ответ без крошек → merge prev на фронте | 5 (контракт), 6 (merge) |
| Ручная сверка breadcrumb на dev-БД; браузерный гейт excluded | 8 |
| Гашение TECH_DEBT (4)–(5) | 8 |
| shadcn-first (Badge для лейблов; ui/ не править) | 7 + Global Constraints |
