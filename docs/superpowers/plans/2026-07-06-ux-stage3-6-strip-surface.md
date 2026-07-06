# UX этап 3.6 «Полоса окружения как справочная поверхность» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Различить роли поверхностей в карточке ревью по спеке
[2026-07-06-ux-stage3-6-strip-surface.md](../specs/2026-07-06-ux-stage3-6-strip-surface.md):
полоса окружения становится утопленной справочной панелью (заливка + подпись +
воздух), присвоенный сосед показывает код статьи вместо полного имени (имя — в
`title`), активная строка получает кромку-резерв без «дёрга» контента.

**Architecture:** Только фронтенд, один компонент (`ContextStrip.tsx`) + его тест
(`ContextStrip.test.tsx`). Один PR — косметика + одно информационное изменение
(имя присвоенной статьи → `title`). Семантика границы раздела (эффективные пути,
предикат открывашки, подавление самообъявления, стилизация открывашки, страж
независимости от `MatchStatus`) из этапа 3.5 §4 — НЕ трогается. Контракт payload
и бэкенд не меняются.

**Tech Stack:** React 19 + TypeScript strict, Tailwind v4 + shadcn/ui,
vitest + React Testing Library.

## Global Constraints

- Ветка: `feat/ux-stage3-6-strip-surface` от `main`; один PR → `main`.
  Спека+план коммитятся первыми на этой ветке, затем задачи реализации.
