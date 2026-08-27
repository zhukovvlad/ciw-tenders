# Блок «Ваш выбор» + скраббер-навигация — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать решение оператора самым заметным элементом карточки ревью и превратить полосу окружения из справки в навигацию.

**Architecture:** Две независимые части. Фича 1 — презентационная: `ReviewCard` получает блок «Ваш выбор», секция рекомендации демоутится, `Enter` гасится на решённых строках. Фича 2 — навигационная: `useReviewQueue` переходит с переупорядочивания очереди на **позиционную модель** (позиция = `sourceIndex` последней обработанной строки, следующая активная — первая нерешённая строго после неё с обёрткой к самой ранней), а `ContextStrip` получает кликабельные строки.

**Tech Stack:** React 19, TypeScript strict, Tailwind v4, shadcn/ui, react-i18next, vitest + React Testing Library.

**Spec:** [2026-07-07-review-card-choice-and-scrubber-design.md](../specs/2026-07-07-review-card-choice-and-scrubber-design.md)

## Global Constraints

- **TDD обязателен:** тест пишется первым, запускается и наблюдается падающим, только потом реализация. Тест, прошедший сразу, — сигнал, что он проверяет не то.
- **i18n:** любой новый UI-текст идёт через `t("...")` и добавляется в **оба** словаря (`frontend/src/locales/ru.json`, `frontend/src/locales/tr.json`). Тест чётности `frontend/src/locales/parity.test.ts` требует полноты — расхождение уронит сборку.
- **Prettier:** `printWidth 80`, `endOfLine lf`. Перед коммитом `cd frontend && npx prettier --write <файлы>`.
- **TypeScript:** проверка только через `npx tsc -b` (корневой `tsconfig.json` — solution-файл; `tsc --noEmit` без `-b` не проверит ничего).
- **Серверный контракт не меняется.** Обе фичи чисто клиентские: ни DTO, ни роуты, ни схемы не трогаются.
- **Запуск тестов:** `cd frontend && npx vitest run <путь>`. Полный прогон занимает ~2 минуты.
- **Базовая линия на момент написания плана:** `tsc -b` чисто, `vitest run` — 37 файлов / 270 тестов зелёные.

---

## Расхождение со спекой (сознательное отступление, Task 3)

Спека предлагает сохранить инвариант «ошибка PATCH → строка в голову» так:

> `commitFailed` принудительно ставит текущую позицию ПЕРЕД откатившейся строкой — тогда «следующая нерешённая после позиции» это и есть откатившаяся строка.

**Этого недостаточно.** `commitFailed` вызывается из `.then` упавшего PATCH-а и одновременно **пиннит оператора** на строке, которую он решает прямо сейчас (существующее поведение, защищённое пин-тестом «STALE CLOSURE»). Когда оператор решит эту строку, её `committed` перезапишет позицию на «после себя» — а откатившаяся строка обычно раньше по документу, значит она снова уедет в хвост и подхватится только обёрткой в самом конце прохода. Инвариант умрёт молча, ровно чего спека и опасалась.

**Решение в плане:** у откатившейся строки отдельный приоритетный слот `priority` (row_number), который проверяется перед позицией. Он не требует ручного сброса — гаснет сам, как только строка перестала быть `pending`. Позиция остаётся простым `number | null` без разновидностей `after`/`from`.

Это единственное отступление от спеки; остальное реализуется как написано.

---

### Task 1: Блок «Ваш выбор» в карточке ревью

**Files:**

- Modify: `frontend/src/pages/estimate/ReviewCard.tsx` (вывод `yourChoice` рядом с `syntheticRecommendation` ~строка 75; вставка разметки после `{contextStrip}`, строка 120)
- Modify: `frontend/src/locales/ru.json` (секция `review`)
- Modify: `frontend/src/locales/tr.json` (секция `review`)
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

**Interfaces:**

- Consumes: существующие `Decision` (`@/lib/types`), `CrumbTrail` (`@/components/estimate/CrumbTrail`), хелперы теста `row(...)`, `renderCard(...)`, константа `CAND` — всё уже есть в `ReviewCard.test.tsx`.
- Produces: `data-testid="your-choice"` — на него опирается Task 2. Ключи `review.yourChoice`, `review.systemRecommendationLabel`.

- [ ] **Step 1: Добавить i18n-ключи в оба словаря**

В `frontend/src/locales/ru.json`, в секцию `review` (рядом с `"aiRecommendation"`):

```json
    "yourChoice": "Ваш выбор",
    "systemRecommendationLabel": "Рекомендация системы",
```

В `frontend/src/locales/tr.json`, в секцию `review`, на том же месте:

```json
    "yourChoice": "Seçiminiz",
    "systemRecommendationLabel": "Sistem önerisi",
```

- [ ] **Step 2: Написать падающие тесты**

В `frontend/src/pages/estimate/ReviewCard.test.tsx` добавить в конец файла:

