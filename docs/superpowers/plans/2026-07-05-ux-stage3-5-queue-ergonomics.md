# UX этап 3.5 «Эргономика карточки очереди» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пять правок экрана очереди ревью по спеке
[2026-07-05-ux-stage3-5-queue-ergonomics.md](../specs/2026-07-05-ux-stage3-5-queue-ergonomics.md):
зона решения в одну колонку, полоса контекста внутри карточки, крошка кандидата
к имени, демоушен «Завершить», новая семантика границы раздела в полосе.

**Architecture:** Только фронтенд, три файла (`ReviewScreen` / `ReviewCard` /
`ContextStrip`) + их тесты. Два PR: PR-1 (задачи 1–6) — косметика без изменения
поведения; PR-2 (задачи 7–9) — семантика границы раздела (эффективные пути,
структурный предикат «открывашки», подавление + стилизация самообъявления).
Контракт payload и бэкенд не меняются.

**Tech Stack:** React 19 + TypeScript strict, Tailwind v4 + shadcn/ui,
vitest + React Testing Library, react-router v7 (library mode).

## Global Constraints

- Ветки/PR: базовая ветка `docs/ux-stage3-5-spec` (спека+план); PR-1 из
  `feat/ux-stage3-5-card` → `docs/ux-stage3-5-spec`; PR-2 из
  `feat/ux-stage3-5-boundary`, создаётся ПОСЛЕ мержа PR-1 от обновлённой
  базовой ветки (PR-2 правит тот же `ContextStrip`).
- **PR-1 не меняет поведение** — только разметка/стили/порядок. Вся семантика
  границы — строго PR-2.
- Бэкенд не трогается. Контракт payload (`MatchRow`, `breadcrumb`) не меняется.
- Контракты excluded не трогаются нигде (спека §6): классификация, guard PATCH,
  очередь, прогресс, приглушение.
- TypeScript strict + `erasableSyntaxOnly` (без enum/parameter properties).
- Prettier `printWidth 80`, `endOfLine lf`; eslint строгий. Перед каждым PR —
  `just lint` из корня.
- shadcn-компоненты `frontend/src/components/ui/*` — вендорные, не править.
- Терминал — PowerShell 5.1: `;` вместо `&&`. Тесты:
  `cd frontend; npx vitest run <путь>`; typecheck: `cd frontend; npm run typecheck`
  (это `tsc -b`; `tsc --noEmit` без `-b` ничего не проверяет).
- Комментарии в коде — по-русски, плотность как в соседних файлах.
- Каждый коммит завершается трейлером:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

## PR-1 — косметика (поведение не меняется)

### Task 1: Слот `contextStrip` в ReviewCard

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewCard.tsx` (пропсы ~строки 20–29, разметка после блока работы ~строка 113)
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx` (~строки 283–330)
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (корневой класс, строка 35)
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

**Interfaces:**
- Produces: `ReviewCardProps.contextStrip?: ReactNode` — рендерится между
  блоком работы и рекомендацией/кандидатами. Task 2 оборачивает результат,
  Task 9 (гейт) проверяет порядок глазом.

- [ ] **Step 1: Write the failing test**

В `ReviewCard.test.tsx` добавить (использовать существующий в файле хелпер
пропсов, если он есть; иначе — самодостаточная фикстура ниже):