- **Один компонент.** Все правки — в `ContextStrip.tsx` (+ тест). `ReviewCard`
  НЕ трогается (воздух живёт на корне полосы — Task 1; если ревьюер предпочтёт
  слот, это однострочный перенос `mb-*` на `{contextStrip}` в
  [ReviewCard.tsx:118](../../../frontend/src/pages/estimate/ReviewCard.tsx#L118),
  но дефолт — корень полосы, чтобы удержать одно-файловый скоуп).
- **Семантика границы раздела не меняется** (спека 3.6 §2, §5): `isOpener`,
  `pathsEqual`, эффективные пути, `divider`/подавление, `data-opener`,
  `font-medium` открывашки, приглушение `opacity-60` excluded/pending — байт-в-байт.
  Единственное изменение внутри строки — правая часть присвоенного соседа (Task 2).
- Бэкенд не трогается. Контракт payload (`MatchRow`, `breadcrumb`, `Decision`)
  не меняется. Контракты excluded (классификация, guard PATCH, очередь, прогресс,
  приглушение) — не трогаются нигде.
- Новый цвет не заводится: заливка — существующий токен `--ds-surface-sunken`
  ([index.css:69](../../../frontend/src/index.css#L69)), через CSS-var инлайн
  (не литерал-класс; см. Task 1). Дедуп токена в именованную `ds-table`-константу —
  вне скоупа (спека §5).
- TypeScript strict + `erasableSyntaxOnly` (без enum/parameter properties).
- Prettier `printWidth 80`, `endOfLine lf`; eslint строгий. Перед PR — `just lint`
  из корня.
- shadcn-компоненты `frontend/src/components/ui/*` — вендорные, не править.
- Терминал — PowerShell 5.1: `;` вместо `&&`. Тесты:
  `cd frontend; npx vitest run <путь>`; typecheck: `cd frontend; npm run typecheck`
  (это `tsc -b`; `tsc --noEmit` без `-b` ничего не проверит).
- Комментарии в коде — по-русски, плотность как в соседних строках `ContextStrip`.
- Каждый коммит завершается трейлером `Co-Authored-By: <модель-исполнителя> <noreply@anthropic.com>`
  (в этапе 3.5 исполнителем был Claude Fable 5 — подставить актуальную модель).

---

### Task 1: Утопленная поверхность — заливка, подпись, воздух, гвард роли

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (корневой контейнер, [строки 55-56](../../../frontend/src/pages/estimate/ContextStrip.tsx#L55-L56))
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Produces: корневой `<div>` полосы несёт заливку `bg-[var(--ds-surface-sunken)]`
  и нижний отступ `mb-*`; первым дочерним элементом — подпись «Окружение в смете».
  Строки полосы остаются без словаря кандидата (`rounded-md`/`border-border`) —
  Task 3 добавит только `border-l`-кромку, гвард это учитывает.

- [ ] **Step 1: Write the failing tests**

В `ContextStrip.test.tsx` добавить (хелпер `row(...)` и фикстура `ROWS` уже в файле):

```tsx
it("подпись панели «Окружение в смете» рендерится", () => {
  render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
  expect(screen.getByText(/Окружение в смете/i)).toBeInTheDocument()
})

it("контейнер полосы залит sunken-токеном и отбит воздухом снизу", () => {
  const { container } = render(
    <ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />
  )
  const root = container.firstElementChild!
  // утопленная поверхность (справка ≠ обведённые кнопки кандидатов)
  expect(root.className).toContain("bg-[var(--ds-surface-sunken)]")
  // воздух полоса↔кандидаты больше внутристрочного шага (спека §3 п.4)
  expect(root.className).toContain("mb-")
})

it("строки полосы не несут словаря кандидата (регресс-гвард роли)", () => {
  render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
  // неактивная строка: нет фрейма кандидата (rounded-md + border-border);
  // гвард проверяет словарь, а не подстроку «border» — Task 3 навесит
  // border-l-2 border-transparent, что этот гвард переживёт.
  const other = screen.getByText("Строка 2").closest("[data-row]")!
  expect(other.className).not.toContain("rounded")
  expect(other.className).not.toContain("border-border")
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — подпись не найдена; корневой класс не содержит `bg-[var(--ds-surface-sunken)]`/`mb-`. (Гвард роли пройдёт сразу — строки и сейчас без рамок; это регресс-замок.)

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx` — корневой контейнер (сейчас `<div className={cn("rounded-md border text-xs", dsHairline)}>`) + подпись первым дочерним элементом:

```tsx
  return (
    <div
      className={cn(
        "mb-4 rounded-md border bg-[var(--ds-surface-sunken)] text-xs",
        dsHairline
      )}
    >
      {/* Подпись справочной панели (спека 3.6 §2 п.2): тот же типографический
          словарь, что подпись разделителя «Раздел — …» ниже. */}
      <div className="px-3 pt-2 pb-1 text-[11px] tracking-wide text-muted-foreground uppercase">
        Окружение в смете
      </div>
      {win.map((r, j) => {
```

(закрывающие `)` / `</div>` структуры `win.map` не меняются — подпись добавляется
ДО `win.map`, внутри того же корневого `<div>`.)

Стартовое значение отступа — `mb-4` (16px поверх флекс-`gap-3` карточки → ~28px
под полосой против ~12px над; уточняется на живом гейте Task 4 так, чтобы разрыв
полоса↔кандидаты был заметно больше внутристрочного шага строк `py-1.5`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS (включая все существующие тесты полосы — заливка/подпись/отступ
не трогают DOM-порядок строк и разделителей).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.6): полоса окружения — утопленная справочная панель

Co-Authored-By: <модель-исполнителя> <noreply@anthropic.com>"
```

### Task 2: Правая часть присвоенного соседа — код статьи + title

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (`rightSide`, [строки 30-36](../../../frontend/src/pages/estimate/ContextStrip.tsx#L30-L36); использование, [строки 103-107](../../../frontend/src/pages/estimate/ContextStrip.tsx#L103-L107))
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `decisionFor` / `statusLabel` из `@/lib/reviewState` (уже
  импортированы); форма `Decision.confirmed` несёт `code`/`name` — сверено по
  [types.ts](../../../frontend/src/lib/types.ts).
- Produces: `rightSide(state, r)` возвращает `{ text: string; title?: string; mono?: boolean }`
  вместо `string` — confirmed-ветвь даёт код + `title`+`mono`, остальные — статусную
  подпись без `title`/`mono`.

- [ ] **Step 1: Write the failing test**

```tsx
// Присвоенный сосед (confident → confirmed через initReview): справа — код
// статьи, полное имя — только в title (спека §2 п.3, осознанный trade-off).
const ASSIGNED_ROWS: MatchRow[] = [
  row(1, 0, "confident", {
    source_name: "Сосед",
    breadcrumb: ["Раздел"],
    matched_code: "3.2",
    matched_name: "Устройство гидроизоляции фундамента",
  }),
  row(2, 1, "needs_review", {
    source_name: "Активная",
    breadcrumb: ["Раздел"],
  }),
]

it("правая часть присвоенного соседа — код, полное имя в title", () => {
  render(
    <ContextStrip state={initReview("x", ASSIGNED_ROWS)} activeRowNumber={2} />
  )
  const neighbor = screen.getByText("Сосед").closest("[data-row]")!
  // справа код, НЕ полное имя (однородный раздел не повторяет длинный хвост)
  expect(neighbor.textContent).toContain("→ 3.2")
  expect(neighbor.textContent).not.toContain(
    "Устройство гидроизоляции фундамента"
  )
  // полное имя доступно в title
  expect(
    within(neighbor).getByTitle("3.2 Устройство гидроизоляции фундамента")
  ).toBeInTheDocument()
})
```

Убедиться, что `within` импортирован в файле (в существующих тестах уже
используется — `import { render, screen, within } from "@testing-library/react"`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — сейчас `rightSide` возвращает `"3.2 Устройство гидроизоляции фундамента"`, `title` отсутствует, `textContent` содержит полное имя.

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx` — `rightSide`:

```tsx
// Присвоенный сосед: код статьи (моноширинно) — сигнал «ушёл вон куда»; полное
// имя в title. Однородный раздел иначе повторял бы длинный хвост имени в каждой
// строке и весил больше кандидатов (спека 3.6 §2 п.3). Осознанный trade-off:
// title недоступен с клавиатуры/тача — для сигнала соседства кода достаточно.
// Неприсвоенные соседи — статусная подпись без изменений.
// (форму Decision.confirmed сверять по lib/types.ts, не выдумывать поля)
function rightSide(
  state: ReviewState,
  r: MatchRow
): { text: string; title?: string; mono?: boolean } {
  const d = decisionFor(state, r)
  if (d.kind === "confirmed")
    return { text: d.code, title: `${d.code} ${d.name}`, mono: true }
  return { text: statusLabel(r, d) }
}
```

В теле `win.map` — вычислить `rs` рядом с `muted` (после строки `const muted = …`):

```tsx
        const muted = r.status === "excluded" || r.status === "pending"
        const rs = rightSide(state, r)
```

Правую часть неактивной строки (ветка `else` тернарника
`r.row_number === activeRowNumber ? … : …`) заменить:

```tsx
              ) : (
                <span
                  title={rs.title}
                  className={cn(
                    "ml-auto shrink-0 text-muted-foreground",
                    rs.mono && "font-mono"
                  )}
                >
                  → {rs.text}
                </span>
              )}
```

(ветка активной строки — `ArrowLeft`-маркер — НЕ трогается; `cn` уже импортирован.
`font-mono` только на коде — статусные подписи остаются обычным начертанием.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS. Существующие тесты границы/окна зелёные без правок: фикстуры
`SAME_LEAF_ROWS`/`SIBLING_ROWS` — `needs_review` → `pending` → правая часть это
`statusLabel` (не затронута); их ассерты идут по тексту разделителя «Раздел — …».

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.6): присвоенный сосед — код статьи, полное имя в title

Co-Authored-By: <модель-исполнителя> <noreply@anthropic.com>"
```

### Task 3: Кромка-резерв активной строки (без «дёрга» контента)

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (класс строки, [строки 85-91](../../../frontend/src/pages/estimate/ContextStrip.tsx#L85-L91))
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `data-active` на строке — сверено, уже в коде с 3.5
  ([ContextStrip.tsx:84](../../../frontend/src/pages/estimate/ContextStrip.tsx#L84));
  добавлять не нужно, тесты опираются на существующий.

- [ ] **Step 1: Write the failing tests**

```tsx
it("активная строка — перекрашенная кромка + тинт, маркер сохранён", () => {
  render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
  const active = screen.getByText("Строка 3").closest("[data-row]")!
  expect(active.className).toContain("border-l-2")
  // тон перекрашен (не прозрачный) — twMerge схлопывает border-transparent
  expect(active.className).not.toContain("border-transparent")
  // тинт из 3.5 сохранён
  expect(active.className).toContain("bg-[color-mix")
  // маркер «вы здесь» сохранён
  expect(within(active).getByLabelText("вы здесь")).toBeInTheDocument()
})

it("неактивная строка несёт кромку-резерв прозрачным тоном (нет «дёрга»)", () => {
  render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
  const other = screen.getByText("Строка 2").closest("[data-row]")!
  expect(other.className).toContain("border-l-2")
  expect(other.className).toContain("border-transparent")
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — `border-l-2` нет ни на одной строке.

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx` — класс строки: базовая кромка-резерв на КАЖДОЙ строке,
активная лишь перекрашивает тон (резерв ширины на всех строках убирает
горизонтальный сдвиг контента при переходе активной — спека §3 п.5):

```tsx
              className={cn(
                "flex items-center gap-2 border-l-2 border-transparent px-3 py-1.5",
                r.row_number === activeRowNumber &&
                  "border-primary bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]",
                muted && "opacity-60",
                openers[g] && "font-medium"
              )}
```

(твёрдый тон `border-primary` — стартовый; финальный тон и читаемость на
sunken-заливке проверяются на живом гейте Task 4. `tailwind-merge` в `cn`
схлопывает `border-transparent` → `border-primary` у активной, оставляя
`border-l-2`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS. Гвард роли из Task 1 остаётся зелёным (`border-l-2`/
`border-transparent` — не `rounded`/`border-border`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.6): кромка-резерв активной строки полосы без дёрга контента

Co-Authored-By: <модель-исполнителя> <noreply@anthropic.com>"
```

### Task 5: Приглушение имени рядового соседа (вторая ось открывашки)

Добавлена по живому гейту 2026-07-06 (спека §2 решение #6, §3 п.6): на
sunken-заливке `font-medium` открывашки против regular — различие на грани.
Решение — опустить фон (приглушить имя рядовых соседей), а не поднять фигуру:
классы открывашки НЕ трогаются, изгородь 3.5 не двигается, парный тест
самообъявления проходит без правок. Выполняется ПЕРЕД финальной верификацией
(Task 4 прогоняется заново после этой задачи).

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (span имени `source_name`, [строка 96](../../../frontend/src/pages/estimate/ContextStrip.tsx#L96))
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `openers[g]` (уже в компоненте с 3.5), `data-row`, `activeRowNumber`.
  Хелпер `headerRows(status)` уже в тест-файле (даёт открывашку «Подраздел Б» и
  рядовых соседей).

- [ ] **Step 1: Write the failing test**

```tsx
it("рядовой сосед приглушён по тону, открывашка — полный тон (вторая ось)", () => {
  // headerRows: row2 «Подраздел Б» — открывашка (next.breadcrumb = [Топ,Подраздел Б]);
  // row1 «Работа А1» — рядовой сосед; active=3 → окно включает обе, обе не активны.
  render(
    <ContextStrip
      state={initReview("x", headerRows("needs_review"))}
      activeRowNumber={3}
    />
  )
  const ordinaryName = screen.getByText("Работа А1")
  const openerName = screen.getByText("Подраздел Б")
  expect(ordinaryName.className).toContain("text-[var(--ds-text-2)]")
  expect(openerName.className).not.toContain("text-[var(--ds-text-2)]")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — сейчас имя рядового соседа не несёт `text-[var(--ds-text-2)]`
(span имени — просто `truncate`).

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx` — span имени (`<span className="truncate">{r.source_name}</span>`):

```tsx
              <span
                className={cn(
                  "truncate",
                  // Вторая ось открывашки (спека §2 решение #6): опускаем фон —
                  // рядовой сосед (не активная, не открывашка) приглушается, а
                  // открывашка остаётся на полном тоне + font-medium. Её классы
                  // не трогаются, изгородь 3.5 цела.
                  !openers[g] &&
                    r.row_number !== activeRowNumber &&
                    "text-[var(--ds-text-2)]"
                )}
              >
                {r.source_name}
              </span>
```

(`cn` уже импортирован. `section_code` слева уже `text-muted-foreground` — не
трогаем. excluded/pending остаются под `opacity-60` на строке — двойное затухание
excluded рядового соседа под наблюдением на гейте, спека §6/§4.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS. Все существующие тесты зелёные без правок — классы открывашки
(`font-medium`) и активной не изменены; меняется тон ДРУГИХ строк.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.6): приглушение имени рядового соседа — вторая ось открывашки

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 6: excluded/pending вне тонового приглушения (`!muted`)

Добавлена по живому гейту 2026-07-06 (спека §2 решение #6 финал). excluded/pending
уже несут свою ось «тихо» — `opacity-60`; тон-приглушение поверх было бы двойным
кодированием и риском двойного затухания на sunken. Гейт показал 0 excluded-
не-открывашек на 4 сметы (двойное затухание в данных не возникает), `!muted`
закрывает и теоретический хвост (excluded-лист без детей) по конструкции.

**Files:**
- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (условие тон-приглушения имени, строка из Task 5)
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**
- Consumes: `muted` (уже вычислен в компоненте: `r.status === "excluded" || r.status === "pending"`).

- [ ] **Step 1: Write the failing test**

```tsx
it("excluded/pending рядовой сосед НЕ приглушается тоном (своя ось opacity-60)", () => {
  // excluded НЕ-открывашка (next.breadcrumb === текущему, не +1), не активная:
  // после Task 5 попал бы под text-2; решение #6 (!muted) его исключает.
  const rows = [
    row(1, 0, "excluded", { source_name: "Орг-лист", breadcrumb: ["Топ"] }),
    row(2, 1, "needs_review", { source_name: "Активная", breadcrumb: ["Топ"] }),
  ]
  render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
  const name = screen.getByText("Орг-лист")
  expect(name.className).not.toContain("text-[var(--ds-text-2)]")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: FAIL — «Орг-лист» (excluded, не-открывашка, не активная) сейчас несёт
`text-[var(--ds-text-2)]` (условие Task 5 его не исключает).

- [ ] **Step 3: Write minimal implementation**

`ContextStrip.tsx` — к условию тон-приглушения имени добавить `&& !muted`:

```tsx
              <span
                className={cn(
                  "truncate",
                  // excluded/pending исключены (спека §2 решение #6): у них своя
                  // ось «тихо» — opacity-60; тон был бы двойным кодированием.
                  !openers[g] &&
                    r.row_number !== activeRowNumber &&
                    !muted &&
                    "text-[var(--ds-text-2)]"
                )}
              >
                {r.source_name}
              </span>
```

(`muted` уже объявлен строкой выше в теле `win.map`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend; npx vitest run src/pages/estimate/ContextStrip.test.tsx`
Expected: PASS. Тест Task 5 (рядовой WORK `needs_review` приглушён, открывашка —
нет) остаётся зелёным: `needs_review` не muted.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(ux3.6): excluded/pending вне тонового приглушения (своя ось opacity-60)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 4: Верификация — полный прогон, живой гейт, devlog, PR

(Прогоняется ЗАНОВО после Task 5 и Task 6.)

- [ ] **Step 1: Полный прогон**

Run: `cd frontend; npm run typecheck; npx vitest run` затем из корня `just lint`
Expected: всё зелёное (typecheck, весь vitest, ruff+eslint+prettier).

- [ ] **Step 2: Живой гейт (браузер, `just dev-back` / `just dev-front`)**

Смета 16 + смета с однородным разделом (скриншот из 3.5, «С5_MIND_Этап 1»),
до/после:

- полоса читается как **справка** (утопленная залитая панель с подписью
  «Окружение в смете»), а не «ещё пять кандидатов без номеров»;
- правый столбец **не шумит**: коды `→ 3.2` вместо повторяющегося длинного
  имени статьи; полное имя всплывает в `title` при наведении;
- **открывашки как вехи на sunken-заливке** (после Task 5): открывашка отбита
  двумя осями (полный тон + `font-medium`) на фоне приглушённых рядовых соседей
  (`text-[var(--ds-text-2)]`) — проверить, что заголовки встают вехами, а не
  сливаются с рядовыми (риск §6, ровно этот пункт всплыл на гейте 2026-07-06);
- **excluded рядовой сосед — двойное затухание** (`text-2` × `opacity-60`): по
  замыслу самая тихая строка; если ушла за порог читаемости на sunken —
  исключить excluded из тонового приглушения (одна ветка в `cn`, спека §6/§4);
- **смета 16 — подпись «Раздел — …»** на разделителе-в-одиночку (некодированный
  заголовок) читается на sunken-фоне (вторая половина семантики границы, не
  показанная на однородном разделе);
- **воздух** полоса↔кандидаты ощущается паузой «читаю → выбираю»; при
  необходимости скорректировать `mb-4` так, чтобы разрыв был заметно больше
  внутристрочного шага полосы;
- **активная строка**: кромка + тинт, не выглядит кнопкой; при движении очереди
  контент строк не прыгает по горизонтали (кромка-резерв на всех строках).

- [ ] **Step 3: Devlog + PR**

Посмотреть `ls docs/devlog` и создать запись по образцу соседних (что сделано,
ссылка на спеку; отложенное — только указателем в TECH_DEBT, если появилось).
PR `feat/ux-stage3-6-strip-surface` → `main` через
`superpowers:finishing-a-development-branch`. CodeRabbit сработает на base=main —
проверить все три источника ревью (top-level, inline, review bodies).

---

## Self-Review Checklist (покрытие спеки)

- **§3 п.1 (заливка) + п.2 (подпись) + п.4 (воздух) → Task 1** (заливка
  sunken-токеном, подпись «Окружение в смете», `mb-*`; гвард роли — регресс-замок
  «нет словаря кандидата»).
- **§3 п.3 (right-side код + title) → Task 2** (confirmed → код + `title`,
  моноширинно; статусные подписи неприсвоенных — без изменений).
- **§3 п.5 (кромка активной) → Task 3** (кромка-резерв `border-l-2 border-transparent`
  на всех строках, активная перекрашивает тон; тинт и маркер сохранены).
- **§3 п.6 (приглушение имени рядового соседа) → Task 5 + Task 6** (рядовой
  не-активный не-открывашка **не-muted** → `text-[var(--ds-text-2)]`; открывашка/
  активная/excluded/pending — полный тон; условие `!openers[g] && !active && !muted`;
  классы открывашки 3.5 не тронуты — вторая ось через приглушение окружения).
- **§4 тесты:** подпись рендерится (Task 1); строки без словаря кандидата
  (Task 1); right-side присвоенного = код + title (Task 2); активная — кромка +
  тинт + маркер, неактивная — резерв прозрачным тоном (Task 3); рядовой сосед
  приглушён, открывашка — нет (Task 5); excluded/pending не приглушаются тоном
  (Task 6). Существующие
  тесты семантики границы 3.5 остаются зелёными без правок (§4, Global
  Constraints) — маркер-тест, парный тест самообъявления, страж независимости
  от `MatchStatus`, «путь укоротился», «две границы» не затрагиваются.
- **§4 живой гейт → Task 4** (смета 16 + однородный раздел С5_MIND: справка vs
  действие, правый столбец, открывашки-вехи после приглушения соседей, двойное
  затухание excluded, подпись «Раздел — …» на смете 16, воздух, кромка без
  «дёрга»).
- **§5 вне скоупа — соблюдено:** тултип-компонент (остаётся нативный `title`),
  виртуализация/интерактив полосы, словарь кандидатов и остальная карточка,
  дедуп токена в `ds-table` — ни одной задачей не трогаются.
- **§2 «что не меняется» — соблюдено:** семантика границы (эффективные пути,
  `isOpener`, подавление, `font-medium`, `data-opener`, страж статуса),
  приглушение excluded/pending, контракт payload, контракты excluded, бэкенд —
  вне правок (Global Constraints).