```tsx
describe("ReviewCard: блок «Ваш выбор»", () => {
  const CAND2: Candidate = {
    id: 9,
    article_code: "07.01",
    name: "Кровельные работы",
    score: 0.64,
    breadcrumb: ["07 Кровля"],
  }

  it("override: показывает код, имя и крошку кандидата по коду", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [CAND, CAND2],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: CAND2.article_code,
        name: CAND2.name,
        manual: false,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).getByText("07.01")).toBeInTheDocument()
    expect(within(block).getByText("Кровельные работы")).toBeInTheDocument()
    expect(within(block).getByText(/07 Кровля/)).toBeInTheDocument()
  })

  it("выбор из поиска: крошка из finalBreadcrumb, когда код совпал с final_code", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
      final_code: "09.09",
      finalBreadcrumb: ["09 Прочее"],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).getByText(/09 Прочее/)).toBeInTheDocument()
  })

  it("крошки нет, если код решения не совпал с final_code и не найден в кандидатах", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
      final_code: "99.99",
      finalBreadcrumb: ["99 Устаревшее"],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).queryByText(/99 Устаревшее/)).toBeNull()
  })

  it("строка no_match, решённая через поиск: блок есть, подписи рекомендации нет", () => {
    const r = row(5, 2, "no_match", {
      matched_code: null,
      matched_name: null,
      candidates: [],
      final_code: "09.09",
      finalBreadcrumb: [],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    expect(screen.getByTestId("your-choice")).toBeInTheDocument()
    expect(screen.queryByText("Рекомендация системы")).toBeNull()
  })

  it("строка error, решённая через поиск: блок есть и стоит ВЫШЕ Alert-а", () => {
    const r = row(5, 2, "error", {
      matched_code: null,
      matched_name: null,
      matchError: "LLM timeout",
      candidates: [],
      final_code: "09.09",
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    const alertText = screen.getByText("LLM timeout")
    // DOCUMENT_POSITION_FOLLOWING === 4: alert идёт ПОСЛЕ блока
    expect(
      block.compareDocumentPosition(alertText) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it("подтверждение самой рекомендации блок НЕ показывает", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "01.01",
        name: "Статья",
        manual: false,
      },
    })
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("нерешённая строка блок НЕ показывает (pending)", () => {
    renderCard(row(5, 2, "needs_review", { candidates: [] }))
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("нерешённая error-строка блок НЕ показывает", () => {
    renderCard(
      row(5, 2, "error", {
        matched_code: null,
        matched_name: null,
        matchError: "LLM timeout",
        candidates: [],
      })
    )
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("reject-решение блок НЕ показывает", () => {
    renderCard(row(5, 2, "no_match", { candidates: [] }), {
      decision: { kind: "no_match" },
    })
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("при показанном блоке рекомендация уходит под подпись «Рекомендация системы»", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [CAND2],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: CAND2.article_code,
        name: CAND2.name,
        manual: false,
      },
    })
    expect(screen.getByText("Рекомендация системы")).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Запустить тесты и убедиться, что падают**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewCard.test.tsx`

Expected: FAIL — `Unable to find an element by: [data-testid="your-choice"]` в тестах, где блок ожидается, и `Unable to find an element with the text: Рекомендация системы` в последнем.

Тесты «блок НЕ показывает» на этом шаге проходят — они защитные, их роль остаться зелёными и после реализации.

- [ ] **Step 4: Вывести `yourChoice` в `ReviewCard`**

В `frontend/src/pages/estimate/ReviewCard.tsx`, сразу после блока `syntheticRecommendation` (после строки 75):

```tsx
  // Блок «Ваш выбор» (спека фичи 1): решение оператора, отличающееся от
  // рекомендации системы — override, выбор не-рекомендованного кандидата или
  // выбор из поиска на строке без рекомендации (matched_code === null).
  // Подтверждение самой рекомендации блок НЕ показывает: её подсветка и так
  // верна. На нерешённых строках любых статусов блок не появляется по kind —
  // отдельная ветка по row.status не нужна и вредна (убила бы полезный
  // случай «решённая через поиск error-строка»).
  const yourChoice =
    decision.kind === "confirmed" && decision.code !== row.matched_code
      ? {
          code: decision.code,
          name: decision.name,
          // Крошка: кандидат по коду → finalBreadcrumb, но ТОЛЬКО если он про
          // этот же код (в переходном окне до синка final_* могут отставать) →
          // иначе крошки нет.
          breadcrumb:
            row.candidates.find((c) => c.article_code === decision.code)
              ?.breadcrumb ??
            (decision.code === row.final_code
              ? row.finalBreadcrumb
              : undefined),
        }
      : null
```

- [ ] **Step 5: Отрисовать блок и подпись рекомендации**

В том же файле, сразу после `{contextStrip}` (строка 120) и ПЕРЕД `{row.status === "error" ? (`:

```tsx
        {/* 2c. Блок «Ваш выбор» (спека фичи 1). Стоит ДО тернарника по status,
            поэтому на error-строке автоматически оказывается над Alert-ом:
            сначала выбор оператора, затем диагностика исходной ошибки. */}
        {yourChoice && (
          <div
            data-testid="your-choice"
            className="flex items-center gap-3 rounded-md border border-primary px-3 py-2 text-sm shadow-[var(--ds-glow-violet)]"
          >
            <span className="shrink-0 text-xs text-muted-foreground">
              ★ {t("review.yourChoice")}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {yourChoice.code}
            </span>
            <span className="flex min-w-0 flex-1 items-baseline gap-2">
              <span>{yourChoice.name}</span>
              {yourChoice.breadcrumb?.length ? (
                <CrumbTrail
                  levels={yourChoice.breadcrumb}
                  className="min-w-0 truncate"
                />
              ) : null}
            </span>
          </div>
        )}
```

Затем внутри ветки `) : (` — то есть в `<>`, непосредственно перед `{syntheticRecommendation && (`:

```tsx
            {/* Демоушен рекомендации: подпись появляется только вместе с
                блоком «Ваш выбор» — там она различает выбор оператора и
                предложение системы. На обычной нерешённой строке подпись
                избыточна, поэтому вид карточки в основном потоке не меняется. */}
            {yourChoice && recommended && (
              <div className="text-[11px] tracking-wide text-muted-foreground uppercase">
                {t("review.systemRecommendationLabel")}
              </div>
            )}
```

- [ ] **Step 6: Запустить тесты и убедиться, что проходят**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewCard.test.tsx src/locales/parity.test.ts`

Expected: PASS, все тесты обоих файлов.

- [ ] **Step 7: Прогнать typecheck и весь фронт**

Run: `cd frontend && npx tsc -b && npx vitest run`

Expected: `tsc` без вывода; vitest — все зелёные (270 прежних + новые).

- [ ] **Step 8: Отформатировать и закоммитить**

```bash
cd frontend && npx prettier --write src/pages/estimate/ReviewCard.tsx src/pages/estimate/ReviewCard.test.tsx src/locales/ru.json src/locales/tr.json
cd .. && git add frontend/src/pages/estimate/ReviewCard.tsx frontend/src/pages/estimate/ReviewCard.test.tsx frontend/src/locales/ru.json frontend/src/locales/tr.json
git commit -m "feat(review): блок «Ваш выбор» на карточке ревью