```tsx
import { initReview, decisionFor } from "@/lib/reviewState"
import type { MatchRow } from "@/lib/types"

const SLOT_ROW: MatchRow = {
  row_number: 1,
  section_code: "10.2.3.9.5",
  source_name: "Пусконаладочные работы",
  sourceIndex: 0,
  breadcrumb: ["Инженерные системы"],
  matchError: null,
  status: "needs_review",
  score: 0.89,
  matched_code: null,
  matched_name: null,
  matched_article_id: null,
  matchedBreadcrumb: [],
  candidates: [
    {
      id: 5,
      article_code: "10.8.5",
      name: "Пусконаладочные работы ИТП",
      score: 0.89,
      breadcrumb: ["ВИС", "Индивидуальный тепловой пункт"],
    },
  ],
  review_status: "unreviewed",
  final_article_id: null,
  finalBreadcrumb: [],
  final_code: null,
  final_name: null,
}

function renderSlotCard(contextStrip?: React.ReactNode) {
  const state = initReview("f", [SLOT_ROW])
  return render(
    <ReviewCard
      row={SLOT_ROW}
      decision={decisionFor(state, SLOT_ROW)}
      canUndo={false}
      onConfirmRecommendation={() => {}}
      onPickCandidate={() => {}}
      onManualPick={() => {}}
      onReject={() => {}}
      searchDebounceMs={0}
      contextStrip={contextStrip}
    />
  )
}

it("слот contextStrip рендерится между строкой работы и кандидатами", () => {
  renderSlotCard(<div data-testid="strip-slot" />)
  const slot = screen.getByTestId("strip-slot")
  const work = screen.getByText("Пусконаладочные работы")
  const candidate = screen.getByText("Пусконаладочные работы ИТП")
  // работа ПЕРЕД слотом, слот ПЕРЕД кандидатом (DOM-порядок)
  expect(
    work.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy()
  expect(
    slot.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING
  ).toBeTruthy()
})

it("без пропа contextStrip карточка рендерится как раньше", () => {
  renderSlotCard(undefined)
  expect(screen.getByTestId("review-card")).toBeInTheDocument()
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx`
Expected: FAIL — TS-ошибка «contextStrip does not exist» / слот не найден.

- [ ] **Step 3: Write minimal implementation**

`ReviewCard.tsx`:

```tsx
import { type ReactNode, useEffect, useRef, useState } from "react"
```

В `ReviewCardProps`:

```tsx
  contextStrip?: ReactNode // полоса окружения (спека 3.5 §3 п.2): карточка не знает о ревью-стейте
```

В деструктуризации пропсов добавить `contextStrip,`. В разметке — сразу после
блока работы (`<div className="text-sm">…</div>`, до ветки `row.status === "error"`):

```tsx
        {/* 2b. Окружение (спека 3.5): крошка → строка → окружение → кандидаты */}
        {contextStrip}
```

`ReviewScreen.tsx` — убрать `<ContextStrip …/>` соседом (и фрагмент `<>…</>`),
передать пропом:

```tsx
        <ReviewCard
          key={active.row_number}
          row={active}
          decision={decisionFor(state, active)}
          canUndo={queue.canUndo}
          contextStrip={
            <ContextStrip state={state} activeRowNumber={active.row_number} />
          }
          onConfirmRecommendation={() =>
```

(остальные пропсы без изменений; закрывающий `/>` вместо `/>\n<ContextStrip …/>`).

`ContextStrip.tsx` — корневой класс: `mt-3` убрать (вертикальный ритм внутри
карточки задаёт `gap-3` у `CardContent`):

```tsx
    <div className={cn("rounded-md border text-xs", dsHairline)}>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx src/pages/estimate/ReviewScreen.test.tsx src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS. Если тесты `ReviewScreen.test.tsx` искали полосу рядом с
карточкой позиционно — актуализировать (полоса теперь внутри карточки; сами
`getByText`-запросы работают, ломаются только structural-селекторы).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ReviewCard.tsx frontend/src/pages/estimate/ReviewScreen.tsx frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ReviewCard.test.tsx
git commit -m "feat(ux3.5): полоса контекста слотом внутрь ReviewCard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 2: Контейнер зоны решения (max-width)

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx` (ветка `view === "queue"` с активной строкой)
- Test: `frontend/src/pages/estimate/ReviewScreen.test.tsx`

**Interfaces:**
- Produces: обёртка `data-testid="decision-zone"` вокруг карточки. Стартовое
  значение `max-w-[68rem]` (~1088px, ориентир спеки ~1100px) — уточняется на
  живом гейте (Task 6).

- [ ] **Step 1: Write the failing test**

В `ReviewScreen.test.tsx` (использовать существующие хелперы файла — `row(...)`
там уже есть):

```tsx
it("зона решения ограничена по ширине и центрирована", () => {
  renderScreen() // существующий рендер экрана очереди с активной строкой
  const zone = screen.getByTestId("decision-zone")
  expect(zone.className).toContain("max-w-")
  expect(zone.className).toContain("mx-auto")
  expect(zone).toContainElement(screen.getByTestId("review-card"))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewScreen.test.tsx`
