# Правка «уверенных» позиций на экране ревью — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Любая строка ревью раскрывается кликом и допускает исправление: другой кандидат, ручной поиск, «без пары», плюс возврат к исходной рекомендации одним кликом.

**Architecture:** Frontend-only (спека [2026-07-02-editable-confident-rows-design.md](../specs/2026-07-02-editable-confident-rows-design.md)): `ReviewRow` теряет особый случай «confident нераскрываем», получает синтетическую карточку «текущая рекомендация» (рисуется, когда `matched_code` отсутствует в `candidates` — кейс фонд-хита) и всюду доступную кнопку «Оставить без пары». Откат держится на бэкенд-инварианте «ревью не мутирует AI-снимок `matched_*`» — его закрепляем pinning-тестом. Редьюсер `reviewState` и бэкенд-код не меняются.

**Tech Stack:** React + TypeScript (vitest + Testing Library), pytest (fakes, без БД/AI).

## Global Constraints

- Фронт: eslint строгий + Prettier (`printWidth 80`, `endOfLine lf`); typecheck = `npm run typecheck` (это `tsc -b`; `tsc --noEmit` без `-b` ничего не проверяет).
- Бэк: ruff (line-length 100), type hints, `from __future__ import annotations`; запуск только `uv run` из `backend/`.
- Юнит-тесты бэка не ходят в БД/AI — фейки портов (`tests/fakes.py`) + `dependency_overrides`.
- Файлы в LF. Коммиты — Conventional Commits, по одному на задачу.
- shadcn-компоненты (`src/components/ui/`) не править (в этой фиче не нужны).
- Windows PowerShell 5.1: в командах justfile `;`, не `&&`. Команды ниже даны для Bash-тула (`&&` допустим).

---

### Task 1: Бэкенд — pinning-тест иммутабельности AI-снимка при ревью

UI-откат (Task 2) опирается на инвариант «`pick`/`reject` не трогают `matched_*`»
(спека §2). Инвариант держится реализацией (`save_review_decision` пишет только
`review_status`/`final_*`), но ни один тест его явно не проверяет. Закрепляем.
Тест должен пройти сразу — это regression pin, не новая функциональность.

**Files:**
- Modify: `backend/tests/test_estimate_review.py` (добавить тест в конец файла)

**Interfaces:**
- Consumes: фикстуры `client`/`auth_headers`/`estimate_repo`/`seed_estimate` из `backend/tests/conftest.py`, хелпер `_match` этого же файла (строки 6–12).
- Produces: ничего для других задач (страж).

- [ ] **Step 1: Написать pinning-тест**

Добавить в конец `backend/tests/test_estimate_review.py`:

```python
def test_pick_and_reject_keep_ai_snapshot(client, auth_headers, estimate_repo, seed_estimate):
    """Два инварианта из спеки editable-confident-rows §2:
    1) ревью пишет только ось review_status/final_* — AI-снимок matched_*/candidates
       иммутабелен (на этом держится откат «вернуть рекомендацию» на фронте);
    2) pick исходной рекомендации нормализуется в confirmed, не overridden
       (откат confident-строки через клик по топ-3 не застревает в «Ручной выбор»)."""
    eid, nid = seed_estimate
    _match(estimate_repo, nid, EstimateRowStatus.NEEDS_REVIEW, mid=7, code="2.1",
           name="Статья", score=0.7,
           cands=[MatchCandidate(7, "2.1", "Статья", 0.7), MatchCandidate(9, "3.2", "Иная", 0.5)])

    picked = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 9},
    )
    assert picked.status_code == 200
    assert picked.json()["review_status"] == "overridden"
    assert picked.json()["matched_article_id"] == 7  # снимок не мутировал
    assert picked.json()["matched_code"] == "2.1"

    # снимок иммутабелен целиком: candidates тоже не тронуты
    assert [c["id"] for c in picked.json()["candidates"]] == [7, 9]

    rejected = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "reject"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["matched_article_id"] == 7
    assert rejected.json()["matched_code"] == "2.1"

    # нормализация (_pick): выбор исходной рекомендации = confirmed, не overridden —
    # поэтому «откат» у confident-строки (клик по исходному кандидату в топ-3)
    # не застревает в «Ручной выбор» (спека §2)
    restored = client.patch(
        f"/api/estimates/{eid}/rows/{nid}/review",
        headers=auth_headers, json={"action": "pick", "article_id": 7},
    )
    assert restored.status_code == 200
    assert restored.json()["review_status"] == "confirmed"
    assert restored.json()["final_code"] == "2.1"
```

