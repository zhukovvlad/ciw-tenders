# Этап 2 / PR-B: экран ревью — очередь, карточка решения, грид, терминальные состояния — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Экран ревью, работающий на тысячах строк: дефолтный режим «Очередь» (карточка решения на первой нерешённой спорной строке + полоса контекста + хоткеи `1–3`/`0`/`Enter`/`N`/`←`), read-only виртуализированный грид под `?view=grid`, терминальный экран пустой очереди, undo-стек всех коммитов сессии, память карточки «откуда пришла»; плюс серверный guard «excluded не решается» и честная шапка «спорных решено X из Y».

**Architecture:** Слоистая (спека §1): редьюсер `reviewState` НЕ меняется (решения = зеркало сервера); поверх него новый сессионный in-memory слой `useReviewQueue` (порядок спорных по `sourceIndex`, skip-в-хвост, undo-стек, происхождение активной карточки, возврат в голову при ошибке PATCH); карточка/грид/полоса — презентационные компоненты над обоими. Режим — клиентский выбор, но адресуемый: `?view=grid` в URL, фаза сметы остаётся серверной (этап 1, маппинг статус→экран в `EstimatePage` не меняется). Контракт PR-A потребляется как есть: `breadcrumb`/`matched_breadcrumb`/`final_breadcrumb`/`candidates[].breadcrumb`/`source_index`/`match_error` уже в payload, merge `prev` в `rowFromDto` — ТОЛЬКО для `breadcrumb` строки (запиновано, не расширять).

**Виртуализация — `@tanstack/react-virtual` v3 (новая зависимость, впервые в проекте).** Обоснование выбора: (1) headless — ноль навязанной разметки и стилей, грид остаётся div-версткой в визуальном языке shadcn Table и токенах MR DS (конвенция shadcn-first); (2) ~4 КБ gzip, без транзитивных зависимостей; (3) есть `scrollToIndex`/`scrollToOffset` — ровно то, что нужно памяти позиции «к таблице» и скроллу к активной строке; (4) фиксированная высота строки = `estimateSize` без measure-цикла; (5) поддерживается TanStack, совместим с React 19; (6) тестируем в jsdom через опцию `initialRect` (без реального layout). Отвергнуто: `react-window` (навязывает собственные компоненты списка — sticky-шапка и table-семантика делаются «через не могу»), `react-virtuoso` (тяжелее, много встроенной магии, стили сложнее подчинить DS), ручная виртуализация (переизобретать overscan/scrollToIndex/пересчёт на resize — вложение не по величине задачи при наличии 4-КБ headless-решения).

**Tech Stack:** FastAPI (бэк — один guard), React 19 + TS strict + shadcn/ui (Card/Command/Badge/Button/Tabs/AlertDialog) + `@tanstack/react-virtual` (фронт), pytest / vitest + RTL.

**Спека:** [docs/superpowers/specs/2026-07-03-ux-stage2-review-screen-design.md](../specs/2026-07-03-ux-stage2-review-screen-design.md) §3 (+§1 таблица решений, §4 тесты/гейты, §5 вне скоупа). Роадмап: [2026-07-02-ux-roadmap-design.md](../specs/2026-07-02-ux-roadmap-design.md) §4.2e. PR-A (контракт, смержен в main PR #21): план [2026-07-03-ux-stage2-pr-a-contract.md](2026-07-03-ux-stage2-pr-a-contract.md), devlog [2026-07-03-ux-stage2-pr-a-contract.md](../devlog/2026-07-03-ux-stage2-pr-a-contract.md).

## Global Constraints

- Ветка: `feat/ux-stage2-pr-b-review-screen` ОТ `docs/ux-stage2-pr-b-plan` (план этого PR живёт там; сама ветка плана — от main, всё нужное уже в main после PR #21).
- Бэк: только `uv run` из `backend/`; ruff line-length 100; `from __future__ import annotations`; type hints обязательны; юнит-тесты НЕ ходят в реальную БД/AI (фейки портов + `app.dependency_overrides`); Clean Architecture `api → services → domain ← infrastructure`. База: 406 passed / 3 skipped.
- Фронт: **shadcn-first** (новая разметка из shadcn-примитивов; `src/components/ui/` не править руками — но ДОБАВЛЯТЬ вендорные компоненты через `npx shadcn@latest add <name>` можно); импорты `@/`; TS strict + `erasableSyntaxOnly` (без enum/parameter properties); Prettier `printWidth 80`, LF; typecheck = `npm run typecheck` (это `tsc -b`; `tsc --noEmit` без `-b` ничего не проверяет). База: vitest 150/150.
- Редьюсер `reviewState` (initReview/reviewReducer/decisionFromRow/decisionFor/progress/requiresDecision/filteredRows/statusLabel) НЕ менять — PR-B только потребляет его. Merge-семантика `rowFromDto(r, prev?)` запинована тестами PR-A — не расширять.
- Новые зависимости фронта: ровно две — `npm install @tanstack/react-virtual` (Task 7) и `npx shadcn@latest add command` (Task 5; принесёт транзитивный `cmdk`). Больше ничего не ставить.
- PowerShell 5.1: `;` вместо `&&`; для кириллицы в stdout Python — `PYTHONIOENCODING=utf-8`. Бэкенд-порт 8260, машина общая — чужие процессы не трогать, свои dev-серверы не поднимать без нужды (на 8260/5173 может висеть чей-то `--reload`).
- Conventional Commits, по одному коммиту на задачу.
- Обязательные ручные гейты (Task 10) выполняет контролёр — сабагентам их не исполнять и не пропускать.
- TECH_DEBT «Крошки статей: карта справочника грузится целиком» — сознательно НЕ чинить в этом PR (кэш только при росте справочника, порог — замер p95).

## Карта файлов

| Файл | Роль |
|---|---|
| `backend/app/domain/errors.py` (modify) | `RowNotReviewableError` — excluded не решается → 409 |
| `backend/app/services/estimate_review_service.py` (modify) | guard excluded в `apply()` |
| `backend/app/api/routes/estimates.py` (modify) | маппинг 409 + хелпер `_collect_article_ids` (гасит дубль из ревью PR-A) |
| `frontend/src/lib/useReviewQueue.ts` (create) | сессионный слой навигации очереди |
| `frontend/src/lib/useReviewKeyboard.ts` (modify) | + `0`, `←`, `canConfirm`, глушение при открытом диалоге |
| `frontend/src/components/estimate/CrumbTrail.tsx` (create) | крошка со средним эллипсисом |
| `frontend/src/components/ui/command.tsx` (create, vendored) | shadcn Command для поиска в карточке |
| `frontend/src/pages/estimate/ReviewCard.tsx` (create) | карточка решения (единственная поверхность решения) |
| `frontend/src/pages/estimate/ContextStrip.tsx` (create) | полоса контекста ±2 по `sourceIndex` |
| `frontend/src/pages/estimate/ReviewGrid.tsx` (create) | read-only виртуализированный грид |
| `frontend/src/pages/estimate/QueueDone.tsx` (create) | терминальный экран «все спорные решены» |
| `frontend/src/pages/estimate/ReviewScreen.tsx` (rewrite) | шелл: шапка + режимы очередь/грид + wiring |
| `frontend/src/pages/estimate/ReviewRow.tsx` (**delete**) | аккордеонная строка старой таблицы — заменена карточкой/гридом |
| `frontend/src/pages/estimate/EstimatePage.tsx` (modify) | `onReview → Promise<boolean>`, toast с именем строки, completed+`?view=grid` |

---

### Task 1: Бэк — серверный guard «excluded не решается» + хелпер `_collect_article_ids`

**Files:**
- Modify: `backend/app/domain/errors.py` (в конец файла, рядом с `RowNotMatchedError`:51)
- Modify: `backend/app/services/estimate_review_service.py` (guard после проверки pending, ~строка 42)
- Modify: `backend/app/api/routes/estimates.py` (роут `review_row`:169 — новый except; `get_estimate`:140 и `review_row` — общий хелпер вместо дублей set-comprehension на строках 150–154 и 193–196)
- Test: `backend/tests/test_estimate_review.py` (дополнить)

**Interfaces:**
- Consumes: `EstimateRowStatus.EXCLUDED = "excluded"` (entities.py:124), `RowNotMatchedError` (pending уже даёт 409 — errors.py:51, service:41-42, пин `test_review_pending_row_409`), фейк `estimate_repo.nodes[nid]["status"]` (fakes.py — прямая запись статуса в тесте), `StoredEstimateRow`.
- Produces: `RowNotReviewableError` (domain) → HTTP 409 на PATCH review excluded-строки; `_collect_article_ids(rows: Iterable[StoredEstimateRow]) -> list[int]` — модульный хелпер routes/estimates.py (двойной call site из PR-A гасится; карточка PR-B — потребитель обоих роутов). Фронту новых полей не нужно — контракт «excluded не решается» теперь держит и сервер (закрывает рекомендацию финального ревью PR-A).

- [ ] **Step 1: Падающий тест**

В `backend/tests/test_estimate_review.py` (фикстуры `client, auth_headers, estimate_repo, seed_estimate` и хелпер `_match` уже в файле):

```python
def test_review_excluded_row_409(client, auth_headers, estimate_repo, seed_estimate):
    """Спека этапа 2 §2b/§3: excluded — контекст, НЕ решается в ревью.
    До этого PR контракт держал только клиент (финальное ревью PR-A)."""
    eid, nid = seed_estimate
    estimate_repo.nodes[nid]["status"] = "excluded"
    for action in ({"action": "confirm"}, {"action": "reject"},
                   {"action": "pick", "article_id": 1}):
        resp = client.patch(
            f"/api/estimates/{eid}/rows/{nid}/review",
            headers=auth_headers, json=action,
        )
        assert resp.status_code == 409, action
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_review.py -v`
Expected: новый тест FAIL (сейчас `confirm` на excluded-строке проходит guard'ы — статус не pending — и падает по-другому или проходит; главное — не 409 на всех трёх действиях).

- [ ] **Step 3: Реализация**

`errors.py`, после `RowNotMatchedError`:

```python
class RowNotReviewableError(Exception):
    """Строка-контекст (excluded) не решается в ревью. → 409."""
```

`estimate_review_service.py`: импортируй `RowNotReviewableError` из `app.domain.errors` и `EstimateRowStatus` из `app.domain.entities`; после существующего guard'а pending (строки 41–42):

```python
        if row.status == str(EstimateRowStatus.EXCLUDED):
            raise RowNotReviewableError("Строка-контекст (excluded) не решается в ревью")
```

`routes/estimates.py`, в `review_row` — новый except рядом с существующими (порядок не важен, оба → 409):

```python
    except RowNotReviewableError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
```

(импорт `RowNotReviewableError` — в существующий блок `from app.domain.errors import (...)`.)

Там же — модульный хелпер (после констант, до роутов) и замена ОБОИХ дублей set-comprehension:

```python
def _collect_article_ids(rows: Iterable[StoredEstimateRow]) -> list[int]:
    """id статей, чьи крошки нужны payload'у: рекомендация + финал + кандидаты."""
    return sorted(
        {r.matched_article_id for r in rows if r.matched_article_id}
        | {r.final_article_id for r in rows if r.final_article_id}
        | {c.id for r in rows for c in r.candidates if c.id}
    )
```

- в `get_estimate` (строки 150–154): `ids = _collect_article_ids(est.rows)`;
- в `review_row` (строки 193–196): `ids = _collect_article_ids([row])` — комментарий про «крошка СТРОКИ не гидратируется здесь» сохранить как есть.

Импорты: `Iterable` — в существующий `from collections.abc import Callable` добавь `Iterable`; `StoredEstimateRow` — в существующий блок `from app.domain.entities import ...`.

- [ ] **Step 4: Зелёные + полный прогон**

Run: `cd backend; $env:PYTHONIOENCODING='utf-8'; uv run pytest tests/test_estimate_review.py tests/test_estimate_routes.py -v; uv run pytest -q; uv run ruff check .`
Expected: PASS; полный прогон без новых падений (база 406/3); ruff чист. Существующие тесты гидратации крошек (`test_patch_review_hydrates_final_breadcrumb`, detail-тесты) — зелёные: хелпер эквивалентен дублям.

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(estimates): серверный guard — review-PATCH на excluded даёт 409"
```

---

### Task 2: Фронт — `useReviewQueue`: сессионный слой навигации очереди

**Files:**
- Create: `frontend/src/lib/useReviewQueue.ts`
- Test: `frontend/src/lib/useReviewQueue.test.ts` (новый; `renderHook`/`act` из `@testing-library/react`)

**Interfaces:**
- Consumes: `ReviewState`, `MatchRow` (`@/lib/types`); `requiresDecision`, `decisionFor` (`@/lib/reviewState` — НЕ менять).
- Produces (Task 9 строит экран ровно на этом):

```ts
export type CardOrigin =
  | { kind: "flow" } // обычный поток очереди
  | { kind: "grid" } // открыта кликом из грида
  | { kind: "undo"; returnTo: number | null } // открыта через ←

export type CommitExit =
  | { kind: "next" } // поток: следующая нерешённая (activeRow обновится сам)
  | { kind: "grid" } // возврат в грид на прежнюю позицию скролла
  | { kind: "row"; rowNumber: number } // после ←: к строке, активной до ←

export interface ReviewQueue {
  queue: MatchRow[] // спорные (requiresDecision) в сессионном порядке
  activeRow: MatchRow | null // null ⇔ пустая очередь (терминальный экран)
  origin: CardOrigin
  canUndo: boolean
  openFromGrid: (rowNumber: number) => void // любая строка, включая confident/фонд
  /** N. Строка ИЗ порядка спорных — в хвост, exit {next}. Ad-hoc строка НЕ из
   * порядка (confident/фонд, открытая из грида) — порядок НЕ трогается,
   * карточка закрывается по origin: «пропустить» точечную правку = передумал,
   * уходи туда, откуда пришёл. */
  skip: () => CommitExit
  undo: () => void // ←: снять вершину стека, открыть с её решением; no-op на пустом
  committed: (rowNumber: number) => CommitExit // после dispatch решения (оптимистично)
  commitFailed: (rowNumber: number) => void // PATCH упал: из undo-стека вон, в голову очереди
  /** Сброс явного выбора (ручной уход в грид через таб): вернувшись в очередь,
   * оператор увидит поток, а не давно открытую из грида карточку. */
  deselect: () => void
}

export function useReviewQueue(state: ReviewState): ReviewQueue
```

**Семантика (спека §3a, дословно):**
- Порядок — спорные по `sourceIndex` возрастанию; сессионный (in-memory): после F5 исходный, undo-стек пуст.
- Активная — первая с `decisionFor(...).kind === "pending"` в сессионном порядке, либо явный выбор (`openFromGrid`, `undo`).
- `committed` пушит номер строки в undo-стек **всегда** (ad-hoc-решения из грида и после `←` — наравне с потоком) и возвращает, куда идти, по `origin` на момент коммита: `grid` → `{grid}` (явный выбор сбрасывается); `undo` c `returnTo` → `{row}` (и активной пиннится `returnTo` с origin `flow`); иначе `{next}` (сброс на авто).
- `undo()`: `returnTo` = текущая активная (или null); вершина стека становится активной с origin `{kind:"undo", returnTo}`. Перерешение открытой строки = существующий PATCH-перезапись — хук этим не занимается.
- `commitFailed(n)`: `n` удаляется из undo-стека (последнее вхождение — решение не состоялось); если `n` есть в сессионном порядке — переставляется в **голову**; текущая активная НЕ прыгает (если явного выбора не было — пиннится текущая активная, чтобы вернувшаяся строка стала следующей, а не немедленной). Строка не из очереди спорных (confident из грида) в порядок не добавляется — для неё достаточно toast+reopen (Task 9). **ВНИМАНИЕ, асинхронность:** `commitFailed` зовётся из `.then` PATCH-промиса — замыкание захвачено рендером ДО `committed()`, где активной была сама упавшая строка. Пиннинг обязан читать активную из **ref-на-последний-рендер** (`activeRowRef`), а не из замыкания — иначе ветка «cur !== n» даст false и оператора выдернет из текущей строки назад (запрещено этим же пунктом спеки). Воспроизводится юнитом «stale closure» ниже.
- Сессионный порядок пересобирается только при смене **набора** спорных строк (загрузка сметы); `syncRow`-обновления объектов строк порядок не трогают.

- [ ] **Step 1: Падающие тесты**

Создай `frontend/src/lib/useReviewQueue.test.ts`:

```ts
import { describe, expect, it } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { useReviewQueue } from "@/lib/useReviewQueue"
import { initReview } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

function row(
  n: number,
  si: number,
  status: MatchStatus = "needs_review",
  over: Partial<MatchRow> = {}
): MatchRow {
  return {
    row_number: n,
    section_code: `1.${n}`,
    source_name: `Строка ${n}`,
    sourceIndex: si,
    breadcrumb: [],
    matchError: null,
    status,
    score: 0.8,
    matched_code: "01.01",
    matched_name: "Статья",
    matched_article_id: 7,
    matchedBreadcrumb: [],
    candidates: [],
    review_status: "unreviewed",
    final_article_id: null,
    finalBreadcrumb: [],
    final_code: null,
    final_name: null,
    ...over,
  }
}

// ВНИМАНИЕ: sourceIndex нарочно не совпадает с row_number — очередь
// сортируется по ПОРЯДКУ ДОКУМЕНТА, а не по id строки
const ROWS: MatchRow[] = [
  row(10, 5), // спорная, в документе ПОСЛЕ строки 20
  row(20, 1), // спорная, первая по документу
  row(30, 2, "confident"), // не в очереди
  row(40, 3, "excluded"), // не в очереди
  row(50, 4, "no_match", { matched_code: null, matched_name: null,
    matched_article_id: null }),
]

function setup(rows: MatchRow[] = ROWS) {
  const state = initReview("смета.xlsx", rows)
  return renderHook(() => useReviewQueue(state))
}

describe("useReviewQueue: порядок и активная", () => {
  it("очередь = спорные по sourceIndex; активная — первая нерешённая", () => {
    const { result } = setup()
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "flow" })
    expect(result.current.canUndo).toBe(false)
  })

  it("пустая очередь: activeRow === null", () => {
    const { result } = setup([row(1, 1, "confident"), row(2, 2, "excluded")])
    expect(result.current.queue).toEqual([])
    expect(result.current.activeRow).toBeNull()
  })
})

describe("useReviewQueue: skip (N)", () => {
  it("активная уходит в хвост, следующей встаёт очередная нерешённая", () => {
    const { result } = setup()
    let exit
    act(() => {
      exit = result.current.skip()
    })
    expect(exit).toEqual({ kind: "next" })
    expect(result.current.activeRow?.row_number).toBe(50)
    expect(result.current.queue.map((r) => r.row_number)).toEqual([50, 10, 20])
  })

  it("N на ad-hoc строке из грида (не в порядке спорных): порядок цел, выход в грид", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30)) // confident — не в очереди
    let exit
    act(() => {
      exit = result.current.skip()
    })
    expect(exit).toEqual({ kind: "grid" })
    // confident-строка НЕ просочилась в очередь спорных
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(20) // выбор сброшен
  })
})