Expected: FAIL — `decision-zone` не найден.

- [ ] **Step 3: Write minimal implementation**

Обернуть `<ReviewCard …/>` (ветка `active !== null`):

```tsx
        <div
          data-testid="decision-zone"
          className="mx-auto w-full max-w-[68rem] px-4 py-4"
        >
          <ReviewCard
            …
          />
        </div>
```

Тулбар, грид и `QueueDone` не оборачиваются (спека §3 п.1).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewScreen.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ReviewScreen.tsx frontend/src/pages/estimate/ReviewScreen.test.tsx
git commit -m "feat(ux3.5): зона решения — центрированная колонка max-w

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 3: Строка кандидата — «имя · крошка», score справа

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewCard.tsx` (кандидаты ~строки 174–217, синтетическая рекомендация ~строки 125–162)
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

**Interfaces:**
- Consumes: `CrumbTrail` (`@/components/estimate/CrumbTrail`) — уже принимает
  `className`, уже несёт `title` с полной цепочкой и средний эллипсис >3 уровней.

- [ ] **Step 1: Write the failing test**

```tsx
it("крошка кандидата примыкает к имени, score — у правого края", () => {
  renderSlotCard()
  const name = screen.getByText("Пусконаладочные работы ИТП")
  const crumb = screen.getByTitle("ВИС › Индивидуальный тепловой пункт")
  // имя и крошка — в одном flex-контейнере
  expect(name.parentElement).toBe(crumb.parentElement)
  // score — последний элемент строки кандидата
  const button = name.closest("button")!
  expect(button.lastElementChild?.textContent).toBe("0.89")
})
```

Литерал `title` сверен с реализацией (`CrumbTrail.tsx`: `SEP = " › "`,
`title={levels.join(SEP)}`) — при расхождении брать литерал из кода
`CrumbTrail`, не из этого плана.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx`
Expected: FAIL — `parentElement` разные (крошка сейчас сестра имени на правом краю).

- [ ] **Step 3: Write minimal implementation**

Кандидат — заменить три span (имя/крошка/score):

```tsx
                  <span className="flex min-w-0 flex-1 items-baseline gap-2">
                    <span>{c.name}</span>
                    <CrumbTrail levels={c.breadcrumb} className="truncate" />
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {c.score.toFixed(2)}
                  </span>
```

(`min-w-0` на обёртке — иначе `truncate` не сработает во flex; ширинное
усечение — только по крошке, имя не жертвуется, полная цепочка в `title`
бесплатно из `CrumbTrail` — спека §3 п.3.)

Синтетическая рекомендация — тем же шаблоном (появляется имя статьи):

```tsx
                <span className="flex min-w-0 flex-1 items-baseline gap-2">
                  <span>{row.matched_name}</span>
                  <CrumbTrail levels={row.matchedBreadcrumb} className="truncate" />
                </span>
```