Примечание: спека предлагала доассертить в `test_pick_candidate_overridden`,
но существующий reject-тест сидит на `NO_MATCH`-строке без `matched_*` —
отдельный тест с одной строкой на оба действия чище и читается как страж.

- [ ] **Step 2: Прогнать — ожидается PASS (pin существующего поведения)**

Run: `cd backend && uv run pytest tests/test_estimate_review.py -v`
Expected: все тесты PASS, включая новый `test_pick_and_reject_keep_ai_snapshot`.
Если новый тест УПАЛ — стоп: инвариант, на который рассчитана фича, не выполняется; вернуться к спеке, не продолжать.

- [ ] **Step 3: Ruff и коммит**

Run: `cd backend && uv run ruff check tests/test_estimate_review.py`
Expected: `All checks passed!`

```bash
git add backend/tests/test_estimate_review.py
git commit -m "test(review): закрепить инвариант — pick/reject не мутируют AI-снимок matched_*"
```

---

### Task 2: `ReviewRow` + `ReviewScreen` — раскрываемость всех строк, карточка рекомендации, «без пары» везде

Ядро фичи. Новый проп `onConfirmRecommendation` типизирован обязательным,
поэтому `ReviewRow`, `ReviewScreen` и тесты меняются в одной задаче (иначе
typecheck красный между коммитами).

**Files:**
- Modify: `frontend/src/pages/estimate/ReviewRow.tsx`
- Modify: `frontend/src/pages/estimate/ReviewScreen.tsx:181-212` (маппинг строк)
- Test: `frontend/src/pages/estimate/ReviewRow.test.tsx`

**Interfaces:**
- Consumes: `MatchRow`/`Candidate`/`Decision` из `@/lib/types`; `requiresDecision`/`statusLabel` из `@/lib/reviewState`; экшен редьюсера `confirmArbiter` и колбэк `onReview(rowNumber, "confirm")` (оба существуют).
- Produces: проп `onConfirmRecommendation: () => void` в `ReviewRowProps` (обязательный). Семантика: «вернуть/подтвердить исходную рекомендацию AI-снимка».

- [ ] **Step 1: Обновить существующие тесты и написать новые (падающие)**

В `frontend/src/pages/estimate/ReviewRow.test.tsx`:

1. Во **все шесть** существующих `render(...)` добавить проп
   `onConfirmRecommendation={vi.fn()}` (рядом с `onConfirmNoMatch`).
2. Расширить импорт RTL: `import { render, screen, within } from "@testing-library/react"`.
3. После существующих кейсов добавить:

```tsx
const fundRowNoCands = { ...fundRow, candidates: [] }

describe("ReviewRow: правка уверенных позиций", () => {
  it("уверенная строка кликабельна: клик зовёт onToggle", async () => {
    const onToggle = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={confidentRow}
          decision={fundDecision}
          expanded={false}
          onToggle={onToggle}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    await userEvent.click(screen.getByText(confidentRow.source_name))
    expect(onToggle).toHaveBeenCalled()
  })

  it("раскрытая уверенная строка даёт кандидатов и ручной поиск", () => {
    render(
      tableWrap(
        <ReviewRow
          row={confidentRow}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    // у confident matched-кандидат уже в candidates → синтетической карточки НЕТ
    // (прямой ассерт по подписи, не по количеству кнопок — устойчив к фикстуре)
    expect(
      screen.queryByText(/рекомендация ai|из фонда/i)
    ).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /СМР-/ })).toHaveLength(1)
    expect(
      screen.getByPlaceholderText(/искать в справочнике/i)
    ).toBeInTheDocument()
  })

  it("фонд-строка без кандидатов рисует карточку рекомендации; клик → onConfirmRecommendation", async () => {
    const onConfirmRec = vi.fn()
    const onPick = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={fundRowNoCands}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={onPick}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={onConfirmRec}
        />
      )
    )
    // спека §Тесты кейс 4: у карточки нет score (0.96 — реальный score фикстуры)
    expect(
      screen.queryByText(fundRowNoCands.score.toFixed(2))
    ).not.toBeInTheDocument()
    const card = screen.getByRole("button", {
      name: new RegExp(fundRowNoCands.matched_code!),
    })
    // спека §Тесты кейс 4: метка происхождения «Из фонда» ВНУТРИ карточки
    // (в статус-ячейке строки она тоже есть — поэтому within, не screen)
    expect(within(card).getByText(/из фонда/i)).toBeInTheDocument()
    await userEvent.click(card)
    expect(onConfirmRec).toHaveBeenCalled()
    expect(onPick).not.toHaveBeenCalled()
  })

  it("карточка рекомендации не-фонд строки подписана «Рекомендация AI»", () => {
    render(
      tableWrap(
        <ReviewRow
          row={{ ...confidentRow, candidates: [] }}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    expect(screen.getByText(/рекомендация ai/i)).toBeInTheDocument()
  })

  // спека §Тесты кейс 3: «без пары» доступна и у confident, и у matched_fund
  it.each([
    ["confident", confidentRow],
    ["matched_fund", fundRow],
  ])(
    "«Оставить без пары» доступна на раскрытой %s-строке и зовёт onConfirmNoMatch",
    async (_status, row) => {
      const onNoMatch = vi.fn()
      render(
        tableWrap(
          <ReviewRow
            row={row}
            decision={fundDecision}
            expanded
            onToggle={vi.fn()}
            onPickCandidate={vi.fn()}
            onManualPick={vi.fn()}
            onConfirmNoMatch={onNoMatch}
            onConfirmRecommendation={vi.fn()}
          />
        )
      )
      await userEvent.click(
        screen.getByRole("button", { name: /оставить без пары/i })
      )
      expect(onNoMatch).toHaveBeenCalled()
    }
  )

  it("после override карточка показывает исходную рекомендацию (снимок иммутабелен) и откатывает через confirm", async () => {
    // регрессия по спеке §Тесты кейс 5: оператор увёл фонд-хит на другую статью —
    // matched_* строки не изменились, карточка продолжает предлагать исходную пару
    const onConfirmRec = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={fundRowNoCands}
          decision={{
            kind: "confirmed",
            code: "СМР-99-999",
            name: "Другая статья",
            manual: true,
          }}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={onConfirmRec}
        />
      )
    )
    const card = screen.getByRole("button", {
      name: new RegExp(fundRowNoCands.matched_code!),
    })
    await userEvent.click(card)
    expect(onConfirmRec).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Прогнать — новые тесты падают, старые проходят**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewRow.test.tsx`
Expected: старые 6 тестов PASS (лишний проп в рантайме безвреден, vitest типы не проверяет), все новые FAIL — «уверенная строка кликабельна» (onToggle не зовётся: строка нераскрываема), панель у confident не рендерится, карточка рекомендации не найдена, «Оставить без пары» отсутствует.

- [ ] **Step 3: Реализовать `ReviewRow.tsx`**

Изменения по блокам (остальной файл не трогать):

Проп в интерфейс (после `onConfirmNoMatch`):

```tsx
interface ReviewRowProps {
  row: MatchRow
  decision: Decision
  expanded: boolean
  onToggle: () => void
  onPickCandidate: (code: string) => void
  onManualPick: (c: Candidate) => void
  onConfirmNoMatch: () => void
  /** вернуть/подтвердить исходную рекомендацию AI-снимка (действие confirm) */
  onConfirmRecommendation: () => void
}
```