describe("useReviewQueue: deselect (ручной уход в грид табом)", () => {
  it("сбрасывает явный выбор — очередь возвращается к потоку", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    act(() => result.current.deselect())
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "flow" })
  })
})

describe("useReviewQueue: committed / undo (←)", () => {
  it("поток: committed → {next}, пушит undo-стек", () => {
    const { result } = setup()
    let exit
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "next" })
    expect(result.current.canUndo).toBe(true)
  })

  it("← открывает последнюю закоммиченную; committed после ← → {row: прежняя}", () => {
    const { result } = setup()
    act(() => void result.current.committed(20))
    // активной стала следующая (50); ← возвращает к 20
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "undo", returnTo: 50 })
    let exit
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "row", rowNumber: 50 })
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("← на пустом стеке — no-op", () => {
    const { result } = setup()
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(20)
  })
})

describe("useReviewQueue: открытие из грида", () => {
  it("openFromGrid делает активной любую строку, включая confident", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    expect(result.current.activeRow?.row_number).toBe(30)
    expect(result.current.origin).toEqual({ kind: "grid" })
  })

  it("committed из грида → {grid}; ad-hoc решение пушится в undo наравне", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    let exit
    act(() => {
      exit = result.current.committed(30)
    })
    expect(exit).toEqual({ kind: "grid" })
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(30)
  })
})