(`matched_name` не-null по гейту `hasRecommendation`; блок score/бейджа после
обёртки не меняется.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewCard.test.tsx`
Expected: PASS (и существующие тесты карточки зелёные — при позиционных
селекторах по крошке актуализировать).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ReviewCard.tsx frontend/src/pages/estimate/ReviewCard.test.tsx
git commit -m "feat(ux3.5): крошка кандидата к имени, score один у правого края

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 4: Демоушен «Завершить»

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx` (~строки 218–231)
- Test: `frontend/src/pages/estimate/ReviewScreen.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
it("«Завершить» приглушена при нерешённых, primary при pending === 0", () => {
  // экран с 1 нерешённой спорной строкой (существующие фикстуры файла)
  renderScreen()
  const btn = screen.getByRole("button", { name: /Завершить/ })
  expect(btn.className).not.toContain("bg-primary")
})

it("«Завершить» primary, когда спорных не осталось", () => {
  // фикстура: все строки confident/решённые → pending === 0
  renderScreenAllResolved()
  const btn = screen.getByRole("button", { name: /Завершить/ })
  expect(btn.className).toContain("bg-primary")
})
```

(имена рендер-хелперов — по факту файла; смысловая пара: pending>0 / pending===0.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewScreen.test.tsx`
Expected: первый тест FAIL — кнопка сейчас всегда primary.

- [ ] **Step 3: Write minimal implementation**

Ветка `pending === 0` не меняется (primary). В ветке с `AlertDialog`
(`pending > 0`) — триггер-кнопка:

```tsx
                <AlertDialogTrigger asChild>
                  {/* Демоушен (спека 3.5 §2): primary «загорается» при pending === 0 —
                      кнопка не приглашает, пока по нажатию ругается диалогом */}
                  <Button size="sm" variant="outline">
                    <Check className="size-4" />
                    Завершить
                  </Button>
                </AlertDialogTrigger>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ReviewScreen.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ReviewScreen.tsx frontend/src/pages/estimate/ReviewScreen.test.tsx
git commit -m "feat(ux3.5): демоушен «Завершить» до решения всех спорных

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 5: Маркер «вы здесь» у активной строки полосы

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (правая часть строки, ~строки 62–64)
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: атрибут `data-row` на строке полосы — сверено, УЖЕ присутствует
  (`ContextStrip.tsx:48`; существующие тесты им пользуются,
  `ContextStrip.test.tsx:55,61`). Добавлять не нужно.

- [ ] **Step 1: Write the failing test**

```tsx
import { within } from "@testing-library/react"

it("активная строка — маркер «вы здесь», не статус", () => {
  render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
  const active = screen.getByText("Строка 3").closest("[data-row]")!
  expect(within(active).getByLabelText("вы здесь")).toBeInTheDocument()
  expect(active.textContent).not.toContain("→")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — маркера нет, активная строка показывает `→ статус`.

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx`:

```tsx
import { ArrowLeft } from "lucide-react"
```

Правая часть строки:

```tsx
              {r.row_number === activeRowNumber ? (
                // статус активной дублировал бы решаемое прямо сейчас (спека 3.5 §2)
                <ArrowLeft
                  aria-label="вы здесь"
                  className="ml-auto size-3 shrink-0 text-primary"
                />
              ) : (
                <span className="ml-auto shrink-0 text-muted-foreground">
                  → {rightSide(state, r)}
                </span>
              )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.5): маркер активной строки полосы вместо дубля статуса

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 6: Верификация PR-1 — полный прогон, живой гейт, PR

- [ ] **Step 1: Полный прогон**

Run: `cd frontend; npm run typecheck; npx vitest run` затем из корня `just lint`
Expected: всё зелёное.

- [ ] **Step 2: Живой гейт (браузер, dev-серверы `just dev-back` / `just dev-front`)**

- очередь на широком мониторе: одна зрительная колонка, тулбар полноширинный;
  при необходимости скорректировать `max-w-[68rem]` (спека: ориентир ~1100px);
- ~1280px: карточка не ломается; шаблон «имя · крошка» на кандидатах с
  длинными крошками ВИС — крошка усекается эллипсисом, имя целиком, `title`
  показывает полный путь;
- порядок в карточке: крошка → работа → полоса → кандидаты → поиск → «без пары»;
- демоушен: «Завершить» outline на смете с нерешёнными; primary после решения
  всех (или на завершённой смете).

- [ ] **Step 3: Devlog + PR**

Посмотреть `ls docs/devlog` и создать запись по образцу соседних (что сделано,
ссылка на спеку; отложенное — только указателем в TECH_DEBT, если появилось).
PR: `feat/ux-stage3-5-card` → `docs/ux-stage3-5-spec` через
`superpowers:finishing-a-development-branch`.

---

## PR-2 — семантика границы раздела (после мержа PR-1)

### Task 7: Эффективные пути, предикат открывашки, подпись, подавление

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (замена `topSection`-логики)
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Produces: `data-opener` на строке-открывашке (потребляет Task 8 для стилизации
  и тестов), разметка разделителя `data-testid="section-boundary"` с текстом
  `Раздел — {имя}`.

- [ ] **Step 1: Write the failing tests**

В `ContextStrip.test.tsx` — новые фикстуры и кейсы (хелпер `row()` уже в файле):

```tsx
// Одноимённые листовые разделы под разными родителями — кейс, ради которого
// сравнивается ПОЛНЫЙ путь (спека §2: имена листовых уровней не уникальны).
const SAME_LEAF_ROWS: MatchRow[] = [
  row(1, 0, "needs_review", {
    source_name: "Работа 1",
    breadcrumb: ["Топ", "Подраздел А", "Материалы"],
  }),
  row(2, 1, "needs_review", {
    source_name: "Работа 2",
    breadcrumb: ["Топ", "Подраздел Б", "Материалы"],
  }),
]

// Два подраздела под одним верхнеуровневым — кейс, на котором breadcrumb[0] молчал.
const SIBLING_ROWS: MatchRow[] = [
  row(1, 0, "needs_review", {
    source_name: "Работа А1",
    breadcrumb: ["Топ", "Подраздел А"],
  }),
  row(2, 1, "needs_review", {
    source_name: "Работа Б1",
    breadcrumb: ["Топ", "Подраздел Б"],
  }),
]

// Заголовок (открывашка) между разделами: next.breadcrumb ===
// header.breadcrumb + [header.source_name] → разделитель подавлен.
function headerRows(headerStatus: MatchStatus): MatchRow[] {
  return [
    row(1, 0, "needs_review", {
      source_name: "Работа А1",
      breadcrumb: ["Топ", "Подраздел А"],
    }),
    row(2, 1, headerStatus, {
      source_name: "Подраздел Б",
      breadcrumb: ["Топ"],
    }),
    row(3, 2, "needs_review", {
      source_name: "Работа Б1",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
  ]
}

it("одноимённые листовые разделы под разными родителями разделяются", () => {
  render(
    <ContextStrip state={initReview("x", SAME_LEAF_ROWS)} activeRowNumber={1} />
  )
  const b = screen.getByTestId("section-boundary")
  expect(b.textContent).toContain("Раздел — Материалы")
})

it("два подраздела под одним верхнеуровневым разделяются с подписью", () => {
  render(
    <ContextStrip state={initReview("x", SIBLING_ROWS)} activeRowNumber={1} />
  )
  expect(screen.getByTestId("section-boundary").textContent).toContain(
    "Раздел — Подраздел Б"
  )
})

it("строки одного раздела границы не имеют", () => {
  const rows = [
    row(1, 0, "needs_review", { breadcrumb: ["Топ", "А"] }),
    row(2, 1, "needs_review", { breadcrumb: ["Топ", "А"] }),
  ]
  render(<ContextStrip state={initReview("x", rows)} activeRowNumber={1} />)
  expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
})

it.each(["excluded", "needs_review"] as const)(
  "разделитель перед открывашкой подавлен (самообъявление), статус=%s",
  (st) => {
    render(
      <ContextStrip state={initReview("x", headerRows(st))} activeRowNumber={1} />
    )
    // граница А↔заголовок подавлена; заголовок↔Б1 — пути равны, границы нет
    expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
  }
)

it("открывашка склеена с детьми, вложенные сходятся", () => {
  const rows = [
    row(1, 0, "excluded", { source_name: "Подраздел Б", breadcrumb: ["Топ"] }),
    row(2, 1, "needs_review", {
      source_name: "Работа Б1",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
    row(3, 2, "needs_review", {
      source_name: "Работа Б2",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
  ]
  render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
  expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
  // край §4: последняя строка списка — не открывашка (next отсутствует)
  expect(
    screen.getByText("Работа Б2").closest("[data-row]")
  ).not.toHaveAttribute("data-opener")
})

it("две границы в одном окне ±2", () => {
  const rows = [
    row(1, 0, "needs_review", { breadcrumb: ["Топ", "А"] }),
    row(2, 1, "needs_review", { breadcrumb: ["Топ", "Б"] }),
    row(3, 2, "needs_review", { breadcrumb: ["Топ", "В"] }),
  ]
  render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
  expect(screen.getAllByTestId("section-boundary")).toHaveLength(2)
})

it("страж: семантика границы не зависит от MatchStatus", () => {
  // одна геометрия, два разных статуса заголовка → одинаковый результат
  const a = render(
    <ContextStrip
      state={initReview("x", headerRows("excluded"))}
      activeRowNumber={3}
    />
  )
  const countExcluded =
    a.container.querySelectorAll('[data-testid="section-boundary"]').length
  a.unmount()
  const b = render(
    <ContextStrip
      state={initReview("x", headerRows("confident"))}
      activeRowNumber={3}
    />
  )
  const countWork =
    b.container.querySelectorAll('[data-testid="section-boundary"]').length
  expect(countWork).toBe(countExcluded)
})
```

Существующий тест «разделитель на границе верхнеуровневого раздела» остаётся
зелёным (граница по полному пути там тоже есть); если он завязан на отсутствие
текста в разделителе — актуализировать на `Раздел — Раздел Б`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — сейчас граница по `breadcrumb[0]`: одноимённые/сиблинги не
разделяются, подпись отсутствует, подавления нет.

- [ ] **Step 3: Write implementation**

`ContextStrip.tsx` — заменить `topSection` и вычисление `boundary` (маркер
активной строки из PR-1 не трогается):

```tsx
// Открывашка — структурный предикат по крошке СЛЕДУЮЩЕЙ строки, НЕ по статусу
// (excluded — не детектор заголовка: WORK-заголовки матчатся; спека 3.5 §2).
// Равенства достаточно, prefix-сравнение не нужно: nearest-persisted-резолв
// не порождает непersистированных уровней в крошке — у первого
// персистированного потомка X путь равен X.breadcrumb + [X.name] ТОЧНО.
function isOpener(r: MatchRow, next: MatchRow | undefined): boolean {
  if (!next) return false
  if (next.breadcrumb.length !== r.breadcrumb.length + 1) return false
  return (
    next.breadcrumb[r.breadcrumb.length] === r.source_name &&
    r.breadcrumb.every((name, k) => name === next.breadcrumb[k])
  )
}

function pathsEqual(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((x, k) => x === b[k])
}
```

В компоненте после `ordered`/`i`:

```tsx
  const openers = ordered.map((r, g) => isOpener(r, ordered[g + 1]))
  // Эффективный путь (спека §4 п.1): открывашка живёт в разделе, который открывает.
  const paths = ordered.map((r, g) =>
    openers[g] ? [...r.breadcrumb, r.source_name] : r.breadcrumb
  )
  const start = Math.max(0, i - WINDOW)
  const win = ordered.slice(start, i + WINDOW + 1)
```

В `win.map((r, j) => …)` — глобальный индекс и правила §4:

```tsx
        const g = start + j
        const boundary = j > 0 && !pathsEqual(paths[g - 1], paths[g])
        // §4 п.3: перед открывашкой разделитель подавлен — заголовок объявляет
        // себя сам (стилизация — Task 8, вторая половина правила).
        const divider = boundary && !openers[g]
        // Имя ближайшего родителя нового пути; пустой путь (граница к корню,
        // «путь укоротился») — разделитель без подписи.
        const label = paths[g][paths[g].length - 1]
```

Разметка разделителя (вместо голого `border-t-2`-div):

```tsx
            {divider && (
              <div
                data-testid="section-boundary"
                className="border-t-2 border-[var(--ds-border-strong)]"
              >
                {label && (
                  <div className="px-3 pt-1 text-[11px] tracking-wide text-muted-foreground uppercase">
                    Раздел — {label}
                  </div>
                )}
              </div>
            )}
```

На строку добавить `data-opener={openers[g] || undefined}` (стилизация — Task 8).
Функция `topSection` удаляется целиком.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS, включая три старых теста.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.5): граница разделов полосы — эффективные пути и подпись

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 8: Стилизация открывашки + парный тест самообъявления

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (класс строки)
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `openers[g]` / `data-opener` из Task 7; атрибут `data-row` —
  сверено, уже в коде (`ContextStrip.tsx:48`).

- [ ] **Step 1: Write the failing tests**

```tsx
it("парный тест самообъявления: разделитель подавлен ∧ открывашка стилизована", () => {
  render(
    <ContextStrip
      state={initReview("x", headerRows("excluded"))}
      activeRowNumber={1}
    />
  )
  expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
  const header = screen.getByText("Подраздел Б").closest("[data-row]")!
  expect(header.className).toContain("font-medium")
  // приглушение excluded сохраняется — оси разные (спека §2)
  expect(header.className).toContain("opacity-60")
})

it("открывашка на краю окна (разделитель отрезан слайсом) всё равно стилизована", () => {
  const rows = [
    row(1, 0, "needs_review", {
      source_name: "Работа А1",
      breadcrumb: ["Топ", "Подраздел А"],
    }),
    row(2, 1, "excluded", { source_name: "Подраздел Б", breadcrumb: ["Топ"] }),
    row(3, 2, "needs_review", {
      source_name: "Работа Б1",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
    row(4, 3, "needs_review", {
      source_name: "Работа Б2",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
    row(5, 4, "needs_review", {
      source_name: "Работа Б3",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
  ]
  // активная 4 → окно [2..5]: заголовок — первая строка окна, j === 0
  render(<ContextStrip state={initReview("x", rows)} activeRowNumber={4} />)
  const header = screen.getByText("Подраздел Б").closest("[data-row]")!
  expect(header.className).toContain("font-medium")
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — `font-medium` нет.

- [ ] **Step 3: Write minimal implementation**

Класс строки — добавить условие (стилизация по предикату, безусловно к
положению в окне — спека §4 п.3):

```tsx
              className={cn(
                "flex items-center gap-2 px-3 py-1.5",
                r.row_number === activeRowNumber &&
                  "bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]",
                muted && "opacity-60",
                openers[g] && "font-medium"
              )}
```

(если строка ещё на строковой конкатенации — перевести на `cn`, поведение то же.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.5): открывашка в полосе стилизована как заголовок

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

### Task 9: Верификация PR-2 — полный прогон, живой гейт на смете 16, PR

- [ ] **Step 1: Полный прогон**

Run: `cd frontend; npm run typecheck; npx vitest run` затем из корня `just lint`
Expected: всё зелёное.

- [ ] **Step 2: Живой гейт на смете 16 (спека §5)**

- место с **некодированным заголовком** между разделами: разделитель с подписью
  «Раздел — …» — единственный класс данных, где правило работает в одиночку;
- место с **WORK-заголовком**: подавление + заголовочный стиль, а не дубль подписи;
- «путь укоротился» (граница вверх по дереву, если найдётся): подпись именем
  родительского раздела — взглянуть глазом (известный край, спека §4);
- прокликать очередь: две границы в окне, приглушённые excluded-открывашки
  читаются как заголовки.

- [ ] **Step 3: Devlog + PR**

Devlog-запись по образцу соседних в `docs/devlog/`. PR:
`feat/ux-stage3-5-boundary` → `docs/ux-stage3-5-spec` через
`superpowers:finishing-a-development-branch`. После мержа PR-2 — финальный PR
`docs/ux-stage3-5-spec` → `main` (как этапы 2–3; CodeRabbit сработает на
base=main — проверить все три источника ревью).

---

## Self-Review Checklist (покрытие спеки)

- **§3 п.1–5 → Tasks 1–5:** max-w → Task 2; слот → Task 1; кандидат +
  ширинное усечение → Task 3; демоушен → Task 4; маркер → Task 5.
- **§4 → Tasks 7–8:** правила 1–4 → Task 7; стилизация открывашки → Task 8.
  Краевые случаи: последняя строка не открывашка (Task 7, ассерт
  `data-opener`); склейка/вложенность (Task 7); две границы в окне (Task 7);
  страж независимости от статуса (Task 7); открывашка на краю окна (Task 8);
  пустой label — «путь укоротился» (реализация Task 7, глазом на гейте Task 9);
  «заголовок без персистированных потомков» — известный край, не чинится (§4).
- **§5 → тесты в Tasks 1–5, 7, 8; живые гейты → Task 6** (широкий монитор +
  ~1280px, демоушен, усечение крошки) **и Task 9** (смета 16: некодированный
  заголовок, WORK-заголовок, «путь укоротился»).
- **§6 вне скоупа — соблюдено:** бэк, контракт payload, контракты excluded,
  окно ±2 и виртуализация не трогаются ни одной задачей.