Деструктуризация в сигнатуре компонента — добавить `onConfirmRecommendation`.

Блок раскрываемости (строки 37–40) — особый случай уходит:

```tsx
const flagged = requiresDecision(row) // warning-рамка: только реально спорные
// любая строка раскрываема и правима (спека editable-confident-rows §1);
// warning-рамка при этом остаётся только у требующих решения
const expandable = true
```

(Переменную можно убрать вовсе; если убираешь — замени её использования ниже:
`tr` всегда кликабелен, шеврон всегда рисуется в non-no_match ветке, панель —
`{expanded && (...)}`.)

Синтетическая карточка + условие — перед `row.candidates.map(...)` в раскрытой
панели. Карточка рисуется, когда рекомендация снимка не представлена среди
кандидатов (фонд-хит; у confident/needs_review matched всегда в топ-3):

```tsx
{row.matched_code &&
  row.matched_name &&
  !row.candidates.some((c) => c.article_code === row.matched_code) && (
    <button
      onClick={(e) => {
        e.stopPropagation()
        onConfirmRecommendation()
      }}
      className={
        "mb-1.5 flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm " +
        (chosenCode === row.matched_code
          ? "border-primary shadow-[var(--ds-glow-violet)]"
          : "border-border")
      }
    >
      <span className="font-mono text-xs text-muted-foreground">
        {row.matched_code}
      </span>
      <span className="flex-1">{row.matched_name}</span>
      <span className="text-xs text-muted-foreground">
        {row.status === "matched_fund" ? (
          <>
            <Database className="mr-1 inline size-3" />
            Из фонда
          </>
        ) : (
          "Рекомендация AI"
        )}
      </span>
    </button>
  )}
```

Кнопка «Оставить без пары» (строки 171–181) — убрать условие
`row.status === "no_match" &&`, кнопка рисуется в любой раскрытой панели
(reject валиден для любой сматченной строки, спека §3):

```tsx
<button
  onClick={(e) => {
    e.stopPropagation()
    onConfirmNoMatch()
  }}
  className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
>
  Оставить без пары
</button>
```

- [ ] **Step 4: Прокинуть проп в `ReviewScreen.tsx`**

В маппинге `<ReviewRow ...>` (после `onConfirmNoMatch`):

```tsx
onConfirmRecommendation={() => {
  dispatch({ type: "confirmArbiter", row: row.row_number })
  onReview?.(row.row_number, "confirm")
  gotoNext()
}}
```

(`confirmArbiter` берёт `matched_code`/`matched_name` из строки-снимка — ровно
исходная рекомендация; `onReview "confirm"` на бэке использует
`matched_article_id`, `article_id` не нужен. `gotoNext()` — симметрично трём
существующим обработчикам, которые зовут его безусловно, в т.ч. на фонд-хитах
вне клавиатурной очереди: для строки вне очереди `findIndex` даёт `-1` →
фокус уходит на первую нерешённую спорную строку — существующее поведение.)

- [ ] **Step 5: Прогнать тесты компонента**

Run: `cd frontend && npx vitest run src/pages/estimate/ReviewRow.test.tsx`
Expected: PASS все 13 — 6 старых + 7 новых (5 `it` + 2 кейса `it.each`).

- [ ] **Step 6: Смежные сьюты и typecheck**