Решение оператора было видно только приглушённой подсветкой кандидата, а
выбор из поиска — нигде. Блок показывается, когда решение отличается от
рекомендации системы, и демоутит её под подпись «Рекомендация системы».

Стоит до тернарника по status, поэтому на error-строке оказывается над
Alert-ом: сначала выбор оператора, затем диагностика ошибки."
```

---

### Task 2: Гашение `Enter` на решённых строках

**Files:**

- Modify: `frontend/src/pages/estimate/ReviewCard.tsx` (бейдж `Enter` внутри кнопки синтетической рекомендации ~строка 172; `LegendItem` с `keyLabel="Enter"` ~строка 303)
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx:124` (гейт `canConfirm`)
- Test: `frontend/src/pages/estimate/ReviewCard.test.tsx`

**Interfaces:**

- Consumes: `decision: Decision` — уже проп `ReviewCard`; `hasRecommendation(row)` из `@/pages/estimate/ReviewCard`; `decisionFor(state, row)` из `@/lib/reviewState`; `data-testid="your-choice"` (Task 1).
- Produces: ничего для последующих задач.

**Зачем:** после Task 1 рекомендация стоит НИЖЕ блока «Ваш выбор», поэтому случайный `Enter` на решённой строке вероятнее — а он перезаписал бы выбор оператора одним нажатием. Правило: `Enter` активен только пока `decision.kind === "pending"`. Клик по рекомендации остаётся (явный ручной возврат к ней), исчезает только бейдж и работа клавиши — инвариант «нет бейджа ⇒ нет клавиши» сохранён.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `frontend/src/pages/estimate/ReviewCard.test.tsx`:

```tsx
describe("ReviewCard: Enter гаснет на решённых строках", () => {
  const r = row(5, 2, "needs_review", {
    matched_code: "01.01",
    matched_name: "Статья",
    candidates: [],
  })

  it("на pending-строке бейдж Enter внутри рекомендации есть", () => {
    renderCard(r)
    const rec = screen.getByText("Статья").closest("button")!
    expect(within(rec).getByText("Enter")).toBeInTheDocument()
  })

  it("на решённой строке бейджа Enter у рекомендации нет", () => {
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "07.01",
        name: "Кровельные работы",
        manual: false,
      },
    })
    // легенда клавиш содержит слово Enter всегда — проверяем именно бейдж
    // внутри кнопки рекомендации
    const rec = screen.getByText("Статья").closest("button")!
    expect(within(rec).queryByText("Enter")).toBeNull()
  })

  it("клик по рекомендации на решённой строке по-прежнему работает", async () => {
    const props = renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "07.01",
        name: "Кровельные работы",
        manual: false,
      },
    })
    const rec = screen.getByText("Статья").closest("button")!
    await userEvent.click(rec)
    expect(props.onConfirmRecommendation).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewCard.test.tsx -t "Enter гаснет"`

Expected: FAIL на «бейджа Enter у рекомендации нет» — бейдж находится. Два других теста проходят сразу (пины существующего поведения).

- [ ] **Step 3: Скрыть бейдж и приглушить легенду**

В `frontend/src/pages/estimate/ReviewCard.tsx` заменить безусловный бейдж внутри кнопки синтетической рекомендации:

```tsx
                <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
                  Enter
                </kbd>
```

на:

```tsx
                {/* Инвариант «клавиша ⇔ элемент»: на решённой строке Enter
                    инертен (защита выбора оператора от перезаписи одним
                    нажатием), поэтому и бейджа нет. Клик остаётся. */}
                {decision.kind === "pending" && (
                  <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
                    Enter
                  </kbd>
                )}
```

И в постоянной легенде клавиш заменить:

```tsx
          <LegendItem
            keyLabel="Enter"
            text={t("review.hintConfirm")}
            muted={!recommended}
          />
```

на:

```tsx
          <LegendItem
            keyLabel="Enter"
            text={t("review.hintConfirm")}
            muted={!recommended || decision.kind !== "pending"}
          />
```

- [ ] **Step 4: Закрыть клавишу в `ReviewScreen`**

В `frontend/src/pages/estimate/ReviewScreen.tsx:124` заменить:

```tsx
    canConfirm: active ? hasRecommendation(active) : false,
```

на:

```tsx
    // Enter активен только пока строка не решена: на решённой (её открыли из
    // грида или полосы) он перезаписал бы выбор оператора одним нажатием.
    canConfirm: active
      ? hasRecommendation(active) &&
        decisionFor(state, active).kind === "pending"
      : false,
```

`decisionFor` уже импортирован в этом файле (используется при рендере `ReviewCard`) — новый импорт не нужен. Если `tsc` скажет иначе, добавить его в существующий импорт из `@/lib/reviewState`.

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewCard.test.tsx src/pages/estimate/ReviewScreen.test.tsx src/lib/useReviewKeyboard.test.tsx`

Expected: PASS.

- [ ] **Step 6: Прогнать typecheck и весь фронт**

Run: `cd frontend && npx tsc -b && npx vitest run`

Expected: чисто и зелено.

- [ ] **Step 7: Отформатировать и закоммитить**

```bash
cd frontend && npx prettier --write src/pages/estimate/ReviewCard.tsx src/pages/estimate/ReviewCard.test.tsx src/pages/estimate/ReviewScreen.tsx
cd .. && git add frontend/src/pages/estimate/ReviewCard.tsx frontend/src/pages/estimate/ReviewCard.test.tsx frontend/src/pages/estimate/ReviewScreen.tsx
git commit -m "feat(review): Enter инертен на решённых строках