describe("useReviewQueue: ошибка PATCH", () => {
  it("commitFailed: строка в голову порядка, из undo-стека вон, активная не прыгает", () => {
    const { result } = setup()
    act(() => void result.current.committed(20)) // активной стала 50
    act(() => result.current.commitFailed(20))
    expect(result.current.canUndo).toBe(false)
    // 20 в голове сессионного порядка…
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    // …но активная осталась 50 (запинована) — 20 станет следующей
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("commitFailed для строки не из очереди (confident) порядок не трогает", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    act(() => void result.current.committed(30))
    act(() => result.current.commitFailed(30))
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
  })

  it("STALE CLOSURE: commitFailed из рендера ДО коммита не выдёргивает оператора", () => {
    // Прод-сценарий: commit(A) захватывает queue рендера R0 (активная A=20),
    // committed(20) двигает активную на 50, PATCH падает ПОЗЖЕ — .then зовёт
    // commitFailed из СТАРОГО замыкания. Пиннинг обязан читать активную из
    // ref-на-последний-рендер, иначе «cur !== n» видит A===A и не пиннит →
    // активная прыгает назад на 20 (запрещено спекой §3a).
    const { result } = setup()
    const stale = result.current // ← замыкание рендера до коммита
    act(() => void result.current.committed(20)) // активная стала 50
    act(() => stale.commitFailed(20)) // асинхронный фейл со старым замыканием
    expect(result.current.activeRow?.row_number).toBe(50) // осталась 50
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
  })
})
```

Нюанс `committed(20) → активной стала 50`: в тестах state иммутабелен (нет dispatch), поэтому «решённость» строки 20 хук из `decisionFor` не увидит. Значит `committed` при exit `{next}` обязан явно пропустить закоммиченную строку — реализация ниже держит `lastCommitted`-набор сессии ИЛИ пиннит следующую. Правильная реализация: хук ведёт собственный набор `sessionDecided: Set<number>` (пополняется в `committed`, чистится в `commitFailed`), и «нерешённая» = `decisionFor(...).kind === "pending" && !sessionDecided.has(n)`. Это же делает хук честным при оптимистичных коммитах до ответа PATCH.

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/lib/useReviewQueue.test.ts`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Реализация**

Создай `frontend/src/lib/useReviewQueue.ts`:

```ts
// Сессионный (in-memory) слой навигации очереди ревью — спека этапа 2 §3a.
// reviewState НЕ трогает: решения остаются зеркалом сервера; здесь живёт только
// порядок/активная/undo текущей сессии (F5 всё сбрасывает — это by design).
import { useMemo, useRef, useState } from "react"
import type { MatchRow, ReviewState } from "@/lib/types"
import { decisionFor, requiresDecision } from "@/lib/reviewState"

export type CardOrigin =
  | { kind: "flow" }
  | { kind: "grid" }
  | { kind: "undo"; returnTo: number | null }

export type CommitExit =
  | { kind: "next" }
  | { kind: "grid" }
  | { kind: "row"; rowNumber: number }

export interface ReviewQueue {
  queue: MatchRow[]
  activeRow: MatchRow | null
  origin: CardOrigin
  canUndo: boolean
  openFromGrid: (rowNumber: number) => void
  skip: () => void
  undo: () => void
  committed: (rowNumber: number) => CommitExit
  commitFailed: (rowNumber: number) => void
}

interface Selection {
  row: number
  origin: CardOrigin
}

export function useReviewQueue(state: ReviewState): ReviewQueue {
  const initialOrder = () =>
    state.rows
      .filter(requiresDecision)
      .sort((a, b) => a.sourceIndex - b.sourceIndex)
      .map((r) => r.row_number)

  const [order, setOrder] = useState<number[]>(initialOrder)
  const [undoStack, setUndoStack] = useState<number[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  // Решённые В ЭТОЙ СЕССИИ (оптимистично, до/независимо от ответа PATCH):
  // decisionFor обновится только после dispatch снаружи — хук не ждёт этого.
  const sessionDecided = useRef<Set<number>>(new Set())

  // Пересборка порядка ТОЛЬКО при смене набора спорных (загрузка новой сметы);
  // ключ — отсортированные row_number, чтобы syncRow-обновления не сбивали сессию.
  const idsKey = state.rows
    .filter(requiresDecision)
    .map((r) => r.row_number)
    .sort((a, b) => a - b)
    .join(",")
  const idsKeyRef = useRef(idsKey)
  if (idsKeyRef.current !== idsKey) {
    idsKeyRef.current = idsKey
    setOrder(initialOrder())
    setUndoStack([])
    setSelection(null)
    sessionDecided.current = new Set()
  }

  const byNum = useMemo(
    () => new Map(state.rows.map((r) => [r.row_number, r])),
    [state.rows]
  )

  const queue = useMemo(
    () =>
      order
        .map((n) => byNum.get(n))
        .filter((r): r is MatchRow => r !== undefined),
    [order, byNum]
  )

  const isPending = (r: MatchRow) =>
    decisionFor(state, r).kind === "pending" &&
    !sessionDecided.current.has(r.row_number)

  const autoActive = queue.find(isPending) ?? null
  const activeRow = selection
    ? (byNum.get(selection.row) ?? null)
    : autoActive
  const origin: CardOrigin = selection?.origin ?? { kind: "flow" }

  // Свежая активная для АСИНХРОННЫХ вызовов (commitFailed из .then PATCH-а):
  // замыкание там — из рендера до committed(), где активной была сама упавшая
  // строка; читать её из замыкания нельзя (пин-тест «STALE CLOSURE»)
  const activeRowRef = useRef(activeRow)
  activeRowRef.current = activeRow

  const exitFor = (o: CardOrigin): CommitExit =>
    o.kind === "grid"
      ? { kind: "grid" }
      : o.kind === "undo" && o.returnTo !== null
        ? { kind: "row", rowNumber: o.returnTo }
        : { kind: "next" }

  const openFromGrid = (rowNumber: number) =>
    setSelection({ row: rowNumber, origin: { kind: "grid" } })

  const deselect = () => setSelection(null)

  const skip = (): CommitExit => {
    const n = activeRow?.row_number
    if (n === undefined) return { kind: "next" }
    if (!order.includes(n)) {
      // Ad-hoc строка (confident/фонд из грида): «пропустить» = передумал —
      // порядок спорных НЕ загрязняем, уходим туда, откуда пришли
      const exit = exitFor(origin)
      if (exit.kind === "row")
        setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
      else setSelection(null)
      return exit
    }
    setOrder((o) => [...o.filter((x) => x !== n), n])
    setSelection(null)
    return { kind: "next" }
  }

  const undo = () => {
    if (undoStack.length === 0) return
    const top = undoStack[undoStack.length - 1]
    const returnTo = activeRow?.row_number ?? null
    setUndoStack((s) => s.slice(0, -1))
    sessionDecided.current.delete(top) // строка снова «в работе»
    setSelection({ row: top, origin: { kind: "undo", returnTo } })
  }

  const committed = (rowNumber: number): CommitExit => {
    setUndoStack((s) => [...s, rowNumber])
    sessionDecided.current.add(rowNumber)
    const exit = exitFor(origin)
    if (exit.kind === "row")
      setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
    else setSelection(null)
    return exit
  }

  const commitFailed = (rowNumber: number) => {
    setUndoStack((s) => {
      const i = s.lastIndexOf(rowNumber)
      return i === -1 ? s : [...s.slice(0, i), ...s.slice(i + 1)]
    })
    sessionDecided.current.delete(rowNumber)
    setOrder((o) =>
      o.includes(rowNumber)
        ? [rowNumber, ...o.filter((x) => x !== rowNumber)]
        : o
    )
    // Не выдёргивать оператора из текущей строки: пиннуть её, если явного
    // выбора не было — вернувшаяся строка станет СЛЕДУЮЩЕЙ (голова очереди).
    // ВАЖНО: активная — из ref-а, НЕ из замыкания: commitFailed зовётся из
    // .then PATCH-а, а замыкание захвачено рендером ДО committed(), где
    // активной была сама упавшая строка (пин-тест «STALE CLOSURE»)
    setSelection((prev) => {
      if (prev) return prev
      const cur = activeRowRef.current
      return cur && cur.row_number !== rowNumber
        ? { row: cur.row_number, origin: { kind: "flow" } }
        : null
    })
  }

  return {
    queue,
    activeRow,
    origin,
    canUndo: undoStack.length > 0,
    openFromGrid,
    skip,
    undo,
    committed,
    commitFailed,
    deselect,
  }
}
```

Нюанс реализации: `setOrder` во время рендера (ветка `idsKeyRef`) — легальный React-паттерн «derived state reset» (setState during render того же компонента); если eslint `react-hooks` возразит — перенести сброс в `useEffect` с тем же ключом и явно отметить это отклонение в отчёте.

- [ ] **Step 4: Зелёные + гигиена**

Run: `cd frontend; npx vitest run src/lib/useReviewQueue.test.ts; npm run typecheck; npx eslint src/lib/useReviewQueue.ts`
Expected: PASS, 0 ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(review): useReviewQueue — сессионный слой очереди (skip, undo, происхождение, голова при ошибке)"
```

---

### Task 3: Фронт — клавиатура: `0`, `←`, `canConfirm`, глушение при открытом диалоге

**Files:**
- Modify: `frontend/src/lib/useReviewKeyboard.ts`
- Test: `frontend/src/lib/useReviewKeyboard.test.tsx` (дополнить)

**Interfaces:**
- Consumes: текущий `useReviewKeyboard({enabled, candidateCount, onPick, onConfirm, onNext})`.
- Produces (обратная совместимость — новые поля опциональны, старый `ReviewScreen` компилируется до Task 9):

```ts
interface Options {
  enabled: boolean
  candidateCount: number
  /** Enter активен ⇔ рекомендация отрисована (правило карточки: клавиша ⇔ элемент). Default true. */
  canConfirm?: boolean
  onPick: (index: number) => void
  onConfirm: () => void
  onNext: () => void
  /** 0 — «оставить без пары» */
  onReject?: () => void
  /** ← — undo; no-op при пустом стеке решает вызывающий */
  onUndo?: () => void
}
```

Глушение — единая точка (спека §3b): фокус в инпуте (`isEditable`, уже есть) ИЛИ открыт Radix-диалог.

- [ ] **Step 1: Падающие тесты**

Дополни `useReviewKeyboard.test.tsx` (харнесс `Harness` уже есть — он принимает пропсы хука как есть):

```tsx
it("0 зовёт onReject, ArrowLeft — onUndo", async () => {
  const onReject = vi.fn(),
    onUndo = vi.fn()
  render(
    <Harness
      enabled
      candidateCount={0}
      onPick={vi.fn()}
      onConfirm={vi.fn()}
      onNext={vi.fn()}
      onReject={onReject}
      onUndo={onUndo}
    />
  )
  await userEvent.keyboard("0")
  expect(onReject).toHaveBeenCalled()
  await userEvent.keyboard("{ArrowLeft}")
  expect(onUndo).toHaveBeenCalled()
})

it("canConfirm=false: Enter не зовёт onConfirm (error/no_match без рекомендации)", async () => {
  const onConfirm = vi.fn()
  render(
    <Harness
      enabled
      candidateCount={0}
      canConfirm={false}
      onPick={vi.fn()}
      onConfirm={onConfirm}
      onNext={vi.fn()}
    />
  )
  await userEvent.keyboard("{Enter}")
  expect(onConfirm).not.toHaveBeenCalled()
})

it("глушится, когда открыт диалог (role=alertdialog data-state=open)", async () => {
  const onNext = vi.fn()
  render(
    <>
      <Harness
        enabled
        candidateCount={0}
        onPick={vi.fn()}
        onConfirm={vi.fn()}
        onNext={onNext}
      />
      <div role="alertdialog" data-state="open" />
    </>
  )
  await userEvent.keyboard("n")
  expect(onNext).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/lib/useReviewKeyboard.test.tsx`
Expected: FAIL (нет пропсов/поведения).

- [ ] **Step 3: Реализация**

В `useReviewKeyboard.ts`: расширь `Options` как в Interfaces; в начале handler'а (после `isEditable`-гейта):

```ts
      // Единая точка глушения хоткеев при модалке (спека §3b): Radix держит
      // data-state="open" на контенте диалога
      if (
        document.querySelector(
          '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]'
        )
      )
        return
```

Ветки клавиш: Enter — только при `canConfirm !== false`; добавь:

```ts
      } else if (e.key === "0") {
        e.preventDefault()
        onReject?.()
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        onUndo?.()
      }
```

Deps эффекта дополни новыми значениями (`canConfirm, onReject, onUndo`).

- [ ] **Step 4: Всё зелёное (включая старые тесты хука и ReviewScreen)**

Run: `cd frontend; npx vitest run; npm run typecheck`
Expected: PASS — новые поля опциональны, существующие вызовы не тронуты.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(review): хоткеи 0 и ← + гейт canConfirm + глушение при открытом диалоге"
```

---

### Task 4: Фронт — `CrumbTrail`: крошка со средним эллипсисом

**Files:**
- Create: `frontend/src/components/estimate/CrumbTrail.tsx`
- Test: `frontend/src/components/estimate/CrumbTrail.test.tsx`

**Interfaces:**
- Produces: `CrumbTrail({ levels, className }: { levels: string[]; className?: string })` — рендерит цепочку имён с разделителем `›`; правило усечения (спека §3b): ≤3 уровней — все; >3 — **первый › … › два последних** (первый и последние уровни всегда видимы); полная цепочка — в `title` (ховер). `levels === []` → `null`. Потребители: карточка (крошка строки — muted, крошки статей у рекомендации/кандидатов/поиска), Task 5.

- [ ] **Step 1: Падающие тесты**

```tsx
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { CrumbTrail } from "@/components/estimate/CrumbTrail"

describe("CrumbTrail", () => {
  it("короткая цепочка — все уровни", () => {
    render(<CrumbTrail levels={["Раздел 1", "Конструктив", "Подземная часть"]} />)
    const el = screen.getByText(/Раздел 1/)
    expect(el.textContent).toBe("Раздел 1 › Конструктив › Подземная часть")
  })

  it("длинная цепочка — средний эллипсис: первый + два последних", () => {
    render(
      <CrumbTrail
        levels={["Раздел 1", "ООО Длинное Юридическое", "Этап 2", "Конструктив",
          "2.4 Подземная часть"]}
      />
    )
    const el = screen.getByText(/Раздел 1/)
    expect(el.textContent).toBe(
      "Раздел 1 › … › Конструктив › 2.4 Подземная часть"
    )
    // полная цепочка доступна ховером
    expect(el).toHaveAttribute(
      "title",
      "Раздел 1 › ООО Длинное Юридическое › Этап 2 › Конструктив › 2.4 Подземная часть"
    )
  })

  it("пустая цепочка — ничего не рендерит", () => {
    const { container } = render(<CrumbTrail levels={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/components/estimate/CrumbTrail.test.tsx`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Реализация**

```tsx
// Крошка иерархии со средним эллипсисом (спека этапа 2 §3b): цепочка полная
// (включая org-уровни с длинными юр.названиями), при >3 уровней видимы первый
// и два последних; полная цепочка — в title.
import { cn } from "@/lib/utils"

const SEP = " › "

interface CrumbTrailProps {
  levels: string[]
  className?: string
}

export function CrumbTrail({ levels, className }: CrumbTrailProps) {
  if (levels.length === 0) return null
  const shown =
    levels.length <= 3
      ? levels
      : [levels[0], "…", ...levels.slice(-2)]
  return (
    <span
      title={levels.join(SEP)}
      className={cn("text-xs text-muted-foreground", className)}
    >
      {shown.join(SEP)}
    </span>
  )
}
```

(`cn` — существующий хелпер `@/lib/utils`, сверь наличие; если его нет — используй конкатенацию className как в соседних компонентах.)

- [ ] **Step 4: Зелёные**

Run: `cd frontend; npx vitest run src/components/estimate/CrumbTrail.test.tsx; npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(review): CrumbTrail — крошка иерархии со средним эллипсисом"
```

---

### Task 5: Фронт — карточка решения `ReviewCard` (+ вендоринг shadcn Command)

**Files:**
- Create: `frontend/src/components/ui/command.tsx` (вендорится CLI — руками не писать)
- Create: `frontend/src/pages/estimate/ReviewCard.tsx`
- Modify: `frontend/src/test/setup.ts` (полифилл `scrollIntoView` для cmdk в jsdom — если тесты попросят)
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

**Interfaces:**
- Consumes: `MatchRow`, `Candidate`, `Decision` (`@/lib/types`); `searchArticles` (`@/lib/api/articles` — серверный поиск, дебаунс-паттерн из бывшего `ReviewRow`); `CrumbTrail` (Task 4); shadcn `Card`, `Badge`, `Button`, `Command` (`CommandInput`/`CommandList`/`CommandItem`/`CommandEmpty`).
- Produces:

```ts
interface ReviewCardProps {
  row: MatchRow
  decision: Decision // подсветка выбранного (перерешение открытой из грида/после ←)
  canUndo: boolean // легенда: ← приглушена на пустом стеке
  onConfirmRecommendation: () => void // Enter
  onPickCandidate: (c: Candidate) => void // 1–3
  onManualPick: (c: Candidate) => void // выбор из поиска
  onReject: () => void // 0 — оставить без пары
  searchDebounceMs?: number // default 250; тесты передают 0
}
```

Хоткеи живут НЕ здесь (их вешает экран, Task 9) — карточка только рендерит и зовёт колбэки по кликам. Экспортируй хелпер-гейт для экрана:

```ts
/** Enter активен ⇔ блок рекомендации отрисован (правило: клавиша ⇔ элемент) */
export function hasRecommendation(row: MatchRow): boolean {
  return (
    row.status !== "error" &&
    row.matched_code !== null &&
    row.matched_name !== null
  )
}
```

Корневой `Card` несёт **`data-testid="review-card"`** — обязательный якорь: полоса контекста (Task 6) дублирует имена соседних строк в DOM, поэтому все ассерты «чья карточка открыта» в тестах экрана (Task 9) скоупятся `within(getByTestId("review-card"))`, а не `screen.getByText` (иначе тест зелёный при чужой активной карточке — ложноположительный сьют).

**Содержимое сверху вниз (спека §3b, дословно):**
1. Крошка сметы: `<CrumbTrail levels={row.breadcrumb} />` (muted; средний эллипсис уже внутри).
2. Работа: `row.section_code` (font-mono muted) + `row.source_name` **полным текстом, без клампа**.
3. Рекомендация (если `hasRecommendation(row)`): лейбл «Из фонда» (`status === "matched_fund"`, с иконкой `Database`) / «Рекомендация AI» — гейт синтетической рекомендации переезжает из `ReviewRow` без изменений: **отдельный блок** рендерится только если `matched_code` не входит в `candidates` (иначе рекомендация — это подсвеченный кандидат); + `<CrumbTrail levels={row.matchedBreadcrumb} />` + score (`row.score.toFixed(2)`, кроме `matched_fund`) + `<kbd>Enter</kbd>`.
4. Кандидаты: кнопки с `<kbd>{i+1}</kbd>`, код (font-mono), имя, `<CrumbTrail levels={c.breadcrumb} />`, score. Подсветка выбранного — по `decision.kind === "confirmed" && decision.code === c.article_code` (стиль `border-primary shadow-[var(--ds-glow-violet)]` — как в бывшем `ReviewRow`).
5. Поиск: shadcn `Command` c `shouldFilter={false}` (фильтрует сервер!), `CommandInput` с плейсхолдером «Нет верного — искать в справочнике…», дебаунс 250 мс (паттерн `reqIdRef` из бывшего `ReviewRow.tsx:60-75` — перенести дословно), результаты `CommandItem` (код + имя + `CrumbTrail`) → `onManualPick`. Проп `searchDebounceMs = 250` — тесты передают 0.
6. Кнопка «Оставить без пары» + `<kbd>0</kbd>`.
7. Постоянная легенда клавиш: `1–3` выбрать кандидата · `0` без пары · `Enter` подтвердить рекомендацию · `N` пропустить · `←` вернуться. Неактивные (нет кандидатов / `!hasRecommendation` / `!canUndo`) — `opacity-50`.

**Error-строки** (`status === "error"`): вместо блоков 3–4 — текст `row.matchError` (в `Alert variant="destructive"` или text-destructive блоке) с бейджем «Ошибка обработки»; поиск и «без пары» остаются; легенда показывает `1–3`/`Enter` приглушёнными. «Повторить обработку» — вне скоупа (спека §5).

**`no_match`-строки**: `hasRecommendation` даёт false при `matched_* === null` → блока рекомендации нет, Enter в легенде приглушён; кандидаты, если вектор что-то вернул, — доступны; иначе поиск и `0`.

- [ ] **Step 1: Вендорить Command**

Run: `cd frontend; npx shadcn@latest add command --yes`
Expected: появился `src/components/ui/command.tsx`, в `package.json` — `cmdk`. Файл вендорный — НЕ править. Если CLI спросит про перезапись чего-либо существующего — не перезаписывать, доложить.

Прогони `npx vitest run` — если cmdk уронит jsdom на `scrollIntoView`, добавь в `src/test/setup.ts`:

```ts
// cmdk (shadcn Command) зовёт scrollIntoView, которого нет в jsdom
Element.prototype.scrollIntoView ??= () => {}
```

- [ ] **Step 2: Падающие тесты**

Создай `frontend/src/pages/estimate/ReviewCard.test.tsx`. Локальный `row()`-хелпер — как в Task 2 (продублируй, задачи читаются независимо). Мок поиска — `vi.mock("@/lib/api/articles")`:

```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReviewCard, hasRecommendation } from "@/pages/estimate/ReviewCard"
import { searchArticles } from "@/lib/api/articles"
import type { Candidate, MatchRow, MatchStatus } from "@/lib/types"

vi.mock("@/lib/api/articles", () => ({ searchArticles: vi.fn() }))

// row(...) — хелпер как в useReviewQueue.test.ts (см. Task 2 Step 1)

const CAND: Candidate = {
  id: 3, article_code: "03.04", name: "Фундаменты под оборудование",
  score: 0.71, breadcrumb: ["03 Фундаменты и основания"],
}

function renderCard(r: MatchRow, over: Partial<Parameters<typeof ReviewCard>[0]> = {}) {
  const props = {
    row: r,
    decision: { kind: "pending" as const },
    canUndo: false,
    onConfirmRecommendation: vi.fn(),
    onPickCandidate: vi.fn(),
    onManualPick: vi.fn(),
    onReject: vi.fn(),
    searchDebounceMs: 0,
    ...over,
  }
  render(<ReviewCard {...props} />)
  return props
}

describe("ReviewCard: спорная строка", () => {
  const r = row(5, 2, "needs_review", {
    breadcrumb: ["Раздел 1", "Конструктив"],
    matchedBreadcrumb: ["03 Фундаменты и основания"],
    candidates: [CAND],
  })

  it("крошка строки, полный текст работы, рекомендация с крошкой и score", () => {
    renderCard(r)
    expect(screen.getByText(/Раздел 1 › Конструктив/)).toBeInTheDocument()
    expect(screen.getByText("Строка 5")).toBeInTheDocument()
    expect(screen.getByText("Рекомендация AI")).toBeInTheDocument()
    expect(screen.getAllByText(/03 Фундаменты/).length).toBeGreaterThan(0)
  })

  it("клик по кандидату зовёт onPickCandidate с кандидатом", async () => {
    const p = renderCard(r)
    await userEvent.click(screen.getByText("Фундаменты под оборудование"))
    expect(p.onPickCandidate).toHaveBeenCalledWith(CAND)
  })

  it("«Оставить без пары» зовёт onReject; легенда клавиш постоянна", async () => {
    const p = renderCard(r)
    await userEvent.click(screen.getByRole("button", { name: /без пары/i }))
    expect(p.onReject).toHaveBeenCalled()
    expect(screen.getByText(/пропустить/i)).toBeInTheDocument()
  })

  it("поиск: хиты с крошками, выбор зовёт onManualPick", async () => {
    vi.mocked(searchArticles).mockResolvedValue([
      { id: 9, article_code: "08.01", name: "Штукатурка", score: 0,
        breadcrumb: ["08 Отделочные работы"] },
    ])
    const p = renderCard(r)
    await userEvent.type(
      screen.getByPlaceholderText(/искать в справочнике/i),
      "штук"
    )
    const hit = await screen.findByText("Штукатурка")
    await userEvent.click(hit)
    expect(p.onManualPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 9, article_code: "08.01" })
    )
  })
})

describe("ReviewCard: error-строка", () => {
  const err = row(7, 3, "error", {
    matched_code: null, matched_name: null, matched_article_id: null,
    matchError: "таймаут LLM-арбитра", candidates: [],
  })

  it("показывает текст ошибки; рекомендации и кандидатов нет; поиск и без пары есть", () => {
    renderCard(err)
    expect(screen.getByText("таймаут LLM-арбитра")).toBeInTheDocument()
    expect(screen.queryByText("Рекомендация AI")).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText(/искать/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /без пары/i })).toBeInTheDocument()
  })

  it("hasRecommendation: false для error даже при matched_*", () => {
    expect(hasRecommendation(row(1, 1, "error"))).toBe(false)
    expect(hasRecommendation(row(1, 1, "needs_review"))).toBe(true)
    expect(
      hasRecommendation(
        row(1, 1, "no_match", { matched_code: null, matched_name: null })
      )
    ).toBe(false)
  })
})
```

- [ ] **Step 3: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx`
Expected: FAIL — модуля нет.

- [ ] **Step 4: Реализация**

`ReviewCard.tsx` — по Interfaces/содержимому выше. Каркас: shadcn `Card`/`CardContent` (без CardHeader-магии — крошка и работа обычными блоками), кнопки кандидатов/рекомендации — стили кнопок из бывшего `ReviewRow.tsx` (та же подсветка `border-primary shadow-[var(--ds-glow-violet)]` у выбранного, `<kbd>` бейджи). Гейт «синтетическая рекомендация отдельным блоком»:

```ts
const syntheticRecommendation =
  hasRecommendation(row) &&
  !row.candidates.some((c) => c.article_code === row.matched_code)
```

Дебаунс поиска — перенести блок `reqIdRef`/`useEffect` из `ReviewRow.tsx:60-75` дословно, заменив константу на проп `searchDebounceMs`. Command: `<Command shouldFilter={false}>` + `<CommandInput value={query} onValueChange={setQuery} placeholder="Нет верного — искать в справочнике…" />` + `<CommandList>` c хитами; `CommandEmpty` — «Ничего не найдено» только при непустом query.

Легенда — нижний ряд `<kbd>`-чипов с подписями; приглушение по `row.candidates.length === 0` / `!hasRecommendation(row)` / `!canUndo`.

- [ ] **Step 5: Зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx; npx vitest run; npm run typecheck`
Expected: PASS; старые сьюты не задеты.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(review): карточка решения — крошки обеих сторон, поиск Command, error/no_match варианты"
```

---

### Task 6: Фронт — полоса контекста `ContextStrip`

**Files:**
- Create: `frontend/src/pages/estimate/ContextStrip.tsx`
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `ReviewState`, `MatchRow`; `decisionFor`, `statusLabel` (`@/lib/reviewState`).
- Produces: `ContextStrip({ state, activeRowNumber }: { state: ReviewState; activeRowNumber: number })` — ±2 соседних узла по `sourceIndex` среди **всех** строк сметы (включая excluded — приглушённые), активная строка подсвечена. Формат строки: `код · название → статья/статус` (правая часть: у confirmed-решения — `final_code/name` из decision, иначе `statusLabel`). Видимый разделитель на границе верхнеуровневого раздела: между соседями с разным `breadcrumb[0] ?? source_name` (строка без предков — сама верхнеуровневая). Виртуализации нет — окно константного размера (спека §5).

- [ ] **Step 1: Падающие тесты**

```tsx
import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { ContextStrip } from "@/pages/estimate/ContextStrip"
import { initReview } from "@/lib/reviewState"
import type { MatchRow } from "@/lib/types"

// row(...) — хелпер как в Task 2 Step 1

const ROWS: MatchRow[] = [
  row(1, 0, "excluded", { source_name: "Орг-заголовок", breadcrumb: [] }),
  row(2, 1, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(3, 2, "needs_review", { breadcrumb: ["Орг-заголовок"] }),
  row(4, 3, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(5, 4, "confident", { source_name: "Другой раздел работа",
    breadcrumb: ["Раздел Б"] }),
  row(6, 5, "confident", { breadcrumb: ["Раздел Б"] }),
]

describe("ContextStrip", () => {
  it("окно ±2 вокруг активной по sourceIndex, включая excluded (приглушён)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    // окно: строки 1..5 (source_index 0..4); строки 6 нет
    expect(screen.getByText(/Орг-заголовок/)).toBeInTheDocument()
    expect(screen.queryByText("Строка 6")).not.toBeInTheDocument()
    const org = screen.getByText(/Орг-заголовок/).closest("[data-row]")!
    expect(org.className).toContain("opacity-60")
  })

  it("активная строка помечена", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen.getByText("Строка 3").closest("[data-row]")!
    expect(active).toHaveAttribute("data-active", "true")
  })

  it("разделитель на границе верхнеуровневого раздела", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={4} />)
    // между строкой 4 (раздел «Орг-заголовок») и строкой 5 («Раздел Б»)
    expect(screen.getByTestId("section-boundary")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Реализация**

```tsx
// Полоса контекста под карточкой (спека §3b): ±2 соседних узла по source_index
// среди ВСЕХ строк (excluded — приглушённые). Не виртуализируется — окно
// константного размера (спека §5).
import type { MatchRow, ReviewState } from "@/lib/types"
import { decisionFor, statusLabel } from "@/lib/reviewState"

const WINDOW = 2

function topSection(r: MatchRow): string {
  return r.breadcrumb[0] ?? r.source_name
}

function rightSide(state: ReviewState, r: MatchRow): string {
  // форма Decision сверена по types.ts: confirmed-вариант несёт code/name
  // (при изменении Decision сверь по lib/types.ts, не выдумывай поля)
  const d = decisionFor(state, r)
  if (d.kind === "confirmed") return `${d.code} ${d.name}`
  return statusLabel(r, d)
}

export function ContextStrip({
  state,
  activeRowNumber,
}: {
  state: ReviewState
  activeRowNumber: number
}) {
  const ordered = [...state.rows].sort((a, b) => a.sourceIndex - b.sourceIndex)
  const i = ordered.findIndex((r) => r.row_number === activeRowNumber)
  if (i === -1) return null
  const win = ordered.slice(Math.max(0, i - WINDOW), i + WINDOW + 1)
  return (
    <div className="mt-3 rounded-md border border-[var(--ds-hairline)] text-xs">
      {win.map((r, j) => {
        const boundary = j > 0 && topSection(win[j - 1]) !== topSection(r)
        const muted = r.status === "excluded" || r.status === "pending"
        return (
          <div key={r.row_number}>
            {boundary && (
              <div
                data-testid="section-boundary"
                className="border-t-2 border-[var(--ds-border-strong)]"
              />
            )}
            <div
              data-row
              data-active={r.row_number === activeRowNumber || undefined}
              className={
                "flex items-center gap-2 px-3 py-1.5 " +
                (r.row_number === activeRowNumber
                  ? "bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]"
                  : "") +
                (muted ? " opacity-60" : "")
              }
            >
              <span className="font-mono text-muted-foreground">
                {r.section_code}
              </span>
              <span className="truncate">{r.source_name}</span>
              <span className="ml-auto shrink-0 text-muted-foreground">
                → {rightSide(state, r)}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

(`data-active={... || undefined}` — чтобы атрибут отсутствовал у неактивных; сверь, что тест-ассерты выше согласованы.)

- [ ] **Step 4: Зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx; npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(review): полоса контекста ±2 по source_index с границами разделов"
```

---

### Task 7: Фронт — виртуализированный read-only грид `ReviewGrid`

**Files:**
- Modify: `frontend/package.json` (через `npm install @tanstack/react-virtual`)
- Create: `frontend/src/pages/estimate/ReviewGrid.tsx`
- Test: `frontend/src/pages/estimate/ReviewGrid.test.tsx`

**Interfaces:**
- Consumes: `useVirtualizer` (`@tanstack/react-virtual`); `filteredRows`, `decisionFor`, `statusLabel`, `requiresDecision` (`@/lib/reviewState`); `ReviewState`, `ReviewAction`.
- Produces:

```ts
interface ReviewGridProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction> // чипы-фильтры (setFilter) живут в гриде
  /** undefined ⇒ read-only (завершённая смета): клики выключены */
  onOpenRow?: (rowNumber: number) => void
  /** память позиции скролла между режимами; null — грид ещё не открывали */
  scrollOffsetRef: React.MutableRefObject<number | null>
  /** скролл к строке при входе (в очередь вошли не из грида → активная) */
  focusRowNumber?: number | null
  /** только для jsdom-тестов: размер вьюпорта виртуализатора */
  initialRect?: { width: number; height: number }
}
```

**Устройство (спека §3c):** div-разметка в визуальном языке shadcn Table (роли `table`/`row`/`columnheader`/`cell` для доступности и тестов), токены MR DS. Фиксированная высота строки — константа `const ROW_H = 64` (px; кламп текста работы `line-clamp-2`, полный текст — в карточке). Скролл-контейнер фиксированной высоты `h-[calc(100vh-220px)]` (оффсет шапки+чипов; ЗАМЕРЯЕТСЯ на реальной смете 16 в ручном гейте Task 10 — при расхождении правится токен, не архитектура). Sticky-шапка колонок (`sticky top-0 z-10 bg-[var(--ds-surface-sunken)]`) внутри скролл-контейнера. Колонки как в старой таблице: № раздела · Работа · Статья справочника · Score · Статус (правая часть строки — из `decisionFor`/`statusLabel`, как в старом `ReviewRow`, включая `Database`-иконку «Из фонда»). Чипы/фильтры/счётчики «как сейчас» — блок чипов из старого `ReviewScreen` переезжает СЮДА (фильтры действуют только в гриде — спека §3a). Кликабельность: `onOpenRow` есть И `row.status` не `excluded`/`pending` → `cursor-pointer` + клик; excluded/pending — `opacity-60`, некликабельны.

Виртуализация:

```ts
const parentRef = useRef<HTMLDivElement>(null)
const rows = filteredRows(state)
const virtualizer = useVirtualizer({
  count: rows.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => ROW_H,
  overscan: 8,
  ...(initialRect ? { initialRect } : {}),
})
```

Монтаж/память позиции:

```ts
useEffect(() => {
  if (focusRowNumber != null) {
    const idx = rows.findIndex((r) => r.row_number === focusRowNumber)
    if (idx >= 0) virtualizer.scrollToIndex(idx, { align: "center" })
  } else if (scrollOffsetRef.current != null) {
    virtualizer.scrollToOffset(scrollOffsetRef.current)
  }
  // только на монтаж — восстановление позиции
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

Запись позиции — в `onScroll` контейнера: `scrollOffsetRef.current = e.currentTarget.scrollTop`.

- [ ] **Step 1: Установить зависимость**

Run: `cd frontend; npm install @tanstack/react-virtual`
Expected: в `package.json` появился `"@tanstack/react-virtual": "^3.x"`. Это ЕДИНСТВЕННАЯ новая npm-зависимость задачи.

- [ ] **Step 2: Падающие тесты**

Создай `frontend/src/pages/estimate/ReviewGrid.test.tsx` (хелпер `row()` — как в Task 2; обёртка не нужна — грид без роутера):

```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createRef } from "react"
import { ReviewGrid } from "@/pages/estimate/ReviewGrid"
import { initReview } from "@/lib/reviewState"
import type { MatchRow } from "@/lib/types"

const RECT = { width: 1024, height: 600 }

function manyRows(n: number): MatchRow[] {
  return Array.from({ length: n }, (_, i) =>
    row(i + 1, i, i % 10 === 0 ? "needs_review" : "confident")
  )
}

function renderGrid(rows: MatchRow[], over: Record<string, unknown> = {}) {
  const scrollOffsetRef = createRef<number | null>() as
    React.MutableRefObject<number | null>
  scrollOffsetRef.current = null
  const onOpenRow = vi.fn()
  render(
    <ReviewGrid
      state={initReview("смета.xlsx", rows)}
      dispatch={vi.fn()}
      onOpenRow={onOpenRow}
      scrollOffsetRef={scrollOffsetRef}
      initialRect={RECT}
      {...over}
    />
  )
  return { onOpenRow, scrollOffsetRef }
}

describe("ReviewGrid: виртуализация", () => {
  it("рендерит окно, а не все 500 строк", () => {
    renderGrid(manyRows(500))
    const rendered = screen.getAllByRole("row") // включая шапку
    expect(rendered.length).toBeGreaterThan(5)
    expect(rendered.length).toBeLessThan(60) // 600px / 64px + overscan ≪ 500
  })
})

describe("ReviewGrid: клики", () => {
  it("клик по строке (включая confident) зовёт onOpenRow", async () => {
    const { onOpenRow } = renderGrid([
      row(1, 0, "confident"),
      row(2, 1, "needs_review"),
    ])
    await userEvent.click(screen.getByText("Строка 1"))
    expect(onOpenRow).toHaveBeenCalledWith(1)
  })

  it("excluded некликабелен; без onOpenRow (read-only) не кликабельно ничего", async () => {
    const { onOpenRow } = renderGrid([
      row(1, 0, "excluded", { source_name: "Орг" }),
      row(2, 1, "needs_review"),
    ])
    await userEvent.click(screen.getByText("Орг"))
    expect(onOpenRow).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 3: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewGrid.test.tsx`
Expected: FAIL — модуля нет.

- [ ] **Step 4: Реализация**

По Interfaces/устройству выше. Абсолютное позиционирование строк — канонический паттерн react-virtual:

```tsx
<div
  ref={parentRef}
  onScroll={(e) => {
    scrollOffsetRef.current = e.currentTarget.scrollTop
  }}
  className="relative h-[calc(100vh-220px)] overflow-auto"
  role="table"
>
  {/* sticky-шапка колонок */}
  <div role="row" className="sticky top-0 z-10 grid grid-cols-[100px_1fr_1fr_80px_160px] bg-[var(--ds-surface-sunken)] px-4 py-2.5 text-left text-xs tracking-wide text-muted-foreground uppercase">
    {/* 5 × <div role="columnheader">№ раздела / Работа из сметы / Статья
        справочника СМР / Score / Статус — заголовки старой таблицы как есть */}
  </div>
  <div style={{ height: virtualizer.getTotalSize(), position: "relative" }}>
    {virtualizer.getVirtualItems().map((vi) => {
      const r = rows[vi.index]
      const clickable =
        onOpenRow !== undefined &&
        r.status !== "excluded" &&
        r.status !== "pending"
      const muted = r.status === "excluded" || r.status === "pending"
      return (
        <div
          key={r.row_number}
          role="row"
          style={{
            position: "absolute", top: 0, left: 0, width: "100%",
            height: ROW_H, transform: `translateY(${vi.start}px)`,
          }}
          onClick={clickable ? () => onOpenRow(r.row_number) : undefined}
          className={
            "grid grid-cols-[100px_1fr_1fr_80px_160px] items-center border-b " +
            "border-[var(--ds-hairline)] px-4 text-sm" +
            (clickable ? " cursor-pointer" : "") +
            (muted ? " opacity-60" : "")
          }
        >
          {/* 5 × <div role="cell">: содержимое ячеек — как в старом ReviewRow
              (font-mono код; line-clamp-2 на работе; правая часть из
              decisionFor/statusLabel + Database-иконка «Из фонда»; Badge для
              excluded/pending; score.toFixed(2) кроме no_match/matched_fund/
              контекстных) */}
        </div>
      )
    })}
  </div>
</div>
```

Чипы-фильтры: перенеси `chip(...)`-хелпер и блок счётчиков (`counts`) из старого `ReviewScreen.tsx:46-50,127-139,205-214` в грид как есть (uverенных/проверить/без пары + фильтры `all/review/no_match` + «проверено X из Y» можно опустить — прогресс теперь в шапке экрана, Task 9).

- [ ] **Step 5: Зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewGrid.test.tsx; npm run typecheck; npx eslint src/pages/estimate/ReviewGrid.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(review): виртуализированный read-only грид на @tanstack/react-virtual"
```

---

### Task 8: Фронт — терминальный экран пустой очереди `QueueDone`

**Files:**
- Create: `frontend/src/pages/estimate/QueueDone.tsx`
- Test: `frontend/src/pages/estimate/QueueDone.test.tsx`

**Interfaces:**
- Consumes: `ReviewState`; `decisionFor`, `progress` (`@/lib/reviewState`); shadcn `Button`.
- Produces: `QueueDone({ state, onComplete, onShowGrid }: { state: ReviewState; onComplete: () => void; onShowGrid: () => void })` — экран «Все спорные строки решены» (спека §3d): сводка (решено спорных X из Y — из `progress`; сопоставлено M / без пары K — счёт по `decisionFor` всем строкам, как в `DoneScreen.tsx:31-36`), CTA «Завершить проверку» (диалог не нужен — пустая очередь ⇔ нерешённых нет), ссылка-кнопка «Посмотреть таблицу».

- [ ] **Step 1: Падающие тесты**

```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueueDone } from "@/pages/estimate/QueueDone"
import { initReview } from "@/lib/reviewState"

// row(...) — хелпер как в Task 2 Step 1; здесь все спорные уже решены сервером
const ROWS = [
  row(1, 0, "confident"),
  row(2, 1, "needs_review", {
    review_status: "confirmed", final_article_id: 7,
    final_code: "01.01", final_name: "Статья",
  }),
  row(3, 2, "no_match", {
    matched_code: null, matched_name: null, matched_article_id: null,
    review_status: "rejected",
  }),
]

describe("QueueDone", () => {
  it("сводка: заголовок, решено спорных, сопоставлено/без пары", () => {
    render(
      <QueueDone state={initReview("x", ROWS)} onComplete={vi.fn()}
        onShowGrid={vi.fn()} />
    )
    expect(screen.getByText(/все спорные строки решены/i)).toBeInTheDocument()
    expect(screen.getByText(/решено 2 из 2/i)).toBeInTheDocument()
  })

  it("CTA и ссылка на таблицу зовут колбэки", async () => {
    const onComplete = vi.fn(), onShowGrid = vi.fn()
    render(
      <QueueDone state={initReview("x", ROWS)} onComplete={onComplete}
        onShowGrid={onShowGrid} />
    )
    await userEvent.click(
      screen.getByRole("button", { name: /завершить проверку/i })
    )
    expect(onComplete).toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole("button", { name: /посмотреть таблицу/i })
    )
    expect(onShowGrid).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Убедиться, что падают → реализация → зелёные**

Run: `cd frontend; npx vitest run src/pages/estimate/QueueDone.test.tsx` (FAIL) → реализуй по Interfaces (вёрстка — по образцу центрированного `DoneScreen`: крупные цифры `font-display`, primary-кнопка CTA, `variant="outline"` для «Посмотреть таблицу») → повтори прогон + `npm run typecheck` (PASS).

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "feat(review): терминальный экран пустой очереди"
```

---

### Task 9: Фронт — `ReviewScreen` (режимы очередь/грид, шапка) + `EstimatePage` (контракт onReview, completed+grid)

Самая интеграционная задача: собирает Task 2–8 в экран, удаляет старую таблицу.

**Files:**
- Rewrite: `frontend/src/pages/estimate/ReviewScreen.tsx`
- Delete: `frontend/src/pages/estimate/ReviewRow.tsx`, `frontend/src/pages/estimate/ReviewRow.test.tsx`
- Modify: `frontend/src/pages/estimate/EstimatePage.tsx`
- Modify: `frontend/src/pages/estimate/DoneScreen.tsx` (кнопка «Просмотреть строки» → read-only грид)
- Test: `frontend/src/pages/estimate/ReviewScreen.test.tsx` (переписывается), `frontend/src/pages/estimate/EstimatePage.test.tsx` (дополнить), `frontend/src/pages/estimate/DoneScreen.test.tsx` (дополнить)

**Interfaces:**
- Consumes: `useReviewQueue` (Task 2), `useReviewKeyboard` (Task 3), `ReviewCard`/`hasRecommendation` (Task 5), `ContextStrip` (Task 6), `ReviewGrid` (Task 7), `QueueDone` (Task 8); `useSearchParams` (react-router v7); `progress` (`@/lib/reviewState`); shadcn `Tabs` (`@/components/ui/tabs`), `AlertDialog` (диалог «остались нерешённые» — переезжает из старого экрана без изменений).
- Produces:

```ts
export type ReviewActionKind = "confirm" | "pick" | "reject" // как было

interface ReviewScreenProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction>
  onExport: () => void
  onComplete: () => void
  /** Коммит на бэк; резолвится true=сохранено / false=ошибка (откат+toast сделал вызывающий) */
  onReview?: (
    rowNumber: number,
    action: ReviewActionKind,
    articleId?: number
  ) => Promise<boolean>
  /** Завершённая смета + ?view=grid: только грид, клики и решение выключены */
  readOnly?: boolean
}
```

**Устройство:**

*Режим из URL* (спека §1): `const [searchParams, setSearchParams] = useSearchParams()`; `view = readOnly || searchParams.get("view") === "grid" ? "grid" : "queue"`. Переключение — `setSearchParams`, мутируя копию: view=grid ставит параметр, очередь — удаляет (дефолт без параметра). F5/back работают через URL автоматически. **Ручной уход в грид (таб или «Посмотреть таблицу») обязан звать `queue.deselect()`** — иначе, вернувшись в очередь, оператор увидит давно открытую из грида карточку вместо потока (пин-тест «возврат в очередь табом»). Программный уход после коммита (`exit.kind === "grid"`) `deselect` не зовёт — selection уже сброшен самим `committed`.

*Шапка (оба режима)*: имя файла · «спорных решено {reviewed} из {Y}» из `progress(state)` (ЧЕСТНАЯ: excluded не считается — гасит ложь «N строк СМР») · Tabs «Очередь | Таблица» (в `readOnly` скрыт) · «Ко всем сметам» · «Выгрузить Excel» · «Завершить» (диалог при `pending > 0` — блок AlertDialog из старого экрана дословно; в `readOnly` вместо «Завершить» ничего — экспорт остаётся).

*Очередь*: `const queue = useReviewQueue(state)`; `active = queue.activeRow`. Если `active === null` → `<QueueDone state onComplete onShowGrid={() => показать грид} />`. Иначе `<ReviewCard row={active} decision={decisionFor(state, active)} canUndo={queue.canUndo} ...колбэки />` + `<ContextStrip state activeRowNumber={active.row_number} />`.

*Единая точка коммита*:

```ts
const commit = (
  row: MatchRow,
  action: ReviewAction, // dispatch-действие редьюсера
  kind: ReviewActionKind,
  articleId?: number
) => {
  dispatch(action)
  const exit = queue.committed(row.row_number)
  if (exit.kind === "grid") switchToGrid() // setSearchParams view=grid
  const p = onReview?.(row.row_number, kind, articleId)
  if (p)
    void p.then((ok) => {
      if (!ok) queue.commitFailed(row.row_number)
    })
}
```

Колбэки карточки — маппинг как в старом экране: `onConfirmRecommendation` → `confirmArbiter`+`"confirm"`; `onPickCandidate(c)` → `pickCandidate`+`"pick"`, `c.id`; `onManualPick(c)` → `manualPick`+`"pick"`, `c.id`; `onReject` → `confirmNoMatch`+`"reject"`.

*Клавиатура* (только очередь; те же маппинги, что колбэки карточки):

```ts
useReviewKeyboard({
  enabled: view === "queue" && !readOnly && active !== null,
  candidateCount: active?.candidates.length ?? 0,
  canConfirm: active ? hasRecommendation(active) : false,
  onPick: (i) => {
    const c = active?.candidates[i]
    if (active && c)
      commit(
        active,
        { type: "pickCandidate", row: active.row_number, code: c.article_code },
        "pick",
        c.id ?? undefined
      )
  },
  onConfirm: () => {
    if (active)
      commit(
        active,
        { type: "confirmArbiter", row: active.row_number },
        "confirm"
      )
  },
  onNext: () => {
    // N = пропустить; для ad-hoc строки из грида skip возвращает выход
    // по происхождению — обработать как у committed
    const exit = queue.skip()
    if (exit.kind === "grid") switchToGrid()
  },
  onReject: () => {
    if (active)
      commit(
        active,
        { type: "confirmNoMatch", row: active.row_number },
        "reject"
      )
  },
  onUndo: queue.undo,
})
```

*Грид*: `scrollOffsetRef = useRef<number | null>(null)` живёт в `ReviewScreen` (переживает переключение режимов). `<ReviewGrid state dispatch onOpenRow={readOnly ? undefined : (n) => { queue.openFromGrid(n); switchToQueue() }} scrollOffsetRef={scrollOffsetRef} focusRowNumber={scrollOffsetRef.current === null ? (queue.activeRow?.row_number ?? null) : null} />` — правило спеки §3c: «к таблице» возвращает на позицию скролла; если грид открывают впервые (в очередь вошли не из него) — скролл к активной строке.

*`EstimatePage`*: `handleReview` возвращает `Promise<boolean>`; toast ошибки — с именем строки:

```ts
function handleReview(
  rowNumber: number,
  action: ReviewActionKind,
  articleId?: number
): Promise<boolean> {
  const prev = state.rows.find((r) => r.row_number === rowNumber)
  return patchRowReview(id, rowNumber, action, articleId, prev)
    .then((updated) => {
      dispatch({ type: "syncRow", row: updated })
      return true
    })
    .catch((err: unknown) => {
      console.error(err)
      dispatch({ type: "reopen", row: rowNumber })
      // Текст нейтральный: «возвращена в начало очереди» была бы ложью для
      // confident-строки из грида (она не в очереди спорных — commitFailed
      // порядок для неё не трогает). Имя строки — требование спеки §3a.
      toast.error(
        `Не удалось сохранить решение по строке «${prev?.source_name ?? rowNumber}»`
      )
      return false
    })
}
```

Completed-ветка: `const [searchParams] = useSearchParams()`; при `meta.kind === "completed"` и `searchParams.get("view") === "grid"` → `<ReviewScreen ... readOnly onComplete={() => {}} />` (экспорт доступен, клики выключены, решение недоступно), иначе `DoneScreen` как сейчас. `processing`/`blocked`/`loading` ветки НЕ трогаются — `?view=grid` там молча игнорируется (фаза серверная и главнее режима, спека §3c).

*`DoneScreen` — вход в read-only грид из UI* (роадмап §3/§4.2d: «итоговый экран … с переходом "Просмотреть строки" → read-only грид»; без этого ветка `completed+?view=grid` достижима только ручной правкой URL): рядом с «Возобновить проверку» добавить

```tsx
<Button variant="outline" size="sm" asChild>
  <Link to="?view=grid">Просмотреть строки</Link>
</Button>
```

(`Link` уже импортирован в `DoneScreen.tsx`; relative `to="?view=grid"` сохраняет путь `/estimates/:id`.) Тест в `DoneScreen.test.tsx` — по паттернам файла: кнопка отрендерена, `href` содержит `view=grid`.

- [ ] **Step 1: Переписать `ReviewScreen.test.tsx` (падающие тесты)**

Полностью замени файл. Обёртка — `MemoryRouter` с `initialEntries` (для `?view=grid`); `WrapRows` как раньше, но с `onReview`-пропом и роутами:

```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReducer } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { initReview, reviewReducer } from "@/lib/reviewState"
import type { MatchRow } from "@/lib/types"

// ВСЕ ассерты «чья карточка открыта» — ТОЛЬКО внутри карточки: полоса
// контекста (±2 соседа) дублирует имена строк в DOM, screen.getByText по
// имени строки ловит не карточку, а полосу (ложноположительный тест)
const card = () => within(screen.getByTestId("review-card"))

vi.mock("@/lib/api/articles", () => ({
  searchArticles: vi.fn().mockResolvedValue([]),
}))

// row(...) — хелпер как в Task 2 Step 1

function Wrap({
  rows,
  url = "/estimates/5",
  onReview,
  readOnly,
}: {
  rows: MatchRow[]
  url?: string
  onReview?: (rowNumber: number, action: string, articleId?: number) => Promise<boolean>
  readOnly?: boolean
}) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("смета.xlsx", rows)
  )
  // Зеркало продового контракта EstimatePage.handleReview: при неуспехе PATCH
  // вызывающий сам диспатчит reopen (откат оптимистичного решения) и лишь
  // потом резолвится false — без этого строка осталась бы «решённой» в
  // редьюсере и тест возврата в голову очереди был бы невыполним.
  const handleReview = onReview
    ? (rowNumber: number, action: string, articleId?: number) =>
        onReview(rowNumber, action, articleId).then((ok) => {
          if (!ok) dispatch({ type: "reopen", row: rowNumber })
          return ok
        })
    : undefined
  return (
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/estimates/:id"
          element={
            <ReviewScreen
              state={state}
              dispatch={dispatch}
              onExport={vi.fn()}
              onComplete={vi.fn()}
              onReview={handleReview as never}
              readOnly={readOnly}
            />
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

const ROWS: MatchRow[] = [
  row(1, 0, "excluded", { source_name: "Орг-заголовок" }),
  row(2, 1, "confident", { source_name: "Уверенная" }),
  row(3, 2, "needs_review", { source_name: "Спорная А" }),
  row(4, 3, "needs_review", { source_name: "Спорная Б" }),
]

describe("режимы", () => {
  it("дефолт — очередь: карточка первой спорной", () => {
    render(<Wrap rows={ROWS} />)
    expect(card().getByText("Спорная А")).toBeInTheDocument()
    // это карточка, а не таблица: у грида роль table
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("?view=grid — грид", () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    expect(screen.getByRole("table")).toBeInTheDocument()
  })

  it("шапка честная: «спорных решено 0 из 2» (excluded/confident не считаются)", () => {
    render(<Wrap rows={ROWS} />)
    expect(screen.getByText(/решено 0 из 2/i)).toBeInTheDocument()
  })
})

describe("поток очереди", () => {
  it("Enter коммитит рекомендацию и двигает к следующей спорной", async () => {
    const onReview = vi.fn().mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("{Enter}")
    expect(onReview).toHaveBeenCalledWith(3, "confirm", undefined)
    await waitFor(() =>
      expect(card().getByText("Спорная Б")).toBeInTheDocument()
    )
  })

  it("0 — без пары; ← возвращает к решённой", async () => {
    const onReview = vi.fn().mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("0")
    expect(onReview).toHaveBeenCalledWith(3, "reject", undefined)
    await userEvent.keyboard("{ArrowLeft}")
    expect(card().getByText("Спорная А")).toBeInTheDocument()
  })

  it("ошибка PATCH: строка в голову очереди — СЛЕДУЮЩЕЙ, активную не выдёргивает", async () => {
    const onReview = vi
      .fn()
      .mockResolvedValueOnce(false) // первый коммит падает
      .mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("{Enter}") // Спорная А → упало (async), активной стала Б
    // даже ПОСЛЕ отработки фейла активная остаётся Б (пин; страж stale closure)
    await waitFor(() => expect(onReview).toHaveBeenCalledTimes(1))
    expect(card().getByText("Спорная Б")).toBeInTheDocument()
    await userEvent.keyboard("{Enter}") // решаем Б
    // Спорная А вернулась в голову — теперь активна она
    await waitFor(() =>
      expect(card().getByText("Спорная А")).toBeInTheDocument()
    )
  })

  it("пустая очередь — терминальный экран", () => {
    render(<Wrap rows={[row(1, 0, "confident")]} />)
    expect(screen.getByText(/все спорные строки решены/i)).toBeInTheDocument()
  })
})

describe("грид ↔ очередь", () => {
  it("клик по строке грида открывает карточку этой строки (включая confident)", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    await userEvent.click(screen.getByText("Уверенная"))
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    // карточка ИМЕННО уверенной строки (перерешение) — скоуп обязателен,
    // «Уверенная» есть и в полосе контекста
    expect(card().getByText("Уверенная")).toBeInTheDocument()
  })

  it("возврат в очередь табом после клика из грида — поток, а не старая карточка", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    await userEvent.click(screen.getByText("Уверенная")) // очередь, карточка «Уверенная»
    await userEvent.click(screen.getByRole("tab", { name: /таблица/i })) // ушли в грид табом
    await userEvent.click(screen.getByRole("tab", { name: /очередь/i })) // вернулись
    // явный выбор сброшен (deselect при уходе в грид) — активна первая спорная
    expect(card().getByText("Спорная А")).toBeInTheDocument()
  })
})

describe("read-only (завершённая смета)", () => {
  it("клики выключены, переключателя нет, экспорт есть", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" readOnly />)
    await userEvent.click(screen.getByText("Спорная А"))
    expect(screen.getByRole("table")).toBeInTheDocument() // остались в гриде
    expect(screen.queryByRole("tab", { name: /очередь/i })).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /выгрузить/i })
    ).toBeInTheDocument()
  })
})
```

Грид в jsdom: `ReviewScreen` должен пробрасывать `initialRect` в `ReviewGrid`? Нет — добавь в `ReviewGrid` дефолт `initialRect` НЕ нужен в проде; для интеграционных тестов экрана достаточно, что виртуализатор с нулевым rect отрендерит overscan-окно (первые ~8 строк) — все тестовые наборы ≤4 строк видимы. Если на практике jsdom отдаст 0 элементов — пробросить `initialRect` пропом через `ReviewScreen` (тестовый проп `gridInitialRect`), отметить в отчёте.

- [ ] **Step 2: Дополнить `EstimatePage.test.tsx` (падающие)**

По паттернам существующего файла (мокинг `@/lib/api/estimates` уже настроен там — сверь):

```tsx
it("completed + ?view=grid → read-only грид; без view — DoneScreen", async () => {
  // getEstimate → completed_at != null; рендер с initialEntries
  // ["/estimates/5?view=grid"] → findByRole("table");
  // с ["/estimates/5"] → текст DoneScreen («Скачать обогащённый») и
  // кнопка «Просмотреть строки» с href, содержащим view=grid
})

it("processing + ?view=grid молча игнорируется (ProcessingScreen)", async () => {
  // getEstimate → status pending/running → ProcessingScreen, не грид
})

it("ошибка PATCH: toast с именем строки и reopen", async () => {
  // patchRowReview.mockRejected; вызвать решение; ассерт toast.error
  // с текстом, содержащим source_name строки (мок sonner уже есть в файле? сверь;
  // нет — vi.mock("sonner", ...) по паттерну других тестов проекта)
})
```

(Разверни по фактическим хелперам файла — там уже есть мокинг `getEstimate`/`patchRowReview`; это механика.)

- [ ] **Step 3: Убедиться, что падают**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewScreen.test.tsx src/pages/estimate/EstimatePage.test.tsx`
Expected: FAIL.

- [ ] **Step 4: Реализация**

1. Перепиши `ReviewScreen.tsx` по устройству выше. Удали `ReviewRow.tsx` и `ReviewRow.test.tsx` (`git rm`). Из старого экрана переезжают: блок AlertDialog «Остались нерешённые строки» (дословно), кнопки шапки, `counts`/`chip` — в `ReviewGrid` (Task 7 уже создал грид с чипами — если чипы там уже есть, здесь просто не дублировать).
2. Обнови `EstimatePage.tsx` (handleReview → Promise<boolean> с toast-именем; completed+view=grid ветка; `useSearchParams` импорт).
3. Добавь в `DoneScreen.tsx` кнопку «Просмотреть строки» (сниппет выше) + тест.
4. `npm run typecheck` — чини по списку (например, `ReviewActionKind` экспорт остаётся в `ReviewScreen.tsx`).

- [ ] **Step 5: Всё зелёное**

Run: `cd frontend; npx vitest run; npm run typecheck; npx eslint src; npx prettier --check "src/**/*.{ts,tsx}"`
Expected: PASS полностью. Если упали чужие тесты, завязанные на старую таблицу (`ReviewScreen`-тесты уже переписаны Step 1; проверь `EstimatePage.test.tsx` и `App.test.tsx`) — обнови их ожидания под карточку/грид и явно перечисли правки в отчёте.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src
git commit -m "feat(review): экран ревью — очередь с карточкой по умолчанию, грид под ?view=grid, терминальные состояния"
```

---

### Task 10: Финализация — полный прогон, ручные гейты, devlog

**Files:**
- Create: `docs/devlog/2026-07-03-ux-stage2-pr-b-review-screen.md` (формат — по соседям)
- Modify: `docs/TECH_DEBT.md` — ТОЛЬКО если по ходу PR-B возник новый осознанный долг (кандидат: замер высоты строки грида/оффсета контейнера, если ручной гейт покажет расхождение). Пункт «Крошки статей: карта справочника грузится целиком» НЕ трогать.

**Ручные гейты выполняет КОНТРОЛЁР (сабагентам не исполнять):**

- [ ] **Step 1: Полная верификация**

Run (из корня): `just lint; just test; cd frontend; npm run typecheck; npm run build`
Expected: всё зелёное (бэк 407+ passed / 3 skipped; фронт 150−(тесты ReviewRow)+новые), prod-сборка ок. Зафиксировать фактические числа в devlog.

- [ ] **Step 2 (КОНТРОЛЁР): браузерный прогон полного потока карточки (спека §4)**

На живых dev-серверах (8260/5173), смета 16 (294 строки, 12 excluded; при необходимости «Возобновить проверку» / перерешить пару строк — данные dev, мутировать можно осознанно):

1. Открытие сметы в ревью → режим «Очередь», карточка на первой нерешённой спорной; крошки строки и статей видны, средний эллипсис на длинных цепочках.
2. Решение хоткеями: `1–3`, `Enter`, `0` — карточка двигается дальше; `N` — пропуск в хвост; `←` — возврат к предыдущему решению, перерешение работает.
3. Ошибка PATCH: остановить бэкенд НЕЛЬЗЯ (машина общая!) — эмулировать через DevTools (Network → block request на `/review`) → toast с именем строки, строка возвращается в голову очереди.
4. Переключение «Очередь ↔ Таблица»: из грида клик по строке (спорной и confident) → карточка; после решения из грида — возврат в грид на ту же позицию скролла; «к таблице» без клика — скролл к активной.
5. F5 в каждом режиме: `?view=grid` держит таблицу, без параметра — очередь; порядок очереди после F5 исходный, `←` неактивна.
6. Пустая очередь → терминальный экран; «Завершить» из обоих режимов (и диалог при остатке нерешённых из грида).
7. Завершённая смета: дефолт — итоговый экран, кнопка «Просмотреть строки» ведёт в read-only грид; там клики не открывают карточку, экспорт работает; `?view=grid` на processing-смете игнорируется.
7а. `N` на карточке, открытой кликом из грида по confident-строке, — возврат в грид, строка в очереди спорных не появляется; таб «Таблица» → таб «Очередь» после клика из грида — поток, не старая карточка.
8. Замер: фиксированная высота строки грида на реальных названиях сметы 16 (кламп 2 строки не рвётся, эллипсис честный); высота скролл-контейнера не оставляет мёртвых зон. Расхождение — правка токена `ROW_H`/оффсета, не архитектуры.
9. Excluded-строки: приглушены в гриде, некликабельны; PATCH руками (curl/DevTools) на excluded → 409.

- [ ] **Step 3: Devlog**

`docs/devlog/2026-07-03-ux-stage2-pr-b-review-screen.md`: что сделано (ссылка на спеку §3), архитектура слоёв (`useReviewQueue` поверх нетронутого `reviewState`), выбор `@tanstack/react-virtual` (обоснование из шапки плана), контракт `onReview → Promise<boolean>` и возврат в голову очереди, серверный guard excluded → 409 + `_collect_article_ids` (закрытие рекомендаций финального ревью PR-A), честная шапка, результаты ручных гейтов. Отложенное — не сюда, а в TECH_DEBT.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs: devlog PR-B этапа 2 — экран ревью (очередь/карточка/грид)"
```

---

## Самопроверка покрытия спеки (§3 + §1 + §4 + долги ревью PR-A)

| Требование спеки | Задача |
|---|---|
| §1: дефолт — «Очередь»; таблица — `?view=grid`; режим в URL, F5/back | 9 |
| §1: слоистая архитектура — `reviewState` не тронут, `useReviewQueue` — сессионный слой | 2, 9 |
| §3a: порядок = спорные по `source_index` | 2 |
| §3a: `N` — skip-в-хвост, после F5 порядок исходный | 2, 9 (гейт 5) |
| §3a: undo-стек `←` = ВСЕ коммиты сессии (включая ad-hoc из грида/после `←`); после F5 пуст | 2 |
| §3a: ошибка PATCH → голова очереди + toast с именем строки | 2, 9 |
| §3a: активную НЕ выдёргивает при асинхронном фейле (страж stale closure) | 2 (пин-тест), 9 |
| §3a: `N`/таб на ad-hoc строке из грида не загрязняет очередь спорных (guard skip, deselect) | 2, 9 |
| §3a: память «откуда пришла»: грид→грид (та же позиция), `←`→прежняя строка, поток→следующая | 2 (CommitExit), 9 |
| §3a: очередь = все спорные; фильтры/чипы — только в гриде | 2, 7, 9 |
| §3b: карточка — крошка сметы (полная, средний эллипсис, первый+последние видимы) | 4, 5 |
| §3b: работа полным текстом + код | 5 |
| §3b: рекомендация «AI»/«Из фонда» (гейт из ReviewRow) + крошка + score + Enter | 5 |
| §3b: кандидаты 1/2/3 с крошками и score | 5 |
| §3b: поиск по справочнику (серверный, shadcn Command) с крошками | 5 |
| §3b: «Оставить без пары» (`0`); легенда `1–3`/`0`/`Enter`/`N`/`←` | 3, 5 |
| §3b: error-строки — `match_error`, только поиск и «без пары», Enter/1–3 неактивны | 3 (canConfirm), 5 |
| §3b: no_match — Enter неактивен, кандидаты если есть; «клавиша ⇔ элемент» | 3, 5 |
| §3b: полоса контекста ±2 по `source_index`, excluded приглушены, границы разделов | 6 |
| §3b: клавиатура — `0`, `←`, только в «Очереди», глушение в поиске/диалоге | 3, 9 |
| §3c: `@tanstack/react-virtual`, div-язык shadcn Table, фикс. высота, кламп 2 строки | 7 |
| §3c: sticky-шапка; чипы/фильтры/счётчики как сейчас | 7 |
| §3c: клик (вкл. confident/фонд) → очередь; excluded/pending некликабельны | 7, 9 |
| §3c: «к таблице» — позиция скролла / скролл к активной | 7, 9 |
| §3c: шапка — имя файла, «спорных решено X из Y», переключатель, экспорт, «Завершить» с диалогом | 9 |
| §3c: `?view=grid` на processing/blocked игнорируется | 9 (пин-тест EstimatePage) |
| §3c: `ReviewRow`/аккордеон удалены, тесты переписаны | 9 |
| §3d: пустая очередь → терминальный экран (сводка, CTA, ссылка на таблицу) | 8, 9 |
| §3d: завершённая смета — дефолт итоговый; `?view=grid` — read-only грид, экспорт доступен | 9 |
| Роадмап §3/§4.2d: «Просмотреть строки» с итогового экрана → read-only грид (достижимость из UI) | 9 (DoneScreen) |
| §4: юниты `useReviewQueue` (порядок/skip/undo/голова/пустая) | 2 |
| §4: карточка (рекомендация/кандидаты/поиск/без пары/error/крошки) | 5 |
| §4: клавиатура (`0`, `←`, глушение) | 3 |
| §4: грид — smoke окна виртуализации; терминальный экран; read-only | 7, 8, 9 |
| §4: обязательный браузерный гейт полного потока | 10 |
| §5 (вне скоупа): повторная обработка error; ед.изм./кол-во; виртуализация полосы; память режима; светлая тема/i18n | нигде — сознательно |
| Долг ревью PR-A: серверный guard excluded → 409 | 1 |
| Долг ревью PR-A: шапка «N строк СМР» врёт | 9 |
| Долг ревью PR-A: `_collect_article_ids` | 1 |
| Долг TECH_DEBT «карта справочника целиком» | НЕ чинится (Global Constraints) |