Run: `cd frontend && npx vitest run src/pages/estimate/ && npm run typecheck`
Expected: PASS (ReviewScreen.test/EstimateFlow.test не мокают ReviewRow-пропсы напрямую, но проверяем; typecheck зелёный).
Если ReviewScreen.test упал на отсутствии пропа — он рендерит настоящий `ReviewScreen`, который проп уже прокидывает; падение = ошибка в Step 4.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/pages/estimate/ReviewRow.tsx frontend/src/pages/estimate/ReviewScreen.tsx frontend/src/pages/estimate/ReviewRow.test.tsx
git commit -m "feat(review): любая строка раскрываема — правка уверенных и фонд-позиций, карточка «вернуть рекомендацию», «без пары» везде"
```

---

### Task 3: `reviewState` — pinning-тест инвариантности прогресса

Редьюсер не меняется; фиксируем, что правка не требующих решения строк не
двигает счётчик «проверено X из Y» (спека §Тесты кейс 6). Ожидается PASS сразу.

**Files:**
- Modify: `frontend/src/lib/reviewState.test.ts` (добавить тест в describe)

**Interfaces:**
- Consumes: `reviewReducer`, `progress`, `initReview` из `@/lib/reviewState`; хелперы `base()`/`rowNum()` этого же файла.
- Produces: ничего (страж).

- [ ] **Step 1: Добавить тест**

В конец `describe("reviewState", ...)`:

```ts
it("pick/reject на confident-строке не двигает progress() (спека editable-confident-rows §4)", () => {
  const r = rowNum("confident")
  const total0 = progress(base()).total
  const picked = reviewReducer(base(), {
    type: "manualPick",
    row: r,
    candidate: { id: null, article_code: "СМР-99-999", name: "Ручная", score: 0 },
  })
  expect(progress(picked)).toEqual({ reviewed: 0, total: total0 })
  const rejected = reviewReducer(base(), { type: "confirmNoMatch", row: r })
  expect(progress(rejected)).toEqual({ reviewed: 0, total: total0 })
})
```

- [ ] **Step 2: Прогнать — ожидается PASS (pin)**

Run: `cd frontend && npx vitest run src/lib/reviewState.test.ts`
Expected: PASS. Если упал — `requiresDecision`/`progress` ведут себя не по спеке, вернуться к спеке.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/lib/reviewState.test.ts
git commit -m "test(review): progress() инвариантен к правкам confident-строк"
```

---

### Task 4: Полная верификация + devlog

**Files:**
- Create: `docs/devlog/2026-07-02-editable-confident-rows.md`

**Interfaces:** нет (финализация).

- [ ] **Step 1: Полный прогон**

Run из корня: `just lint && just test`
Expected: ruff/eslint/prettier чисто; pytest и vitest зелёные.
Если prettier ругается на новые файлы — `just fmt` и перепрогнать.

- [ ] **Step 2: Написать devlog**

`docs/devlog/2026-07-02-editable-confident-rows.md`:

```markdown
# 2026-07-02 — Правка «уверенных» позиций на экране ревью

**Ветка:** `feat/editable-confident-rows`
**Спека:** [../superpowers/specs/2026-07-02-editable-confident-rows-design.md](../superpowers/specs/2026-07-02-editable-confident-rows-design.md)

## Что сделано

Frontend-only: снят особый случай «confident-строка нераскрываема» —
любая строка ревью раскрывается кликом (кандидаты + ручной поиск + «Оставить
без пары»). Для строк, у которых рекомендация AI-снимка не входит в
`candidates` (фонд-хиты), первой рисуется синтетическая карточка «текущая
рекомендация» — клик по ней откатывает правку через действие `confirm`
(бэкенд берёт нетронутый `matched_article_id`). Новый проп
`ReviewRow.onConfirmRecommendation`, прокинут из `ReviewScreen`
(`confirmArbiter` + `onReview "confirm"`).

Бэкенд-код не менялся. Инвариант, на котором держится откат («ревью пишет
только ось `review_status`/`final_*`, снимок `matched_*` иммутабелен»),
закреплён pinning-тестом `test_pick_and_reject_keep_ai_snapshot`; на фронте —
регрессионный тест карточки после override и pinning инвариантности
`progress()`.

## Сознательно вне объёма

Reject фонд-хита не гасит запись фонда — оператор будет отвергать тот же
матч в каждой новой смете. Заведено в
[TECH_DEBT](../TECH_DEBT.md#-золотой-фонд-reject-фонд-хита-не-гасит-запись-фонда).
```

- [ ] **Step 3: Коммит**

```bash
git add docs/devlog/2026-07-02-editable-confident-rows.md
git commit -m "docs(devlog): правка уверенных позиций на экране ревью"
```