После демоушена рекомендации под блок «Ваш выбор» случайный Enter стал
вероятнее, а он перезаписывал бы решение оператора одним нажатием. Теперь
confirmArbiter активен только при decision.kind === pending; бейдж Enter на
решённой строке скрыт (инвариант «клавиша ⇔ элемент»), клик по рекомендации
остаётся как явный ручной возврат к ней."
```

---

### Task 3: Позиционная модель очереди (ядро скраббера)

**Files:**

- Modify: `frontend/src/lib/useReviewQueue.ts` (переписываются `order`→`queue`, `skip`, `committed`, `commitFailed`; добавляются `position`, `priority`, `navigateTo`)
- Test: `frontend/src/lib/useReviewQueue.test.ts`

**Interfaces:**

- Consumes: `requiresDecision`, `decisionFor` из `@/lib/reviewState`; типы `MatchRow`, `ReviewState`.
- Produces: `ReviewQueue.navigateTo: (rowNumber: number) => void` — Task 5 вешает его на `ContextStrip`. Поле `queue: MatchRow[]` теперь **всегда** отсортировано по `sourceIndex` и никогда не переупорядочивается.

**Переписываемый пин-тест (обоснование обязательно).** Существующий тест «активная уходит в хвост, следующей встаёт очередная нерешённая» (`useReviewQueue.test.ts:72`) пинует старую механику: `skip` физически двигал строку в конец `order`, и это наблюдалось через `result.current.queue`. Позиционная модель этого не делает — пропущенная строка остаётся на своём месте в порядке документа и подхватывается обёрткой в конце прохода. Наблюдаемый эффект для оператора тот же (пропустил → вернулся в конце), меняется только внутреннее представление. Тест переписывается на проверку **эффекта**, а не представления. Остальные пины (`origin=grid`, `undo`/`returnTo`, `STALE CLOSURE`, `commitFailed`, «двойной коммит») остаются без правок.

- [ ] **Step 1: Написать падающие тесты**

В `frontend/src/lib/useReviewQueue.test.ts` **заменить** тест на строке 72 (`it("активная уходит в хвост, следующей встаёт очередная нерешённая", ...)`) на два:

```ts
  it("N: очередь НЕ переупорядочивается, активной встаёт следующая по документу", () => {
    const { result } = setup()
    // порядок документа: 20 (si=1), 50 (si=4), 10 (si=5)
    expect(result.current.activeRow?.row_number).toBe(20)
    act(() => void result.current.skip())
    // пропущенная 20 осталась на месте — «следующую» задаёт позиция, не порядок
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("обёртка: после последней нерешённой поток возвращается к самой ранней", () => {
    const { result } = setup()
    act(() => void result.current.skip()) // с 20 → 50
    act(() => void result.current.skip()) // с 50 → 10
    expect(result.current.activeRow?.row_number).toBe(10)
    act(() => void result.current.skip()) // дальше нет → обёртка к ранней
    expect(result.current.activeRow?.row_number).toBe(20)
  })
```

И добавить в конец файла:

```ts
describe("useReviewQueue: скраббер-навигация", () => {
  it("navigateTo делает произвольную строку активной с origin=flow", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(10))
    expect(result.current.activeRow?.row_number).toBe(10)
    expect(result.current.origin).toEqual({ kind: "flow" })
  })

  it("navigateTo не пишется в undo-стек (навигация ≠ решение)", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(10))
    expect(result.current.canUndo).toBe(false)
  })

  it("после решения строки из полосы поток идёт от её позиции вперёд", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(20)) // si=1, самая ранняя
    let exit: ReturnType<typeof result.current.committed> | undefined
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "next" })
    // следующая нерешённая строго после si=1 — это 50 (si=4)
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("ad-hoc строка из полосы (confident) решается, поток идёт от её позиции", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(30)) // confident, si=2, не в очереди
    expect(result.current.activeRow?.row_number).toBe(30)
    act(() => void result.current.committed(30))
    // первая нерешённая строго после si=2 — 50 (si=4)
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("линейный проход сверху вниз не изменился (пин обратной совместимости)", () => {
    const { result } = setup()
    const seen: number[] = []
    for (let k = 0; k < 3; k++) {
      const n = result.current.activeRow?.row_number
      if (n === undefined) break
      seen.push(n)
      act(() => void result.current.committed(n))
    }
    expect(seen).toEqual([20, 50, 10])
    expect(result.current.activeRow).toBeNull()
  })

  it("commitFailed: откатившаяся строка следующая ПОСЛЕ текущей (пин PR-B)", () => {
    const { result } = setup()
    // решаем 20 (si=1) — активной становится 50
    act(() => void result.current.committed(20))
    expect(result.current.activeRow?.row_number).toBe(50)
    // PATCH по 20 падает: оператора не выдёргиваем, но 20 должна стать следующей
    act(() => result.current.commitFailed(20))
    expect(result.current.activeRow?.row_number).toBe(50)
    // решаем текущую 50 — и вот теперь всплывает откатившаяся 20,
    // хотя по документу она ПОЗАДИ позиции (si=1 < si=4)
    act(() => void result.current.committed(50))
    expect(result.current.activeRow?.row_number).toBe(20)
  })
})
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `cd frontend && npx vitest run src/lib/useReviewQueue.test.ts`

Expected: FAIL — `result.current.navigateTo is not a function` в новом describe; в переписанных тестах `queue` приходит `[50, 10, 20]` вместо `[20, 50, 10]`, а `activeRow` не тот; пин PR-B даёт `10` вместо `20`.

- [ ] **Step 3: Заменить состояние очереди на позиционное**

В `frontend/src/lib/useReviewQueue.ts` добавить `navigateTo` в интерфейс:

```ts
export interface ReviewQueue {
  queue: MatchRow[]
  activeRow: MatchRow | null
  origin: CardOrigin
  canUndo: boolean
  openFromGrid: (rowNumber: number) => void
  navigateTo: (rowNumber: number) => void
  skip: () => CommitExit
  undo: () => void
  committed: (rowNumber: number) => CommitExit
  commitFailed: (rowNumber: number) => void
  deselect: () => void
}
```

Заменить объявления состояния (текущие строки 37–45: `initialOrder` и `const [order, setOrder]`) на:

```ts
export function useReviewQueue(state: ReviewState): ReviewQueue {
  const [undoStack, setUndoStack] = useState<number[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  // Позиция скраббера: sourceIndex последней обработанной строки. Следующая
  // активная — первая нерешённая СТРОГО ПОСЛЕ неё по порядку документа, с
  // обёрткой к самой ранней. null — сессия только началась, ищем с начала.
  // Заменяет прежнее переупорядочивание order: оператор движется в одном
  // направлении по смете, а полоса лишь переставляет точку продолжения.
  const [position, setPosition] = useState<number | null>(null)
  // Инвариант PR-B «ошибка PATCH → строка становится следующей». Позиции для
  // этого мало: commitFailed пиннит оператора на строке, которую он решает
  // сейчас, а её committed перезапишет позицию на «после себя» — откатившаяся
  // (она обычно раньше по документу) снова уехала бы в хвост. Поэтому
  // отдельный слот, проверяемый ПЕРЕД позицией. Ручного сброса не требует:
  // гаснет сам, когда строка перестала быть pending (условие в autoActive).
  const [priority, setPriority] = useState<number | null>(null)
```

`sessionDecided` (текущая строка 51) оставить как есть, вместе с комментарием.

- [ ] **Step 4: Обновить сброс сессии и вывод очереди**

Заменить ветку сброса на смену набора спорных на:

```ts
  const [prevIdsKey, setPrevIdsKey] = useState(idsKey)
  if (prevIdsKey !== idsKey) {
    setPrevIdsKey(idsKey)
    setUndoStack([])
    setSelection(null)
    setPosition(null)
    setPriority(null)
    // Сброс сессии — мутировать ref во время рендера здесь безопасно: ветка
    // выполняется однократно на смену набора и не участвует в выводе JSX.
    // eslint-disable-next-line react-hooks/refs
    sessionDecided.current = new Set()
  }
```

Заменить `queue` (текущие строки 81–87) — очередь больше не состояние, а производная от строк:

```ts
  // Очередь спорных в порядке документа. НЕИЗМЕНЯЕМА: в позиционной модели ни
  // skip, ни commitFailed её не переупорядочивают — «следующую» задают
  // position/priority, а не порядок массива.
  const queue = useMemo(
    () =>
      state.rows
        .filter(requiresDecision)
        .sort((a, b) => a.sourceIndex - b.sourceIndex),
    [state.rows]
  )
```

- [ ] **Step 5: Переписать выбор активной строки**

Заменить блок вычисления `autoActive` (текущие строки 93–99) на:

```ts
  const isPending = (r: MatchRow) =>
    decisionFor(state, r).kind === "pending" &&
    !sessionDecided.current.has(r.row_number)

  // eslint-disable-next-line react-hooks/refs -- см. комментарий у sessionDecided/isPending
  const pending = queue.filter(isPending)

  const nextByPosition = (): MatchRow | null => {
    if (pending.length === 0) return null
    if (position === null) return pending[0]
    // Обёртка к самой ранней нерешённой, если впереди по документу пусто.
    return pending.find((r) => r.sourceIndex > position) ?? pending[0]
  }

  const priorityRow = priority !== null ? byNum.get(priority) : undefined
  const autoActive =
    priorityRow && pending.includes(priorityRow)
      ? priorityRow
      : nextByPosition()

  const activeRow = selection ? (byNum.get(selection.row) ?? null) : autoActive
```

- [ ] **Step 6: Добавить `navigateTo` и перевести переходы на позицию**

После `openFromGrid` добавить:

```ts
  // Скраббер: клик по строке окружения. От openFromGrid отличается только
  // origin — после решения оператор продолжает поток от этой позиции, а не
  // возвращается в грид. В undo-стек не пишется: навигация ≠ решение.
  const navigateTo = (rowNumber: number) =>
    setSelection({ row: rowNumber, origin: { kind: "flow" } })

  // Позиция = sourceIndex обработанной строки; следующая ищется строго после.
  const advanceFrom = (rowNumber: number) => {
    const si = byNum.get(rowNumber)?.sourceIndex
    if (si !== undefined) setPosition(si)
  }
```

Заменить `skip` на:

```ts
  const skip = (): CommitExit => {
    const n = activeRow?.row_number
    if (n === undefined) return { kind: "next" }
    if (!queue.some((r) => r.row_number === n)) {
      // Ad-hoc строка (confident/фонд, открытая из грида или полосы):
      // «пропустить» = передумал — уходим туда, откуда пришли, позицию потока
      // не двигаем.
      const exit = exitFor(origin)
      if (exit.kind === "row")
        setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
      else setSelection(null)
      return exit
    }
    // Пропущенная строка остаётся нерешённой на своём месте в порядке
    // документа и подхватится обёрткой в конце прохода — переупорядочивать
    // очередь больше не нужно.
    advanceFrom(n)
    setSelection(null)
    return { kind: "next" }
  }
```

Заменить `committed` на:

```ts
  const committed = (rowNumber: number): CommitExit => {
    setUndoStack((s) => [...s, rowNumber])
    sessionDecided.current.add(rowNumber)
    const exit = exitFor(origin)
    if (exit.kind === "row")
      setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
    else {
      advanceFrom(rowNumber)
      setSelection(null)
    }
    return exit
  }
```

Заменить `commitFailed` на (ушла мутация `order`, добавился `setPriority`):

```ts
  const commitFailed = (rowNumber: number) => {
    setUndoStack((s) => {
      const i = s.lastIndexOf(rowNumber)
      return i === -1 ? s : [...s.slice(0, i), ...s.slice(i + 1)]
    })
    sessionDecided.current.delete(rowNumber)
    // Откатившаяся строка — следующая, как только оператор закончит текущую.
    setPriority(rowNumber)
    // Не выдёргивать оператора из текущей строки: пиннуть её, если явного
    // выбора не было.
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
```

Добавить `navigateTo` в возвращаемый объект, сразу после `openFromGrid`:

```ts
    openFromGrid,
    navigateTo,
```

- [ ] **Step 7: Запустить тесты и убедиться, что проходят**

Run: `cd frontend && npx vitest run src/lib/useReviewQueue.test.ts`

Expected: PASS — все тесты файла, включая нетронутые пины `origin=grid`, `undo`/`returnTo`, `STALE CLOSURE`, «двойной коммит».

Если упал пин «STALE CLOSURE» или «commitFailed … активная не прыгает» — НЕ правь тест: смотри порядок `setPriority`/`setSelection` в `commitFailed`, инвариант «оператора не выдёргивает» должен сохраниться.

- [ ] **Step 8: Прогнать typecheck и весь фронт**

Run: `cd frontend && npx tsc -b && npx vitest run`

Expected: `tsc` чисто. Возможные падения — в `ReviewScreen.test.tsx`/`EstimatePage.test.tsx`, если они опирались на переупорядочивание после `skip`; тогда править их тем же принципом (проверять активную строку, а не порядок массива), сохраняя намерение теста.

- [ ] **Step 9: Отформатировать и закоммитить**

```bash
cd frontend && npx prettier --write src/lib/useReviewQueue.ts src/lib/useReviewQueue.test.ts
cd .. && git add frontend/src/lib/useReviewQueue.ts frontend/src/lib/useReviewQueue.test.ts
git commit -m "feat(review): позиционная модель очереди — ядро скраббера

Вместо переупорядочивания order вводится позиция = sourceIndex последней
обработанной строки; следующая активная — первая нерешённая строго после неё
с обёрткой к самой ранней. order перестал быть состоянием: очередь теперь
производная от строк и всегда идёт по документу.

Инвариант PR-B «ошибка PATCH → строка становится следующей» позицией не
выражается: commitFailed пиннит оператора на текущей строке, и её committed
перезапишет позицию на «после себя», уронив откатившуюся в хвост. Поэтому у
неё отдельный приоритетный слот, гаснущий сам при выходе строки из pending.

Пин-тест на «уход в хвост после N» переписан на проверку эффекта (какая
строка стала активной), а не внутреннего порядка массива."
```

---

### Task 4: Кликабельные строки полосы окружения

**Files:**

- Modify: `frontend/src/pages/estimate/ContextStrip.tsx` (проп `onNavigate`, рендер строки)
- Test: `frontend/src/pages/estimate/ContextStrip.test.tsx`

**Interfaces:**

- Consumes: ничего из предыдущих задач — колбэк приходит пропом, поэтому задача независима от Task 3.
- Produces: проп `onNavigate?: (rowNumber: number) => void` у `ContextStrip` — Task 5 передаёт в него `queue.navigateTo`.

**Регресс-гвард.** Тест «строки полосы не несут словаря кандидата» (`ContextStrip.test.tsx:302`) запрещает словарь кандидата (`rounded`, `border-border`), а не интерактивность. Выбранный аффорданс — hover-тинт грида + `cursor-pointer` — его не нарушает, гвард должен пройти **без правок**. Если резет-классы `<button>` его случайно заденут, гвард можно поправить, но беречь его **намерение** (полоса ≠ кандидаты: без `rounded`/`border-border`/рамки кандидата), а не букву.

- [ ] **Step 1: Написать падающие тесты**

В начало `frontend/src/pages/estimate/ContextStrip.test.tsx` дописать `vi` в существующий импорт из `vitest` и добавить импорт `userEvent`:

```tsx
import { describe, expect, it, vi } from "vitest"
import userEvent from "@testing-library/user-event"
```

Добавить в конец файла:

```tsx
describe("ContextStrip: навигация по клику", () => {
  it("клик по решаемой строке зовёт onNavigate с её row_number", async () => {
    const onNavigate = vi.fn()
    render(
      <ContextStrip
        state={initReview("x", ROWS)}
        activeRowNumber={3}
        onNavigate={onNavigate}
      />
    )
    await userEvent.click(screen.getByText("Строка 2"))
    expect(onNavigate).toHaveBeenCalledWith(2)
  })

  it("excluded/pending не кликабельны: не button, onNavigate не зовётся", async () => {
    const onNavigate = vi.fn()
    render(
      <ContextStrip
        state={initReview("x", ROWS)}
        activeRowNumber={3}
        onNavigate={onNavigate}
      />
    )
    const excluded = screen.getByText("Орг-заголовок").closest("[data-row]")!
    expect(excluded.tagName).toBe("DIV")
    await userEvent.click(excluded)
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it("активная строка не кликабельна (клик по себе — no-op)", () => {
    render(
      <ContextStrip
        state={initReview("x", ROWS)}
        activeRowNumber={3}
        onNavigate={vi.fn()}
      />
    )
    const active = screen.getByText("Строка 3").closest("[data-row]")!
    expect(active.tagName).toBe("DIV")
  })

  it("кликабельная строка — button с аффордансом грида, без словаря кандидата", () => {
    render(
      <ContextStrip
        state={initReview("x", ROWS)}
        activeRowNumber={3}
        onNavigate={vi.fn()}
      />
    )
    const clickable = screen.getByText("Строка 2").closest("[data-row]")!
    expect(clickable.tagName).toBe("BUTTON")
    expect(clickable.className).toContain("hover:bg-muted/50")
    expect(clickable.className).toContain("cursor-pointer")
    // видимый focus-ring — требование a11y из спеки
    expect(clickable.className).toContain("focus-visible:ring-3")
    // роль полосы сохранена: не кандидат
    expect(clickable.className).not.toContain("rounded")
    expect(clickable.className).not.toContain("border-border")
  })

  it("без onNavigate строки остаются неинтерактивными (обратная совместимость)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const other = screen.getByText("Строка 2").closest("[data-row]")!
    expect(other.tagName).toBe("DIV")
  })
})
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `cd frontend && npx vitest run src/pages/estimate/ContextStrip.test.tsx`

Expected: FAIL — TS-ошибка о неизвестном пропе `onNavigate`; `clickable.tagName` приходит `DIV` вместо `BUTTON`; `onNavigate` не вызывается.

- [ ] **Step 3: Добавить проп**

В `frontend/src/pages/estimate/ContextStrip.tsx` расширить сигнатуру:

```tsx
export function ContextStrip({
  state,
  activeRowNumber,
  onNavigate,
}: {
  state: ReviewState
  activeRowNumber: number
  // Скраббер (спека фичи 2): клик по строке делает её активной. Проп
  // опциональный — без него полоса остаётся чистой справкой, как была.
  onNavigate?: (rowNumber: number) => void
}) {
```

- [ ] **Step 4: Развести кликабельную и статичную строку**

Внутри `win.map(...)`, после `const rs = rightSide(state, r)`, добавить:

```tsx
        const isActive = r.row_number === activeRowNumber
        // Кликабельны те же строки, что в гриде: excluded/pending — контекст,
        // не решения. Активная не кликабельна: клик по себе — no-op.
        const clickable = onNavigate !== undefined && !muted && !isActive
        const rowClass = cn(
          "flex w-full items-center gap-2 border-l-2 border-transparent px-3 py-1.5 text-left",
          isActive &&
            "border-primary bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]",
          muted && "opacity-60",
          openers[g] && "font-medium",
          // Аффорданс — словарь ГРИДА, не рамка кандидата: в покое полоса
          // остаётся утопленной справкой, интерактивность проявляется только
          // на hover (иначе вернулась бы проблема «полоса читается как
          // кандидаты», этап 3.6). focus-visible — по конвенции ui/button.
          clickable &&
            "cursor-pointer outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
        )
        const inner = (
          <>
            <span className="font-mono text-muted-foreground">
              {r.section_code}
            </span>
            <span
              className={cn(
                "truncate",
                // Вторая ось открывашки (спека §2 решение #6): опускаем фон —
                // рядовой сосед (не активная, не открывашка) приглушается, а
                // открывашка остаётся на полном тоне + font-medium.
                // excluded/pending исключены: у них своя ось «тихо» —
                // opacity-60; тон был бы двойным кодированием.
                !openers[g] && !isActive && !muted && "text-[var(--ds-text-2)]"
              )}
            >
              {r.source_name}
            </span>
            {isActive ? (
              // статус активной дублировал бы решаемое прямо сейчас (спека 3.5 §2)
              <ArrowLeft
                aria-label={t("review.youAreHere")}
                className="ml-auto size-3 shrink-0 text-primary"
              />
            ) : (
              <span
                title={rs.title}
                className={cn(
                  "ml-auto shrink-0 text-muted-foreground",
                  rs.mono && "font-mono"
                )}
              >
                → {t(rs.text)}
              </span>
            )}
          </>
        )
```

Затем заменить существующий блок строки (`<div data-row ...>…</div>` со всем содержимым) на развилку тега:

```tsx
            {clickable ? (
              <button
                type="button"
                data-row
                data-opener={openers[g] || undefined}
                onClick={() => onNavigate(r.row_number)}
                className={rowClass}
              >
                {inner}
              </button>
            ) : (
              <div
                data-row
                data-opener={openers[g] || undefined}
                data-active={isActive || undefined}
                className={rowClass}
              >
                {inner}
              </div>
            )}
```

`data-active` остаётся только на `<div>`: активная строка никогда не кликабельна, так что на `<button>` этот атрибут недостижим.

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `cd frontend && npx vitest run src/pages/estimate/ContextStrip.test.tsx`

Expected: PASS, включая нетронутый регресс-гвард «строки полосы не несут словаря кандидата» и гвард утопленной поверхности.

Если гвард упал на подстроке `rounded` — значит она пришла из резет-классов кнопки. Убери её из `rowClass`, не из гварда.

- [ ] **Step 6: Прогнать typecheck и весь фронт**

Run: `cd frontend && npx tsc -b && npx vitest run`

Expected: чисто и зелено.

- [ ] **Step 7: Отформатировать и закоммитить**

```bash
cd frontend && npx prettier --write src/pages/estimate/ContextStrip.tsx src/pages/estimate/ContextStrip.test.tsx
cd .. && git add frontend/src/pages/estimate/ContextStrip.tsx frontend/src/pages/estimate/ContextStrip.test.tsx
git commit -m "feat(review): строки полосы окружения кликабельны

Оператор видел соседа, требующего внимания, и не мог к нему перейти. Теперь
решаемые строки — настоящие button (фокус, Enter/Space, focus-ring), а
excluded/pending остаются неинтерактивным контекстом.

Аффорданс взят из словаря грида (hover-тинт + cursor-pointer), а не из рамки
кандидата: в покое полоса остаётся утопленной справкой, поэтому проблема
«полоса читается как кандидаты» (этап 3.6) не возвращается — регресс-гвард
роли проходит без правок.

Роль поверхности осознанно эволюционирует: «справка» → «справка + навигация»."
```

---

### Task 5: Подключить навигацию на экране ревью

**Files:**

- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx:290-291` (передать `onNavigate` в `ContextStrip`)
- Test: `frontend/src/pages/estimate/ReviewScreen.test.tsx`

**Interfaces:**

- Consumes: `ReviewQueue.navigateTo` (Task 3), проп `ContextStrip.onNavigate` (Task 4).
- Produces: ничего.

**Важно — упрощение против спеки.** Спека предписывает проброс `ReviewScreen → ReviewCard (проп рядом с contextStrip) → ContextStrip`. Он не нужен: `ContextStrip` **инстанцируется прямо в `ReviewScreen`** и попадает в карточку уже готовым `ReactNode`. Колбэк вешается там же, `ReviewCard` для Фичи 2 не правится вовсе — иначе карточка получила бы знание о навигации ревью, что противоречит её собственному инварианту (комментарий к пропу `contextStrip` в `ReviewCard.tsx`: «карточка не знает о ревью-стейте»).

- [ ] **Step 1: Написать падающий тест**

Добавить в `frontend/src/pages/estimate/ReviewScreen.test.tsx` новый `describe` в конец файла. Используются готовые хелперы файла: `Wrap`, `ROWS`, `workText` (последний ищет текст работы карточки, исключая совпадения внутри `[data-row]` — то есть внутри полосы; без него тест был бы ложноположительным, о чём предупреждает комментарий в шапке файла).

Напоминание про фикстуру `ROWS` этого файла: `Орг-заголовок` (excluded, si=0), `Уверенная` (confident, si=1), `Спорная А` (needs_review, si=2), `Спорная Б` (needs_review, si=3). Активная по умолчанию — «Спорная А», окно полосы ±2 покрывает все четыре строки.

```tsx
describe("скраббер: навигация по полосе окружения", () => {
  it("клик по соседу делает его активной строкой карточки", async () => {
    render(<Wrap rows={ROWS} />)
    expect(workText("Спорная А")).toBeInTheDocument()
    // «Спорная Б» пока присутствует ТОЛЬКО в полосе окружения
    await userEvent.click(screen.getByText("Спорная Б"))
    expect(workText("Спорная Б")).toBeInTheDocument()
  })

  it("клик по excluded-строке полосы активную не меняет", async () => {
    render(<Wrap rows={ROWS} />)
    await userEvent.click(screen.getByText("Орг-заголовок"))
    expect(workText("Спорная А")).toBeInTheDocument()
  })

  it("ad-hoc сосед (confident) открывается из полосы", async () => {
    render(<Wrap rows={ROWS} />)
    await userEvent.click(screen.getByText("Уверенная"))
    expect(workText("Уверенная")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить тест и убедиться, что падает**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewScreen.test.tsx -t "скраббер"`

Expected: FAIL на первом и третьем тестах — `текст работы карточки "Спорная Б" не найден` (клик по `div` ничего не делает: колбэк не передан). Второй тест (excluded не меняет активную) проходит сразу — он защитный.

- [ ] **Step 3: Передать колбэк**

В `frontend/src/pages/estimate/ReviewScreen.tsx` заменить:

```tsx
            contextStrip={
              <ContextStrip state={state} activeRowNumber={active.row_number} />
            }
```

на:

```tsx
            contextStrip={
              // onNavigate вешается ЗДЕСЬ, а не пробрасывается через
              // ReviewCard: полоса инстанцируется в этом файле и попадает в
              // карточку готовым узлом. Карточка о навигации ревью не знает —
              // её инвариант (см. проп contextStrip в ReviewCard) цел.
              <ContextStrip
                state={state}
                activeRowNumber={active.row_number}
                onNavigate={queue.navigateTo}
              />
            }
```

**Почему без гейта по `readOnly`.** Клавиши гейтятся им потому, что они меняют данные (`commit`). Навигация по полосе ничего не меняет — она переставляет точку просмотра, что в режиме только-чтения так же уместно, как клик по строке грида. Спека дополнительного ограничения не вводит, и вводить его тут значило бы отнять безвредную возможность.

- [ ] **Step 4: Запустить тест и убедиться, что проходит**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewScreen.test.tsx`

Expected: PASS.

- [ ] **Step 5: Прогнать полную верификацию**

Run: `cd frontend && npx tsc -b && npx vitest run && npx eslint . && npx prettier --check .`

Expected: всё чисто и зелено.

- [ ] **Step 6: Закоммитить**

```bash
cd frontend && npx prettier --write src/pages/estimate/ReviewScreen.tsx src/pages/estimate/ReviewScreen.test.tsx
cd .. && git add frontend/src/pages/estimate/ReviewScreen.tsx frontend/src/pages/estimate/ReviewScreen.test.tsx
git commit -m "feat(review): подключить скраббер-навигацию на экране ревью

ContextStrip получает queue.navigateTo прямо в ReviewScreen, где он и
инстанцируется. Проброс через ReviewCard (как предлагала спека) не нужен и
нарушил бы её инвариант «карточка не знает о ревью-стейте».

Гейта по readOnly нет сознательно: клавиши гейтятся им потому, что меняют
данные, а навигация лишь переставляет точку просмотра."
```

---

## Финальная проверка ветки

- [ ] `cd frontend && npx tsc -b` — чисто
- [ ] `cd frontend && npx vitest run` — все зелёные
- [ ] `just lint` из корня — ruff + eslint + prettier `--check`
- [ ] Devlog по конвенции проекта: `docs/devlog/YYYY-MM-DD-review-card-choice-and-scrubber.md` — что сделано, затронутые файлы, решения и нюансы, что осталось. Обязательно зафиксировать два отхода от спеки: приоритетный слот вместо «позиции перед строкой» в `commitFailed` и отказ от проброса `onNavigate` через `ReviewCard`.
- [ ] Ручная проверка в браузере (`just dev-back` + `just dev-front`): override-строка, открытая из грида, показывает блок «Ваш выбор»; `Enter` на ней ничего не перезаписывает; клик по соседу в полосе переносит карточку; после решения поток идёт вперёд от новой позиции; пропущенная через `N` строка возвращается в конце прохода
