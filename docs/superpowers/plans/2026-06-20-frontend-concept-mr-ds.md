# Фронтенд-концепт под MR Design System — план реализации (frontend-only, на моках)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перекроить фронтенд CIW под тёмную MR Design System и собрать все ключевые экраны (вход → старт → обработка → проверка → выгрузка + справочник) на моках/заглушках API, чтобы концепт можно было пройти руками целиком, не дожидаясь бэкенда.

**Architecture:** Re-skin через слой CSS-переменных (значения MR DS подставляются в shadcn-токены `--background/--primary/...`, тёмная тема — постоянная), весь поток данных идёт через **мок-API** (`src/lib/mock/`) на фикстурах из реального файла. Состояние ревью — чистый reducer; восстановление сессии — `sessionStorage`. Реальный бэкенд позже подключается заменой одного модуля `api`.

**Tech Stack:** React 19, TypeScript, Vite 8, Tailwind v4 (`@theme`/CSS-vars), shadcn/ui (radix-ui, cva), lucide-react, vitest + React Testing Library + user-event.

## Global Constraints

- **Только фронтенд, только моки.** Никаких изменений в `backend/`. Все сетевые вызовы — через `src/lib/mock/`. Реальные эндпоинты (выгрузка `.xlsx`, поиск статьи, rationale) — вне этого плана (бэкенд-гейты из спеки).
- **Тёмная тема MR DS — постоянная.** Значения берутся из `temp/design_handoff_mr_design_system/tokens/tokens.css` (источник правды). Акцент `#754AE8`, фон `#0A0814`, success `#82D6CC`, warning `#BD9375`, danger `#E8657A`. Радиусы: контролы 4px, карточки 8–10px.
- **Шрифты:** Grtsk Giga (заголовки/числа), Suisse Intl (текст). Самохостинг — файлы кладём в `frontend/public/fonts/`.
- **shadcn-компоненты в `src/components/ui/` — вендорные, не править** (CLAUDE.md). Перекраска — только через CSS-переменные в `index.css`.
- **Импорты через alias `@/`. Иконки — `lucide-react`.** TypeScript строгий, eslint строгий. Запускать `npm run typecheck` и `npm run lint` перед коммитом.
- **Тесты:** vitest + RTL, окружение jsdom уже настроено (`vitest.config.ts`, `src/test/setup.ts`). Импортировать `{ describe, it, expect }` из `vitest` явно (как в существующих тестах). В реальную сеть тесты не ходят — мок-API детерминирован.
- **Каждая задача завершается:** `npm run typecheck` (PASS) + `npm run test` (PASS) + коммит. Команды запускать из `frontend/`.
- **Язык интерфейса — русский** (как в текущем коде).

## Структура файлов

Создаётся (frontend/src, если не указано иное):
- `public/fonts/*.{otf,ttf}` — 5 файлов шрифтов (копия из temp)
- `index.css` — **переписываем**: токены MR DS + @font-face + тёмная тема по умолчанию
- `lib/types.ts` — доменные типы UI: `MatchStatus`, `Candidate`, `MatchRow`, `Decision`, `ReviewState`
- `lib/mock/fixtures.ts` — фикстуры: 15 строк СМР из реального файла, справочник, кандидаты, rationale
- `lib/mock/api.ts` — мок-API: `matchEstimate`, `searchArticles`, `exportEstimateCsv`, `downloadCsv`
- `lib/session.ts` — сохранение/восстановление/очистка ревью в `sessionStorage`
- `lib/reviewState.ts` — reducer ревью + селекторы (`initReview`, `reviewReducer`, `progress`, `filteredRows`, `decisionFor`, `statusLabel`)
- `lib/useReviewKeyboard.ts` — хук клавиатурного лупа (1·2·3 / Enter / n)
- `components/auth/LoginScreen.tsx`, `components/auth/AuthGate.tsx` — вход (мок)
- `components/AppShell.tsx` — шапка MR DS (лого, вкладки, пользователь)
- `pages/estimate/StartScreen.tsx` — dropzone
- `pages/estimate/ProcessingScreen.tsx` — прогресс + ETA после поиска
- `pages/estimate/ReviewRow.tsx` — раскрывающаяся строка + кандидаты + rationale + ручной поиск
- `pages/estimate/ReviewScreen.tsx` — главный экран (таблица, фильтры, прогресс, выгрузка)
- `pages/estimate/DoneScreen.tsx` — итог + выгрузка + новая смета
- `pages/estimate/EstimateFlow.tsx` — оркестратор потока + восстановление сессии + guard
- `pages/ArticlesPage.tsx` — **переписываем** под мок-API и MR DS
- `App.tsx` — **переписываем**: AuthGate + AppShell + вкладки (поток сметы / справочник)

Удаляется/замещается: `pages/EstimatePage.tsx` и `pages/EstimatePage.test.tsx` (старый одно-экранный поток заменяется `EstimateFlow`); `lib/api.ts` остаётся как тип-референс, но UI ходит в `lib/mock/api.ts`.

---

### Task 1: Тема MR DS + шрифты (фундамент визуала)

**Files:**
- Create: `frontend/public/fonts/` (копия 5 файлов из `temp/design_handoff_mr_design_system/fonts/`)
- Modify: `frontend/src/index.css` (переписать токены/тему/шрифты)
- Modify: `frontend/src/main.tsx` (тёмная тема по умолчанию)

**Interfaces:**
- Produces: CSS-переменные MR DS подставлены в shadcn-токены; тёмная тема активна всегда; шрифты Giga/Suisse доступны. Утилит-класс `.font-display` (Grtsk Giga) для заголовков/чисел.

Чистый CSS/ассеты — модульного юнит-теста нет; верификация через build + ручной просмотр.

- [ ] **Step 1: Скопировать шрифты в public**

Run (из `frontend/`):
```bash
mkdir -p public/fonts
cp "../temp/design_handoff_mr_design_system/fonts/"*.otf "../temp/design_handoff_mr_design_system/fonts/"*.ttf public/fonts/
ls public/fonts/
```
Expected: 5 файлов — `Grtsk-Giga-Thin.otf`, `GrtskGiga-Light.ttf`, `Grtsk-Giga-Medium.otf`, `SuisseIntl-Light.otf`, `SuisseIntl-Regular.otf`.

- [ ] **Step 2: Переписать `src/index.css`**

Полное содержимое файла:
```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";

@custom-variant dark (&:is(.dark *));

/* ---------- MR DS fonts (self-hosted) ---------- */
@font-face { font-family:"Grtsk Giga"; src:url("/fonts/Grtsk-Giga-Thin.otf") format("opentype"); font-weight:100; font-display:swap; }
@font-face { font-family:"Grtsk Giga"; src:url("/fonts/GrtskGiga-Light.ttf") format("truetype"); font-weight:300; font-display:swap; }
@font-face { font-family:"Grtsk Giga"; src:url("/fonts/Grtsk-Giga-Medium.otf") format("opentype"); font-weight:500; font-display:swap; }
@font-face { font-family:"Suisse Intl"; src:url("/fonts/SuisseIntl-Light.otf") format("opentype"); font-weight:300; font-display:swap; }
@font-face { font-family:"Suisse Intl"; src:url("/fonts/SuisseIntl-Regular.otf") format("opentype"); font-weight:400; font-display:swap; }

@theme inline {
  --font-sans: "Suisse Intl", system-ui, sans-serif;
  --font-display: "Grtsk Giga", system-ui, sans-serif;
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  /* MR DS статусы (нет в shadcn) */
  --color-success: var(--success);
  --color-warning: var(--warning);
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 8px;
  --radius-xl: 10px;
}

/* MR DS значения — единственная тема (тёмная). :root и .dark одинаковы,
   чтобы shadcn-компоненты в любом режиме брали фирменные цвета. */
:root, .dark {
  --background: #0A0814;
  --foreground: #F4F2FA;
  --card: #16121F;
  --card-foreground: #F4F2FA;
  --popover: #1E1930;
  --popover-foreground: #F4F2FA;
  --primary: #754AE8;
  --primary-foreground: #FFFFFF;
  --secondary: #1E1930;
  --secondary-foreground: #F4F2FA;
  --muted: #16121F;
  --muted-foreground: #76728C;
  --accent: #1E1930;
  --accent-foreground: #F4F2FA;
  --destructive: #E8657A;
  --border: #2A2640;
  --input: #2A2640;
  --ring: #754AE8;
  --success: #82D6CC;
  --warning: #BD9375;
  --radius: 0.5rem;
  /* доступ к примитивам MR DS из компонентов концепта */
  --ds-surface-sunken: #110D1C;
  --ds-border-strong: #3A3556;
  --ds-hairline: #1C1830;
  --ds-text-2: #B5B2C4;
  --ds-accent-hover: #8B66F0;
  --ds-accent-subtle: rgba(117,74,232,0.16);
  --ds-focus-ring: 0 0 0 3px rgba(117,74,232,0.2);
  --ds-glow-violet: 0 0 0 1px rgba(117,74,232,.5), 0 8px 30px rgba(117,74,232,.35);
}

@layer base {
  * { @apply border-border outline-ring/50; }
  body { @apply bg-background text-foreground; font-family: var(--font-sans); }
  .font-display { font-family: var(--font-display); }
}
```

- [ ] **Step 3: Тёмная тема по умолчанию в `main.tsx`**

Заменить `<ThemeProvider>` на `<ThemeProvider defaultTheme="dark">` в `frontend/src/main.tsx:11` (свойство добавляется к существующему элементу).

- [ ] **Step 4: Проверить сборку и типы**

Run:
```bash
npm run typecheck && npm run build
```
Expected: оба PASS, без ошибок про шрифты/CSS.

- [ ] **Step 5: Ручная проверка**

Run: `npm run dev`, открыть `http://localhost:5173`. Expected: тёмный фон `#0A0814`, фиолетовые кнопки, текст шрифтом Suisse. (Старый экран ещё работает — он заменится в Task 13.)

- [ ] **Step 6: Commit**

```bash
git add public/fonts src/index.css src/main.tsx
git commit -m "feat(ui): тема MR DS (тёмная) и фирменные шрифты"
```

---

### Task 2: Доменные типы UI + фикстуры из реального файла

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/mock/fixtures.ts`
- Test: `frontend/src/lib/mock/fixtures.test.ts`

**Interfaces:**
- Produces:
  - `type MatchStatus = "confident" | "needs_review" | "no_match"`
  - `interface Candidate { article_code: string; name: string; section_name: string; score: number }`
  - `interface MatchRow { row_number: number; source_name: string; status: MatchStatus; score: number; matched_code: string | null; matched_name: string | null; candidates: Candidate[]; rationale: string | null }`
  - `type Decision = { kind: "pending" } | { kind: "confirmed"; code: string; name: string; manual: boolean } | { kind: "no_match" }`
  - `interface ReviewState { fileName: string; rows: MatchRow[]; decisions: Record<number, Decision>; filter: "all" | "review" | "no_match" }`
  - `MOCK_ROWS: MatchRow[]` (15 строк), `MOCK_ARTICLES: Candidate[]` (справочник для поиска)

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/lib/mock/fixtures.test.ts
import { describe, expect, it } from "vitest"
import { MOCK_ROWS, MOCK_ARTICLES } from "@/lib/mock/fixtures"

describe("MOCK_ROWS", () => {
  it("содержит 15 строк СМР", () => {
    expect(MOCK_ROWS).toHaveLength(15)
  })
  it("у каждой needs_review есть ровно 3 кандидата и rationale", () => {
    const review = MOCK_ROWS.filter((r) => r.status === "needs_review")
    expect(review.length).toBeGreaterThan(0)
    for (const r of review) {
      expect(r.candidates).toHaveLength(3)
      expect(r.rationale).toBeTruthy()
      expect(r.matched_code).toBeTruthy()
    }
  })
  it("confident-строки имеют matched_code и не имеют rationale", () => {
    const conf = MOCK_ROWS.filter((r) => r.status === "confident")
    expect(conf.length).toBeGreaterThan(0)
    for (const r of conf) {
      expect(r.matched_code).toBeTruthy()
      expect(r.rationale).toBeNull()
    }
  })
  it("no_match-строки без matched_code", () => {
    const nm = MOCK_ROWS.filter((r) => r.status === "no_match")
    expect(nm.length).toBeGreaterThan(0)
    for (const r of nm) expect(r.matched_code).toBeNull()
  })
  it("справочник для ручного поиска непустой", () => {
    expect(MOCK_ARTICLES.length).toBeGreaterThan(10)
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `npm run test -- fixtures`
Expected: FAIL — «Cannot find module '@/lib/mock/fixtures'».

- [ ] **Step 3: Создать `types.ts`**

```typescript
// frontend/src/lib/types.ts
export type MatchStatus = "confident" | "needs_review" | "no_match"

export interface Candidate {
  article_code: string
  name: string
  section_name: string
  score: number
}

export interface MatchRow {
  row_number: number
  source_name: string
  status: MatchStatus
  score: number
  matched_code: string | null
  matched_name: string | null
  candidates: Candidate[]
  rationale: string | null
}

export type Decision =
  | { kind: "pending" }
  | { kind: "confirmed"; code: string; name: string; manual: boolean }
  | { kind: "no_match" }

export interface ReviewState {
  fileName: string
  rows: MatchRow[]
  decisions: Record<number, Decision>
  filter: "all" | "review" | "no_match"
}
```

- [ ] **Step 4: Создать `fixtures.ts`** (15 строк СМР из реального файла `temp/Смета — копия.xlsx`)

```typescript
// frontend/src/lib/mock/fixtures.ts
import type { Candidate, MatchRow } from "@/lib/types"

export const MOCK_ARTICLES: Candidate[] = [
  { article_code: "СМР-01-001", name: "Подготовительные работы и содержание площадки", section_name: "Подготовка", score: 0 },
  { article_code: "СМР-02-010", name: "Разработка грунта котлована", section_name: "Земляные работы", score: 0 },
  { article_code: "СМР-02-014", name: "Устройство котлована с креплением стенок", section_name: "Земляные работы", score: 0 },
  { article_code: "СМР-03-021", name: "Гидроизоляция подземной части (обмазочная)", section_name: "Изоляция", score: 0 },
  { article_code: "СМР-03-022", name: "Гидроизоляция оклеечная рулонная", section_name: "Изоляция", score: 0 },
  { article_code: "СМР-04-031", name: "Возведение монолитных несущих конструкций", section_name: "Бетонные работы", score: 0 },
  { article_code: "СМР-04-033", name: "Монтаж сборных ж/б конструкций", section_name: "Бетонные работы", score: 0 },
  { article_code: "СМР-05-040", name: "Кладка перегородок и стен", section_name: "Каменные работы", score: 0 },
  { article_code: "СМР-06-050", name: "Устройство навесных фасадов", section_name: "Фасады", score: 0 },
  { article_code: "СМР-06-052", name: "Штукатурные фасады (мокрый фасад)", section_name: "Фасады", score: 0 },
  { article_code: "СМР-07-060", name: "Устройство кровли", section_name: "Кровля", score: 0 },
  { article_code: "СМР-08-070", name: "Отделка МОП и технических помещений", section_name: "Отделка", score: 0 },
  { article_code: "СМР-09-080", name: "Монтаж лифтов и подъёмников", section_name: "Инженерия", score: 0 },
  { article_code: "СМР-10-090", name: "Инженерные системы (ОВ, ВК, ЭОМ)", section_name: "Инженерия", score: 0 },
  { article_code: "СМР-11-100", name: "Благоустройство и наружное освещение", section_name: "Благоустройство", score: 0 },
  { article_code: "СМР-12-110", name: "Технологические решения автостоянки", section_name: "Технология", score: 0 },
]

function cand(code: string, score: number): Candidate {
  const a = MOCK_ARTICLES.find((x) => x.article_code === code)!
  return { ...a, score }
}

export const MOCK_ROWS: MatchRow[] = [
  { row_number: 2, source_name: "Подготовительные работы и содержание площадки (включая содержание прилегающей территории)", status: "confident", score: 0.96, matched_code: "СМР-01-001", matched_name: "Подготовительные работы и содержание площадки", candidates: [cand("СМР-01-001", 0.96)], rationale: null },
  { row_number: 3, source_name: "Устройство котлована", status: "needs_review", score: 0.83, matched_code: "СМР-02-014", matched_name: "Устройство котлована с креплением стенок", candidates: [cand("СМР-02-014", 0.83), cand("СМР-02-010", 0.79), cand("СМР-04-031", 0.55)], rationale: "Речь о выемке грунта под здание с креплением стенок, а не просто разработке грунта." },
  { row_number: 4, source_name: "Устройство гидроизоляции подземной части здания", status: "needs_review", score: 0.81, matched_code: "СМР-03-021", matched_name: "Гидроизоляция подземной части (обмазочная)", candidates: [cand("СМР-03-021", 0.81), cand("СМР-03-022", 0.77), cand("СМР-04-031", 0.4)], rationale: "Подземная часть — обычно обмазочная гидроизоляция; оклеечная маловероятна по контексту." },
  { row_number: 5, source_name: "Возведение несущих конструкций здания", status: "confident", score: 0.94, matched_code: "СМР-04-031", matched_name: "Возведение монолитных несущих конструкций", candidates: [cand("СМР-04-031", 0.94)], rationale: null },
  { row_number: 6, source_name: "Общестроительные работы - перегородки и стены", status: "confident", score: 0.92, matched_code: "СМР-05-040", matched_name: "Кладка перегородок и стен", candidates: [cand("СМР-05-040", 0.92)], rationale: null },
  { row_number: 7, source_name: "Устройство фасадов", status: "needs_review", score: 0.74, matched_code: "СМР-06-050", matched_name: "Устройство навесных фасадов", candidates: [cand("СМР-06-050", 0.74), cand("СМР-06-052", 0.71), cand("СМР-07-060", 0.45)], rationale: "Тип фасада не указан; навесной — более частый для зданий такого класса." },
  { row_number: 8, source_name: "Устройство кровли", status: "confident", score: 0.95, matched_code: "СМР-07-060", matched_name: "Устройство кровли", candidates: [cand("СМР-07-060", 0.95)], rationale: null },
  { row_number: 9, source_name: "Отделка паркинга, технических помещений, МОП, двери, ворота и шлагбаумы", status: "confident", score: 0.9, matched_code: "СМР-08-070", matched_name: "Отделка МОП и технических помещений", candidates: [cand("СМР-08-070", 0.9)], rationale: null },
  { row_number: 10, source_name: "Лифты и подъемники с использованием системы мониторинга и диспетчеризации", status: "confident", score: 0.93, matched_code: "СМР-09-080", matched_name: "Монтаж лифтов и подъёмников", candidates: [cand("СМР-09-080", 0.93)], rationale: null },
  { row_number: 11, source_name: "Инженерные системы", status: "confident", score: 0.91, matched_code: "СМР-10-090", matched_name: "Инженерные системы (ОВ, ВК, ЭОМ)", candidates: [cand("СМР-10-090", 0.91)], rationale: null },
  { row_number: 12, source_name: "Благоустройство и наружное освещение", status: "confident", score: 0.95, matched_code: "СМР-11-100", matched_name: "Благоустройство и наружное освещение", candidates: [cand("СМР-11-100", 0.95)], rationale: null },
  { row_number: 13, source_name: "Технологические решения автостоянки, комплекса и арендуемых помещений", status: "needs_review", score: 0.68, matched_code: "СМР-12-110", matched_name: "Технологические решения автостоянки", candidates: [cand("СМР-12-110", 0.68), cand("СМР-10-090", 0.6), cand("СМР-08-070", 0.41)], rationale: "Совпало частично — «технологические решения» шире статьи автостоянки; проверить вручную." },
  { row_number: 14, source_name: "ЗИП", status: "no_match", score: 0.31, matched_code: null, matched_name: null, candidates: [], rationale: null },
  { row_number: 15, source_name: "MR - SHELL & CORE", status: "no_match", score: 0.28, matched_code: null, matched_name: null, candidates: [], rationale: null },
  { row_number: 16, source_name: "Работы по реконструкции и реставрации", status: "no_match", score: 0.35, matched_code: null, matched_name: null, candidates: [], rationale: null },
]
```

- [ ] **Step 5: Запустить тест — PASS**

Run: `npm run test -- fixtures`
Expected: PASS (5 тестов). Then `npm run typecheck` — PASS.

- [ ] **Step 6: Commit**

```bash
git add src/lib/types.ts src/lib/mock/fixtures.ts src/lib/mock/fixtures.test.ts
git commit -m "feat(mock): доменные типы UI и фикстуры из реального файла сметы"
```

---

### Task 3: Мок-API (сопоставление, поиск, выгрузка CSV)

**Files:**
- Create: `frontend/src/lib/mock/api.ts`
- Test: `frontend/src/lib/mock/api.test.ts`

**Interfaces:**
- Consumes: `MOCK_ROWS`, `MOCK_ARTICLES`, типы из Task 2.
- Produces:
  - `interface Progress { phase: "parsing" | "embedding" | "matching" | "done"; done: number; total: number; etaSeconds: number | null }`
  - `matchEstimate(file: File, onProgress: (p: Progress) => void): Promise<MatchRow[]>`
  - `searchArticles(query: string): Promise<Candidate[]>`
  - `exportEstimateCsv(state: ReviewState): string`
  - `downloadCsv(filename: string, csv: string): void`
  - `statusLabelForExport(row: MatchRow, decision: Decision): string` (re-exported из reviewState в Task 5; здесь импортируется)

> Примечание: ETA числовой появляется только на фазе `matching` (когда знаменатель — число спорных — известен), на `parsing`/`embedding` `etaSeconds === null` (спека, экран 02).

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/lib/mock/api.test.ts
import { describe, expect, it, vi } from "vitest"
import { matchEstimate, searchArticles, exportEstimateCsv } from "@/lib/mock/api"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

describe("mock api", () => {
  it("matchEstimate возвращает строки и сообщает прогресс, ETA только на matching", async () => {
    const phases: string[] = []
    const etaByPhase: Record<string, number | null> = {}
    const rows = await matchEstimate(new File([""], "смета.xlsx"), (p) => {
      phases.push(p.phase)
      etaByPhase[p.phase] = p.etaSeconds
    })
    expect(rows.length).toBe(15)
    expect(phases).toContain("embedding")
    expect(phases).toContain("matching")
    expect(etaByPhase["embedding"]).toBeNull()
    expect(typeof etaByPhase["matching"]).toBe("number")
  })

  it("searchArticles фильтрует справочник по подстроке без регистра", async () => {
    const res = await searchArticles("кровл")
    expect(res.some((c) => c.name.toLowerCase().includes("кровл"))).toBe(true)
  })

  it("exportEstimateCsv: ручной выбор → пустой Score, статус «Ручной выбор»", () => {
    const state = initReview("смета.xlsx", MOCK_ROWS)
    state.decisions[3] = { kind: "confirmed", code: "СМР-99-999", name: "Ручная статья", manual: true }
    const csv = exportEstimateCsv(state)
    const line = csv.split("\n").find((l) => l.startsWith("3;"))!
    const cells = line.split(";")
    // колонки: row;source;code;name;score;status;alt2;alt3
    expect(cells[2]).toBe("СМР-99-999")
    expect(cells[4]).toBe("") // score пустой
    expect(cells[5]).toContain("Ручной выбор")
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- mock/api`
Expected: FAIL — модуль `@/lib/mock/api` не найден.

- [ ] **Step 3: Реализовать `api.ts`**

```typescript
// frontend/src/lib/mock/api.ts
import type { Candidate, MatchRow, ReviewState } from "@/lib/types"
import { MOCK_ARTICLES, MOCK_ROWS } from "@/lib/mock/fixtures"
import { decisionFor, statusLabel } from "@/lib/reviewState"

export interface Progress {
  phase: "parsing" | "embedding" | "matching" | "done"
  done: number
  total: number
  etaSeconds: number | null
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** Мок сопоставления: имитирует фазы и прогресс, отдаёт фикстуру. */
export async function matchEstimate(
  _file: File,
  onProgress: (p: Progress) => void,
): Promise<MatchRow[]> {
  const total = MOCK_ROWS.length
  onProgress({ phase: "parsing", done: 0, total, etaSeconds: null })
  await delay(150)
  for (let i = 1; i <= total; i++) {
    onProgress({ phase: "embedding", done: i, total, etaSeconds: null })
    await delay(20)
  }
  const review = MOCK_ROWS.filter((r) => r.status !== "confident").length
  for (let i = 1; i <= total; i++) {
    // ETA известен: ~0.4с на спорную строку (LLM дороже эмбеддинга)
    const remainingReview = Math.max(0, review - Math.round((i / total) * review))
    onProgress({ phase: "matching", done: i, total, etaSeconds: remainingReview * 0.4 })
    await delay(20)
  }
  onProgress({ phase: "done", done: total, total, etaSeconds: 0 })
  return MOCK_ROWS
}

/** Escape-hatch: ручной поиск по справочнику (мок). */
export async function searchArticles(query: string): Promise<Candidate[]> {
  await delay(120)
  const q = query.trim().toLowerCase()
  if (!q) return []
  return MOCK_ARTICLES.filter(
    (c) =>
      c.name.toLowerCase().includes(q) ||
      c.article_code.toLowerCase().includes(q) ||
      c.section_name.toLowerCase().includes(q),
  )
}

const HEADERS = ["row", "Работа из сметы", "Код статьи", "Наименование статьи", "Score", "Статус", "Альтернатива 2", "Альтернатива 3"]

/** Стенд-ин выгрузки: CSV (`;`-разделитель). Прод заменит на бэкенд .xlsx. */
export function exportEstimateCsv(state: ReviewState): string {
  const esc = (v: string) => (v.includes(";") || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v)
  const lines = [HEADERS.join(";")]
  for (const row of state.rows) {
    const d = decisionFor(state, row)
    const manual = d.kind === "confirmed" && d.manual
    const code = d.kind === "confirmed" ? d.code : ""
    const name = d.kind === "confirmed" ? d.name : ""
    const score = manual || d.kind === "no_match" ? "" : row.score.toFixed(2)
    const alt2 = row.candidates[1] ? `${row.candidates[1].article_code} ${row.candidates[1].name}` : ""
    const alt3 = row.candidates[2] ? `${row.candidates[2].article_code} ${row.candidates[2].name}` : ""
    lines.push([String(row.row_number), row.source_name, code, name, score, statusLabel(row, d), alt2, alt3].map(esc).join(";"))
  }
  return lines.join("\n")
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
```

> Зависимость: `decisionFor`/`statusLabel` реализуются в Task 5. Реализуйте Task 5 перед запуском теста Task 3 (тест Task 3 импортирует `initReview`). Порядок исполнения: 2 → 5 → 3, либо заглушить и вернуться. Здесь Task 5 идёт следующим намеренно; запускайте тест Task 3 после Task 5.

- [ ] **Step 4: Реализовать Task 5 (reviewState), затем вернуться и запустить тест Task 3 — PASS**

Run: `npm run test -- mock/api`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add src/lib/mock/api.ts src/lib/mock/api.test.ts
git commit -m "feat(mock): мок-API сопоставления, поиска статьи и выгрузки CSV"
```

---

### Task 4: Сохранение/восстановление сессии (sessionStorage)

**Files:**
- Create: `frontend/src/lib/session.ts`
- Test: `frontend/src/lib/session.test.ts`

**Interfaces:**
- Consumes: `ReviewState`.
- Produces:
  - `const REVIEW_SESSION_KEY = "ciw.review.v1"`
  - `saveReview(state: ReviewState): void` (при `QuotaExceededError` логирует `console.warn` и продолжает)
  - `loadReview(): ReviewState | null`
  - `clearReview(): void`

> ⚠️ **Это осознанное упрощение прототипа, НЕ требование спеки.** Спека постановила
> обратное: для production — **IndexedDB**, потому что реальные сметы доходят до тысяч
> строк, и `sessionStorage` (~5 МБ) на них молча падает с `QuotaExceededError`. Здесь
> `sessionStorage` оправдан **только потому, что прототип гоняет 15 фикстур без бэкенда** —
> объём заведомо крошечный. **Production-гейт:** прежде чем подключать реальный бэкенд,
> вернуть IndexedDB для данных прогона (per спека, раздел «Долговечность сессии»). Не
> читать этот выбор как «спека разрешает sessionStorage» — она не разрешает.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/lib/session.test.ts
import { afterEach, describe, expect, it } from "vitest"
import { saveReview, loadReview, clearReview } from "@/lib/session"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

afterEach(() => clearReview())

describe("session", () => {
  it("round-trip: сохранили → загрузили то же", () => {
    const state = initReview("смета.xlsx", MOCK_ROWS)
    saveReview(state)
    const loaded = loadReview()
    expect(loaded?.fileName).toBe("смета.xlsx")
    expect(loaded?.rows).toHaveLength(15)
  })
  it("loadReview без данных → null", () => {
    expect(loadReview()).toBeNull()
  })
  it("clearReview стирает", () => {
    saveReview(initReview("x.xlsx", MOCK_ROWS))
    clearReview()
    expect(loadReview()).toBeNull()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- session`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `session.ts`**

```typescript
// frontend/src/lib/session.ts
import type { ReviewState } from "@/lib/types"

export const REVIEW_SESSION_KEY = "ciw.review.v1"

export function saveReview(state: ReviewState): void {
  try {
    sessionStorage.setItem(REVIEW_SESSION_KEY, JSON.stringify(state))
  } catch (err) {
    // Прототип-стенд-ин. На крупных сметах прод обязан использовать IndexedDB (per спека).
    // Не глушим молча: иначе провал восстановления невидим.
    console.warn("saveReview: не удалось сохранить сессию (вероятно QuotaExceededError) — нужен IndexedDB в проде", err)
  }
}

export function loadReview(): ReviewState | null {
  const raw = sessionStorage.getItem(REVIEW_SESSION_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as ReviewState
  } catch {
    return null
  }
}

export function clearReview(): void {
  sessionStorage.removeItem(REVIEW_SESSION_KEY)
}
```

- [ ] **Step 4: Запустить тест — PASS**

Run: `npm run test -- session`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add src/lib/session.ts src/lib/session.test.ts
git commit -m "feat(session): восстановление ревью через sessionStorage"
```

---

### Task 5: Reducer ревью + селекторы

**Files:**
- Create: `frontend/src/lib/reviewState.ts`
- Test: `frontend/src/lib/reviewState.test.ts`

**Interfaces:**
- Consumes: `MatchRow`, `Decision`, `ReviewState`, `Candidate`.
- Produces:
  - `initReview(fileName: string, rows: MatchRow[]): ReviewState` — confident → `confirmed` авто; needs_review/no_match → `pending`
  - `type ReviewAction =`
    `{ type: "pickCandidate"; row: number; code: string }` ·
    `{ type: "confirmArbiter"; row: number }` ·
    `{ type: "manualPick"; row: number; candidate: Candidate }` ·
    `{ type: "confirmNoMatch"; row: number }` ·
    `{ type: "reopen"; row: number }` ·
    `{ type: "setFilter"; filter: ReviewState["filter"] }` ·
    `{ type: "load"; state: ReviewState }` (замена всего состояния — для загрузки новой сметы/восстановления)
  - `reviewReducer(state: ReviewState, action: ReviewAction): ReviewState`
  - `decisionFor(state: ReviewState, row: MatchRow): Decision`
  - `progress(state: ReviewState): { reviewed: number; total: number }` — total = число строк, требующих решения (needs_review + no_match); reviewed = из них с не-pending решением
  - `filteredRows(state: ReviewState): MatchRow[]`
  - `statusLabel(row: MatchRow, d: Decision): string`
  - `requiresDecision(row: MatchRow): boolean`

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/lib/reviewState.test.ts
import { describe, expect, it } from "vitest"
import {
  initReview, reviewReducer, decisionFor, progress, filteredRows, statusLabel,
} from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

const base = () => initReview("смета.xlsx", MOCK_ROWS)
const rowNum = (status: string) => MOCK_ROWS.find((r) => r.status === status)!.row_number

describe("reviewState", () => {
  it("confident инициализируются как confirmed, спорные — pending", () => {
    const s = base()
    expect(decisionFor(s, MOCK_ROWS.find((r) => r.status === "confident")!).kind).toBe("confirmed")
    expect(decisionFor(s, MOCK_ROWS.find((r) => r.status === "needs_review")!).kind).toBe("pending")
  })

  it("progress: total = спорные + без пары, изначально reviewed считает только confident? нет — только требующие", () => {
    const s = base()
    const review = MOCK_ROWS.filter((r) => r.status !== "confident").length
    expect(progress(s).total).toBe(review)
    expect(progress(s).reviewed).toBe(0)
  })

  it("confirmArbiter закрывает спорную строку и двигает прогресс", () => {
    const r = rowNum("needs_review")
    const s = reviewReducer(base(), { type: "confirmArbiter", row: r })
    const d = decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!)
    expect(d.kind).toBe("confirmed")
    expect(progress(s).reviewed).toBe(1)
  })

  it("confirmNoMatch закрывает строку «без пары» (входит в счётчик)", () => {
    const r = rowNum("no_match")
    const s = reviewReducer(base(), { type: "confirmNoMatch", row: r })
    expect(decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!).kind).toBe("no_match")
    expect(progress(s).reviewed).toBe(1)
  })

  it("manualPick помечает manual:true", () => {
    const r = rowNum("needs_review")
    const s = reviewReducer(base(), {
      type: "manualPick", row: r,
      candidate: { article_code: "СМР-99-999", name: "Ручная", section_name: "X", score: 0 },
    })
    const d = decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!)
    expect(d).toMatchObject({ kind: "confirmed", manual: true, code: "СМР-99-999" })
  })

  it("filter=review показывает только needs_review", () => {
    const s = reviewReducer(base(), { type: "setFilter", filter: "review" })
    expect(filteredRows(s).every((r) => r.status === "needs_review")).toBe(true)
  })

  it("statusLabel различает арбитра, ручной выбор и без пары", () => {
    expect(statusLabel(MOCK_ROWS[0], { kind: "confirmed", code: "x", name: "y", manual: false })).toBe("Подтверждено оператором")
    expect(statusLabel(MOCK_ROWS[0], { kind: "confirmed", code: "x", name: "y", manual: true })).toBe("Ручной выбор")
    expect(statusLabel(MOCK_ROWS[0], { kind: "no_match" })).toBe("Нет совпадения")
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- reviewState`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `reviewState.ts`**

```typescript
// frontend/src/lib/reviewState.ts
import type { Candidate, Decision, MatchRow, ReviewState } from "@/lib/types"

export function requiresDecision(row: MatchRow): boolean {
  return row.status !== "confident"
}

export function initReview(fileName: string, rows: MatchRow[]): ReviewState {
  const decisions: Record<number, Decision> = {}
  for (const r of rows) {
    decisions[r.row_number] =
      r.status === "confident" && r.matched_code && r.matched_name
        ? { kind: "confirmed", code: r.matched_code, name: r.matched_name, manual: false }
        : { kind: "pending" }
  }
  return { fileName, rows, decisions, filter: "all" }
}

export type ReviewAction =
  | { type: "pickCandidate"; row: number; code: string }
  | { type: "confirmArbiter"; row: number }
  | { type: "manualPick"; row: number; candidate: Candidate }
  | { type: "confirmNoMatch"; row: number }
  | { type: "reopen"; row: number }
  | { type: "setFilter"; filter: ReviewState["filter"] }
  | { type: "load"; state: ReviewState }

function rowByNum(state: ReviewState, n: number): MatchRow | undefined {
  return state.rows.find((r) => r.row_number === n)
}

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  const set = (row: number, d: Decision): ReviewState => ({
    ...state,
    decisions: { ...state.decisions, [row]: d },
  })
  switch (action.type) {
    case "load":
      return action.state
    case "setFilter":
      return { ...state, filter: action.filter }
    case "reopen":
      return set(action.row, { kind: "pending" })
    case "confirmNoMatch":
      return set(action.row, { kind: "no_match" })
    case "confirmArbiter": {
      const r = rowByNum(state, action.row)
      if (!r || !r.matched_code || !r.matched_name) return state
      return set(action.row, { kind: "confirmed", code: r.matched_code, name: r.matched_name, manual: false })
    }
    case "pickCandidate": {
      const r = rowByNum(state, action.row)
      const c = r?.candidates.find((x) => x.article_code === action.code)
      if (!c) return state
      return set(action.row, { kind: "confirmed", code: c.article_code, name: c.name, manual: false })
    }
    case "manualPick":
      return set(action.row, { kind: "confirmed", code: action.candidate.article_code, name: action.candidate.name, manual: true })
    default:
      return state
  }
}

export function decisionFor(state: ReviewState, row: MatchRow): Decision {
  return state.decisions[row.row_number] ?? { kind: "pending" }
}

export function progress(state: ReviewState): { reviewed: number; total: number } {
  const required = state.rows.filter(requiresDecision)
  const reviewed = required.filter((r) => decisionFor(state, r).kind !== "pending").length
  return { reviewed, total: required.length }
}

export function filteredRows(state: ReviewState): MatchRow[] {
  switch (state.filter) {
    case "review":
      return state.rows.filter((r) => r.status === "needs_review")
    case "no_match":
      return state.rows.filter((r) => r.status === "no_match")
    default:
      return state.rows
  }
}

export function statusLabel(_row: MatchRow, d: Decision): string {
  if (d.kind === "no_match") return "Нет совпадения"
  if (d.kind === "pending") return "Требует проверки"
  return d.manual ? "Ручной выбор" : "Подтверждено оператором"
}
```

- [ ] **Step 4: Запустить тесты Task 5 и Task 3 — PASS**

Run: `npm run test -- reviewState` затем `npm run test -- mock/api`
Expected: оба PASS. Затем `npm run typecheck` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/lib/reviewState.ts src/lib/reviewState.test.ts
git commit -m "feat(review): reducer решений оператора, прогресс и фильтры"
```

---

### Task 6: Клавиатурный луп ревью (хук)

**Files:**
- Create: `frontend/src/lib/useReviewKeyboard.ts`
- Test: `frontend/src/lib/useReviewKeyboard.test.tsx`

**Interfaces:**
- Produces: `useReviewKeyboard(opts: { enabled: boolean; candidateCount: number; onPick: (index: number) => void; onConfirm: () => void; onNext: () => void }): void`
  - `1`/`2`/`3` → `onPick(0|1|2)` (только если `index < candidateCount`)
  - `Enter` → `onConfirm()`
  - `n` → `onNext()`
  - Игнорирует, когда фокус в input/textarea/select/contenteditable, и при `enabled === false`.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/lib/useReviewKeyboard.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReviewKeyboard } from "@/lib/useReviewKeyboard"

function Harness(props: Parameters<typeof useReviewKeyboard>[0]) {
  useReviewKeyboard(props)
  return <input aria-label="вне-лупа" />
}

describe("useReviewKeyboard", () => {
  it("цифры выбирают кандидата, Enter подтверждает, n — следующая", async () => {
    const onPick = vi.fn(), onConfirm = vi.fn(), onNext = vi.fn()
    render(<Harness enabled candidateCount={3} onPick={onPick} onConfirm={onConfirm} onNext={onNext} />)
    await userEvent.keyboard("2")
    expect(onPick).toHaveBeenCalledWith(1)
    await userEvent.keyboard("{Enter}")
    expect(onConfirm).toHaveBeenCalled()
    await userEvent.keyboard("n")
    expect(onNext).toHaveBeenCalled()
  })

  it("игнорирует ввод в поле и при enabled=false", async () => {
    const onPick = vi.fn()
    const { rerender } = render(<Harness enabled={false} candidateCount={3} onPick={onPick} onConfirm={vi.fn()} onNext={vi.fn()} />)
    await userEvent.keyboard("1")
    expect(onPick).not.toHaveBeenCalled()
    rerender(<Harness enabled candidateCount={3} onPick={onPick} onConfirm={vi.fn()} onNext={vi.fn()} />)
    const input = document.querySelector("input")!
    input.focus()
    await userEvent.keyboard("1")
    expect(onPick).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- useReviewKeyboard`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `useReviewKeyboard.ts`**

```typescript
// frontend/src/lib/useReviewKeyboard.ts
import { useEffect } from "react"

interface Options {
  enabled: boolean
  candidateCount: number
  onPick: (index: number) => void
  onConfirm: () => void
  onNext: () => void
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return Boolean(target.closest("input, textarea, select, [contenteditable='true']"))
}

export function useReviewKeyboard({ enabled, candidateCount, onPick, onConfirm, onNext }: Options): void {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      if (isEditable(e.target)) return
      if (e.key === "1" || e.key === "2" || e.key === "3") {
        const idx = Number(e.key) - 1
        if (idx < candidateCount) { e.preventDefault(); onPick(idx) }
      } else if (e.key === "Enter") {
        e.preventDefault(); onConfirm()
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault(); onNext()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [enabled, candidateCount, onPick, onConfirm, onNext])
}
```

- [ ] **Step 4: Запустить тест — PASS**

Run: `npm run test -- useReviewKeyboard`
Expected: PASS (2 теста).

- [ ] **Step 5: Commit**

```bash
git add src/lib/useReviewKeyboard.ts src/lib/useReviewKeyboard.test.tsx
git commit -m "feat(review): клавиатурный луп проверки (1·2·3 / Enter / n)"
```

---

### Task 7: Компонент строки ревью (раскрытие + кандидаты + rationale + ручной поиск)

**Files:**
- Create: `frontend/src/pages/estimate/ReviewRow.tsx`
- Test: `frontend/src/pages/estimate/ReviewRow.test.tsx`

**Interfaces:**
- Consumes: `MatchRow`, `Decision`, `Candidate`; `searchArticles` (мок); `statusLabel` (Task 5).
- Produces: компонент
  ```typescript
  interface ReviewRowProps {
    row: MatchRow
    decision: Decision
    expanded: boolean
    onToggle: () => void
    onPickCandidate: (code: string) => void
    onManualPick: (c: Candidate) => void
    onConfirmNoMatch: () => void
  }
  export function ReviewRow(props: ReviewRowProps): JSX.Element
  ```
- Поведение: раскрытая `needs_review` показывает rationale (если есть), 3 кандидата (выбранный — рамка), score приглушённым, и поле «искать вручную» (escape-hatch). `no_match` раскрытая показывает «искать вручную» + кнопку «Оставить без пары». Рендерится как набор `<tr>` (строка + строка-раскрытие через `<td colSpan>`).

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/pages/estimate/ReviewRow.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReviewRow } from "@/pages/estimate/ReviewRow"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

function tableWrap(ui: React.ReactNode) {
  return <table><tbody>{ui}</tbody></table>
}
const reviewRow = MOCK_ROWS.find((r) => r.status === "needs_review")!

describe("ReviewRow", () => {
  it("раскрытая спорная строка показывает rationale и 3 кандидата", () => {
    render(tableWrap(
      <ReviewRow row={reviewRow} decision={{ kind: "pending" }} expanded
        onToggle={vi.fn()} onPickCandidate={vi.fn()} onManualPick={vi.fn()} onConfirmNoMatch={vi.fn()} />
    ))
    expect(screen.getByText(reviewRow.rationale!)).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /СМР-/ })).toHaveLength(3)
  })

  it("клик по кандидату вызывает onPickCandidate с кодом", async () => {
    const onPick = vi.fn()
    render(tableWrap(
      <ReviewRow row={reviewRow} decision={{ kind: "pending" }} expanded
        onToggle={vi.fn()} onPickCandidate={onPick} onManualPick={vi.fn()} onConfirmNoMatch={vi.fn()} />
    ))
    await userEvent.click(screen.getByRole("button", { name: new RegExp(reviewRow.candidates[1].article_code) }))
    expect(onPick).toHaveBeenCalledWith(reviewRow.candidates[1].article_code)
  })

  it("ручной поиск находит статью и отдаёт её в onManualPick", async () => {
    const onManual = vi.fn()
    render(tableWrap(
      <ReviewRow row={reviewRow} decision={{ kind: "pending" }} expanded
        onToggle={vi.fn()} onPickCandidate={vi.fn()} onManualPick={onManual} onConfirmNoMatch={vi.fn()} />
    ))
    await userEvent.type(screen.getByPlaceholderText(/искать в справочнике/i), "кровл")
    const hit = await screen.findByRole("button", { name: /кровл/i })
    await userEvent.click(hit)
    expect(onManual).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- ReviewRow`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `ReviewRow.tsx`**

```tsx
// frontend/src/pages/estimate/ReviewRow.tsx
import { useState } from "react"
import { ChevronDown, Search } from "lucide-react"
import type { Candidate, Decision, MatchRow } from "@/lib/types"
import { statusLabel } from "@/lib/reviewState"
import { searchArticles } from "@/lib/mock/api"

interface ReviewRowProps {
  row: MatchRow
  decision: Decision
  expanded: boolean
  onToggle: () => void
  onPickCandidate: (code: string) => void
  onManualPick: (c: Candidate) => void
  onConfirmNoMatch: () => void
}

const statusTone: Record<string, string> = {
  confident: "text-[var(--success)]",
  needs_review: "text-[var(--warning)]",
  no_match: "text-destructive",
}

export function ReviewRow({ row, decision, expanded, onToggle, onPickCandidate, onManualPick, onConfirmNoMatch }: ReviewRowProps) {
  const [query, setQuery] = useState("")
  const [hits, setHits] = useState<Candidate[]>([])
  const flagged = row.status !== "confident"
  const chosenCode = decision.kind === "confirmed" ? decision.code : row.matched_code

  async function runSearch(q: string) {
    setQuery(q)
    setHits(await searchArticles(q))
  }

  return (
    <>
      <tr
        className={flagged ? "cursor-pointer border-l-2 border-l-[var(--warning)]" : ""}
        onClick={flagged ? onToggle : undefined}
        data-state={expanded ? "open" : "closed"}
      >
        <td className="px-4 py-2 font-mono text-muted-foreground">{row.row_number}</td>
        <td className="px-4 py-2 text-[var(--ds-text-2)]">{row.source_name}</td>
        <td className="px-4 py-2">
          {decision.kind === "no_match" || row.status === "no_match"
            ? <span className="text-muted-foreground">— без пары —</span>
            : <span>{flagged && <ChevronDown className="mr-1 inline size-3 text-[var(--ds-accent-hover)]" />}<span className="font-mono text-xs text-muted-foreground">{chosenCode}</span> {decision.kind === "confirmed" ? decision.name : row.matched_name}</span>}
        </td>
        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">{row.status === "needs_review" ? row.score.toFixed(2) : row.status === "confident" ? row.score.toFixed(2) : ""}</td>
        <td className={"px-4 py-2 text-sm " + (statusTone[row.status] ?? "")}>{statusLabel(row, decision)}</td>
      </tr>

      {expanded && flagged && (
        <tr>
          <td colSpan={5} className="bg-[color-mix(in_srgb,var(--primary)_5%,transparent)] px-12 py-3">
            {row.rationale && (
              <p className="mb-2 text-sm text-[var(--ds-text-2)]">
                <span className="mr-1 text-xs uppercase tracking-wide text-muted-foreground">Почему:</span>{row.rationale}
              </p>
            )}
            {row.candidates.map((c, i) => {
              const sel = c.article_code === chosenCode
              return (
                <button
                  key={c.article_code}
                  onClick={(e) => { e.stopPropagation(); onPickCandidate(c.article_code) }}
                  className={"mb-1.5 flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm " + (sel ? "border-primary shadow-[var(--ds-glow-violet)]" : "border-border")}
                >
                  <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">{i + 1}</kbd>
                  <span className="font-mono text-xs text-muted-foreground">{c.article_code}</span>
                  <span className="flex-1">{c.name}</span>
                  <span className="font-mono text-xs text-muted-foreground">{c.score.toFixed(2)}</span>
                </button>
              )
            })}

            <div className="mt-2 flex items-center gap-2 rounded-md border border-border px-2">
              <Search className="size-3.5 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => runSearch(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                placeholder="Нет верного — искать в справочнике…"
                className="flex-1 bg-transparent py-2 text-sm outline-none"
              />
            </div>
            {hits.map((c) => (
              <button
                key={c.article_code}
                onClick={(e) => { e.stopPropagation(); onManualPick(c) }}
                className="mt-1 flex w-full items-center gap-3 rounded-md border border-border px-3 py-1.5 text-left text-sm hover:border-[var(--ds-border-strong)]"
              >
                <span className="font-mono text-xs text-muted-foreground">{c.article_code}</span>
                <span className="flex-1">{c.name}</span>
              </button>
            ))}

            {row.status === "no_match" && (
              <button
                onClick={(e) => { e.stopPropagation(); onConfirmNoMatch() }}
                className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                Оставить без пары
              </button>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
```

> Примечание: для `no_match` строки `flagged` тоже `true` (status !== confident), поэтому она раскрывается и показывает поиск + «Оставить без пары».

- [ ] **Step 4: Запустить тест — PASS**

Run: `npm run test -- ReviewRow`
Expected: PASS (3 теста). Затем `npm run typecheck` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/estimate/ReviewRow.tsx src/pages/estimate/ReviewRow.test.tsx
git commit -m "feat(review): строка с раскрытием, кандидатами, rationale и ручным поиском"
```

---

### Task 8: Главный экран «Проверка» (таблица, фильтры, прогресс, выгрузка)

**Files:**
- Create: `frontend/src/pages/estimate/ReviewScreen.tsx`
- Test: `frontend/src/pages/estimate/ReviewScreen.test.tsx`

**Interfaces:**
- Consumes: reducer/селекторы (Task 5), `ReviewRow` (Task 7), `useReviewKeyboard` (Task 6), `exportEstimateCsv`/`downloadCsv` (Task 3), `saveReview` (Task 4).
- Produces:
  ```typescript
  interface ReviewScreenProps {
    state: ReviewState
    dispatch: React.Dispatch<import("@/lib/reviewState").ReviewAction>
    onExport: () => void
    onNewEstimate: () => void
  }
  export function ReviewScreen(props: ReviewScreenProps): JSX.Element
  ```
- Поведение: под-панель (имя файла + счётчики + «Новая смета» + «Выгрузить Excel»); тулбар (чипы Все/Проверить/Без пары, прогресс «проверено k из N»); таблица из `filteredRows`. Активная раскрытая строка — локальный стейт `activeRow`; клавиатура: `1·2·3` выбирает кандидата активной строки, `Enter` подтверждает арбитра, `n` — следующая спорная (авто-раскрытие + перенос `activeRow`).

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/pages/estimate/ReviewScreen.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReducer } from "react"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { initReview, reviewReducer, progress } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

function Wrap({ onExport = vi.fn() }: { onExport?: () => void }) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () => initReview("смета.xlsx", MOCK_ROWS))
  return <ReviewScreen state={state} dispatch={dispatch} onExport={onExport} onNewEstimate={vi.fn()} />
}

describe("ReviewScreen", () => {
  it("показывает имя файла и счётчики", () => {
    render(<Wrap />)
    expect(screen.getByText(/смета\.xlsx/)).toBeInTheDocument()
    expect(screen.getByText(/проверено/i)).toBeInTheDocument()
  })

  it("фильтр «Проверить» оставляет только спорные строки", async () => {
    render(<Wrap />)
    await userEvent.click(screen.getByRole("button", { name: /Проверить/ }))
    // confident-строка «Устройство кровли» исчезает
    expect(screen.queryByText("Устройство кровли")).not.toBeInTheDocument()
  })

  it("кнопка выгрузки вызывает onExport", async () => {
    const onExport = vi.fn()
    render(<Wrap onExport={onExport} />)
    await userEvent.click(screen.getByRole("button", { name: /Выгрузить/ }))
    expect(onExport).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- ReviewScreen`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `ReviewScreen.tsx`**

```tsx
// frontend/src/pages/estimate/ReviewScreen.tsx
import { useEffect, useState } from "react"
import { Download, Plus } from "lucide-react"
import type { ReviewState } from "@/lib/types"
import {
  type ReviewAction, decisionFor, filteredRows, progress,
} from "@/lib/reviewState"
import { Button } from "@/components/ui/button"
import { ReviewRow } from "@/pages/estimate/ReviewRow"
import { useReviewKeyboard } from "@/lib/useReviewKeyboard"

interface ReviewScreenProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction>
  onExport: () => void
  onNewEstimate: () => void
}

const counts = (state: ReviewState) => ({
  confident: state.rows.filter((r) => r.status === "confident").length,
  review: state.rows.filter((r) => r.status === "needs_review").length,
  no_match: state.rows.filter((r) => r.status === "no_match").length,
})

export function ReviewScreen({ state, dispatch, onExport, onNewEstimate }: ReviewScreenProps) {
  const rows = filteredRows(state)
  const { reviewed, total } = progress(state)
  const c = counts(state)
  const [activeRow, setActiveRow] = useState<number | null>(null)

  // Очередь навигации = спорные строки ИЗ ВИДИМОГО (отфильтрованного) набора,
  // чтобы «следующая» не уезжала на строку, скрытую активным фильтром.
  const queue = rows.filter((r) => r.status !== "confident")
  const gotoNext = () => {
    const idx = queue.findIndex((r) => r.row_number === activeRow)
    const next = queue.slice(idx + 1).find((r) => decisionFor(state, r).kind === "pending")
      ?? queue.find((r) => decisionFor(state, r).kind === "pending")
    setActiveRow(next ? next.row_number : null)
  }
  // автостарт: первая нерешённая спорная в текущем фильтре
  useEffect(() => {
    if (activeRow === null) {
      const first = queue.find((r) => decisionFor(state, r).kind === "pending")
      if (first) setActiveRow(first.row_number)
    }
  }, [activeRow, queue, state])

  const active = state.rows.find((r) => r.row_number === activeRow)
  useReviewKeyboard({
    enabled: Boolean(active),
    candidateCount: active?.candidates.length ?? 0,
    onPick: (i) => { if (active?.candidates[i]) { dispatch({ type: "pickCandidate", row: active.row_number, code: active.candidates[i].article_code }); gotoNext() } },
    onConfirm: () => { if (active) { dispatch({ type: "confirmArbiter", row: active.row_number }); gotoNext() } },
    onNext: gotoNext,
  })

  const chip = (key: ReviewState["filter"], label: string) => (
    <button
      onClick={() => dispatch({ type: "setFilter", filter: key })}
      className={"rounded-full border px-3 py-1.5 text-xs " + (state.filter === key ? "border-primary bg-primary text-primary-foreground" : "border-border text-[var(--ds-text-2)]")}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--ds-hairline)] px-4 py-3">
        <span className="text-sm">{state.fileName}</span>
        <span className="text-xs text-muted-foreground">· {state.rows.length} строк СМР</span>
        <div className="flex gap-2">
          <span className="rounded-full bg-[color-mix(in_srgb,var(--success)_16%,transparent)] px-2.5 py-1 text-xs text-[var(--success)]">{c.confident} уверенных</span>
          <span className="rounded-full bg-[color-mix(in_srgb,var(--warning)_18%,transparent)] px-2.5 py-1 text-xs text-[var(--warning)]">{c.review} проверить</span>
          <span className="rounded-full bg-[color-mix(in_srgb,var(--destructive)_16%,transparent)] px-2.5 py-1 text-xs text-destructive">{c.no_match} без пары</span>
        </div>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" onClick={onNewEstimate}><Plus className="size-4" />Новая смета</Button>
          <Button size="sm" onClick={onExport}><Download className="size-4" />Выгрузить Excel</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex gap-2">
          {chip("all", `Все · ${state.rows.length}`)}
          {chip("review", `Проверить · ${c.review}`)}
          {chip("no_match", `Без пары · ${c.no_match}`)}
        </div>
        <span className="ml-2 text-xs text-muted-foreground">проверено {reviewed} из {total}</span>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2.5 font-normal">#</th>
            <th className="px-4 py-2.5 font-normal">Работа из сметы</th>
            <th className="px-4 py-2.5 font-normal">Статья справочника СМР</th>
            <th className="px-4 py-2.5 text-right font-normal">Score</th>
            <th className="px-4 py-2.5 font-normal">Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <ReviewRow
              key={row.row_number}
              row={row}
              decision={decisionFor(state, row)}
              expanded={activeRow === row.row_number}
              onToggle={() => setActiveRow(activeRow === row.row_number ? null : row.row_number)}
              onPickCandidate={(code) => { dispatch({ type: "pickCandidate", row: row.row_number, code }); gotoNext() }}
              onManualPick={(cand) => { dispatch({ type: "manualPick", row: row.row_number, candidate: cand }); gotoNext() }}
              onConfirmNoMatch={() => { dispatch({ type: "confirmNoMatch", row: row.row_number }); gotoNext() }}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 4: Запустить тест — PASS**

Run: `npm run test -- ReviewScreen`
Expected: PASS (3 теста). Затем `npm run typecheck` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/estimate/ReviewScreen.tsx src/pages/estimate/ReviewScreen.test.tsx
git commit -m "feat(review): главный экран проверки — таблица, фильтры, прогресс, клавиатура"
```

---

### Task 9: Экраны «Старт» и «Обработка»

**Files:**
- Create: `frontend/src/pages/estimate/StartScreen.tsx`
- Create: `frontend/src/pages/estimate/ProcessingScreen.tsx`
- Test: `frontend/src/pages/estimate/StartProcessing.test.tsx`

**Interfaces:**
- Produces:
  - `interface StartScreenProps { onFile: (file: File) => void }` — `export function StartScreen(props): JSX.Element`
  - `interface ProcessingScreenProps { progress: import("@/lib/mock/api").Progress; fileName: string }` — `export function ProcessingScreen(props): JSX.Element`
- Поведение Start: dropzone + `<input type="file">`; drag-over подсветка; выбор/дроп .xlsx → `onFile`. Processing: три фазы с прогресс-барами; ETA-число только когда `progress.etaSeconds !== null`.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/pages/estimate/StartProcessing.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"

describe("StartScreen", () => {
  it("выбор файла вызывает onFile", async () => {
    const onFile = vi.fn()
    render(<StartScreen onFile={onFile} />)
    const input = screen.getByLabelText(/файл сметы/i) as HTMLInputElement
    await userEvent.upload(input, new File(["x"], "смета.xlsx"))
    expect(onFile).toHaveBeenCalled()
  })
})

describe("ProcessingScreen", () => {
  it("на фазе embedding ETA-число не показывается", () => {
    render(<ProcessingScreen fileName="смета.xlsx" progress={{ phase: "embedding", done: 10, total: 15, etaSeconds: null }} />)
    expect(screen.queryByText(/сек/i)).not.toBeInTheDocument()
  })
  it("на фазе matching показывается ETA-число", () => {
    render(<ProcessingScreen fileName="смета.xlsx" progress={{ phase: "matching", done: 5, total: 15, etaSeconds: 8 }} />)
    expect(screen.getByText(/сек/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- StartProcessing`
Expected: FAIL — модули не найдены.

- [ ] **Step 3: Реализовать `StartScreen.tsx`**

```tsx
// frontend/src/pages/estimate/StartScreen.tsx
import { useState } from "react"
import { UploadCloud } from "lucide-react"

interface StartScreenProps { onFile: (file: File) => void }

export function StartScreen({ onFile }: StartScreenProps) {
  const [hot, setHot] = useState(false)
  return (
    <div className="p-8">
      <label
        htmlFor="estimate-file"
        onDragOver={(e) => { e.preventDefault(); setHot(true) }}
        onDragLeave={() => setHot(false)}
        onDrop={(e) => { e.preventDefault(); setHot(false); const f = e.dataTransfer.files?.[0]; if (f) onFile(f) }}
        className={"flex min-h-64 cursor-pointer flex-col items-center justify-center gap-3 rounded-lg border border-dashed text-center " + (hot ? "border-primary bg-[color-mix(in_srgb,var(--primary)_6%,transparent)]" : "border-[var(--ds-border-strong)]")}
      >
        <UploadCloud className="size-7 text-muted-foreground" />
        <div className="text-foreground">{hot ? "Отпустите файл сметы" : "Перетащите смету или выберите файл"}</div>
        <div className="font-mono text-xs text-muted-foreground">.xlsx · .xls — обрабатываются строки «Вид раздела = СМР»</div>
        <input
          id="estimate-file"
          aria-label="файл сметы"
          type="file"
          accept=".xlsx,.xls"
          className="sr-only"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f) }}
        />
      </label>
    </div>
  )
}
```

- [ ] **Step 4: Реализовать `ProcessingScreen.tsx`**

```tsx
// frontend/src/pages/estimate/ProcessingScreen.tsx
import type { Progress } from "@/lib/mock/api"

interface ProcessingScreenProps { progress: Progress; fileName: string }

const PHASES: { key: Progress["phase"]; label: string }[] = [
  { key: "parsing", label: "Отбор строк СМР" },
  { key: "embedding", label: "Векторизация" },
  { key: "matching", label: "Поиск + LLM-арбитр" },
]
const order: Progress["phase"][] = ["parsing", "embedding", "matching", "done"]

export function ProcessingScreen({ progress, fileName }: ProcessingScreenProps) {
  const curIdx = order.indexOf(progress.phase)
  return (
    <div className="mx-auto max-w-md p-10">
      <div className="mb-6 text-sm">{fileName}</div>
      {PHASES.map((ph) => {
        const phIdx = order.indexOf(ph.key)
        const done = phIdx < curIdx
        const active = ph.key === progress.phase
        const pct = done ? 100 : active ? Math.round((progress.done / progress.total) * 100) : 0
        return (
          <div key={ph.key} className="mb-3">
            <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
              {done ? "✓ " : ""}{ph.label}{active ? ` · ${progress.done}/${progress.total}` : ""}
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-secondary">
              <div className="h-1.5 bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })}
      {progress.etaSeconds !== null && progress.phase === "matching" && (
        <div className="mt-3 font-mono text-xs text-muted-foreground">≈ {Math.ceil(progress.etaSeconds)} сек осталось</div>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Запустить тесты — PASS**

Run: `npm run test -- StartProcessing`
Expected: PASS (3 теста). Затем `npm run typecheck` — PASS.

- [ ] **Step 6: Commit**

```bash
git add src/pages/estimate/StartScreen.tsx src/pages/estimate/ProcessingScreen.tsx src/pages/estimate/StartProcessing.test.tsx
git commit -m "feat(estimate): экраны старта (dropzone) и обработки (прогресс + ETA после поиска)"
```

---

### Task 10: Экран «Выгрузка / готово»

**Files:**
- Create: `frontend/src/pages/estimate/DoneScreen.tsx`
- Test: `frontend/src/pages/estimate/DoneScreen.test.tsx`

**Interfaces:**
- Consumes: `ReviewState`, `decisionFor` (Task 5).
- Produces:
  ```typescript
  interface DoneScreenProps { state: ReviewState; onExport: () => void; onNewEstimate: () => void }
  export function DoneScreen(props: DoneScreenProps): JSX.Element
  ```
- Поведение: крупные числа (сопоставлено = confirmed-решения; без пары = no_match-решения), кнопка «Скачать обогащённый .xlsx» → `onExport`, ссылка «Загрузить следующую смету» → `onNewEstimate`.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/pages/estimate/DoneScreen.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DoneScreen } from "@/pages/estimate/DoneScreen"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

describe("DoneScreen", () => {
  it("кнопки выгрузки и новой сметы работают", async () => {
    const onExport = vi.fn(), onNew = vi.fn()
    render(<DoneScreen state={initReview("смета.xlsx", MOCK_ROWS)} onExport={onExport} onNewEstimate={onNew} />)
    await userEvent.click(screen.getByRole("button", { name: /Скачать/ }))
    expect(onExport).toHaveBeenCalled()
    await userEvent.click(screen.getByRole("button", { name: /следующую смету/ }))
    expect(onNew).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- DoneScreen`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `DoneScreen.tsx`**

```tsx
// frontend/src/pages/estimate/DoneScreen.tsx
import { Download } from "lucide-react"
import type { ReviewState } from "@/lib/types"
import { decisionFor } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"

interface DoneScreenProps { state: ReviewState; onExport: () => void; onNewEstimate: () => void }

export function DoneScreen({ state, onExport, onNewEstimate }: DoneScreenProps) {
  const matched = state.rows.filter((r) => decisionFor(state, r).kind === "confirmed").length
  const noPair = state.rows.filter((r) => decisionFor(state, r).kind === "no_match").length
  return (
    <div className="mx-auto max-w-md p-10 text-center">
      <div className="mb-6 flex justify-center gap-10">
        <div><div className="font-display text-4xl text-[var(--success)]">{matched}</div><div className="text-xs uppercase tracking-wide text-muted-foreground">сопоставлено</div></div>
        <div><div className="font-display text-4xl text-destructive">{noPair}</div><div className="text-xs uppercase tracking-wide text-muted-foreground">без пары</div></div>
      </div>
      <p className="mb-5 text-sm text-muted-foreground">Исходный Excel + колонки: код статьи, наименование, score, статус, топ-3 альтернативы.</p>
      <Button onClick={onExport}><Download className="size-4" />Скачать обогащённый .xlsx</Button>
      <div className="mt-4">
        <button onClick={onNewEstimate} className="text-sm text-[var(--ds-accent-hover)]">＋ Загрузить следующую смету</button>
      </div>
    </div>
  )
}
```

> Примечание для исполнителя: кнопка названа «Скачать обогащённый .xlsx», но мок отдаёт CSV (стенд-ин). Это осознанно — прод заменит `onExport` на вызов бэкенд-эндпоинта `.xlsx` (бэкенд-гейт из спеки).

- [ ] **Step 4: Запустить тест — PASS**

Run: `npm run test -- DoneScreen`
Expected: PASS. Затем `npm run typecheck` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/estimate/DoneScreen.tsx src/pages/estimate/DoneScreen.test.tsx
git commit -m "feat(estimate): экран выгрузки/готово"
```

---

### Task 11: Оркестратор потока сметы + восстановление сессии + guard

**Files:**
- Create: `frontend/src/pages/estimate/EstimateFlow.tsx`
- Test: `frontend/src/pages/estimate/EstimateFlow.test.tsx`

**Interfaces:**
- Consumes: все экраны потока (Task 8–10), `matchEstimate`/`exportEstimateCsv`/`downloadCsv` (Task 3), `initReview`/`reviewReducer`/`progress` (Task 5), `saveReview`/`loadReview`/`clearReview` (Task 4).
- Produces: `export function EstimateFlow(): JSX.Element`
- Поведение: фазы `start → processing → review → done`. При старте сессии — если `loadReview()` вернул состояние, сразу `review` (восстановление). После обработки — `initReview` + `saveReview`. На `review` каждое изменение — `saveReview`. Выгрузка → `done`. «Новая смета» → `clearReview()` + `start`. `beforeunload` guard навешивается, пока есть незавершённые решения (`progress.reviewed < progress.total`).

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/pages/estimate/EstimateFlow.test.tsx
import { afterEach, describe, expect, it } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { clearReview } from "@/lib/session"

afterEach(() => clearReview())

describe("EstimateFlow", () => {
  it("проходит путь старт → обработка → проверка", async () => {
    render(<EstimateFlow />)
    const input = screen.getByLabelText(/файл сметы/i)
    await userEvent.upload(input, new File(["x"], "смета.xlsx"))
    // после мок-обработки появляется главный экран проверки
    await waitFor(() => expect(screen.getByText(/проверено/i)).toBeInTheDocument(), { timeout: 5000 })
  })

  it("восстанавливает ревью из sessionStorage при монтировании", async () => {
    const { unmount } = render(<EstimateFlow />)
    await userEvent.upload(screen.getByLabelText(/файл сметы/i), new File(["x"], "смета.xlsx"))
    await waitFor(() => expect(screen.getByText(/проверено/i)).toBeInTheDocument(), { timeout: 5000 })
    unmount()
    render(<EstimateFlow />) // новый маунт — должен сразу показать ревью
    expect(screen.getByText(/проверено/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- EstimateFlow`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Реализовать `EstimateFlow.tsx`**

```tsx
// frontend/src/pages/estimate/EstimateFlow.tsx
import { useEffect, useReducer, useRef, useState } from "react"
import type { Progress } from "@/lib/mock/api"
import { downloadCsv, exportEstimateCsv, matchEstimate } from "@/lib/mock/api"
import { initReview, progress, reviewReducer } from "@/lib/reviewState"
import { clearReview, loadReview, saveReview } from "@/lib/session"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { DoneScreen } from "@/pages/estimate/DoneScreen"

type Phase = "start" | "processing" | "review" | "done"

export function EstimateFlow() {
  const restored = useRef(loadReview())
  const [phase, setPhase] = useState<Phase>(restored.current ? "review" : "start")
  const [fileName, setFileName] = useState(restored.current?.fileName ?? "")
  const [prog, setProg] = useState<Progress>({ phase: "parsing", done: 0, total: 0, etaSeconds: null })
  const [state, dispatch] = useReducer(reviewReducer, undefined, () => restored.current ?? initReview("", []))

  // персист ревью на каждое изменение
  useEffect(() => {
    if (phase === "review" || phase === "done") saveReview(state)
  }, [state, phase])

  // guard от случайного ухода с незавершённой проверкой
  useEffect(() => {
    const { reviewed, total } = progress(state)
    if (phase !== "review" || reviewed >= total) return
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = "" }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [phase, state])

  async function handleFile(file: File) {
    setFileName(file.name)
    setPhase("processing")
    const rows = await matchEstimate(file, setProg)
    // Чистая загрузка нового состояния в reducer (без мутаций): action "load" из Task 5.
    const fresh = initReview(file.name, rows)
    dispatch({ type: "load", state: fresh })
    saveReview(fresh)
    setPhase("review")
  }

  function handleNew() {
    clearReview()
    setFileName("")
    setPhase("start")
  }

  function handleExport() {
    downloadCsv(`${fileName.replace(/\.[^.]+$/, "")}_сопоставлено.csv`, exportEstimateCsv(state))
    setPhase("done")
  }

  if (phase === "start") return <StartScreen onFile={handleFile} />
  if (phase === "processing") return <ProcessingScreen fileName={fileName} progress={prog} />
  if (phase === "done") return <DoneScreen state={state} onExport={handleExport} onNewEstimate={handleNew} />
  return <ReviewScreen state={state} dispatch={dispatch} onExport={handleExport} onNewEstimate={handleNew} />
}
```

> Реинициализация reducer — через `dispatch({ type: "load", state: fresh })` (action
> `load` определён в Task 5). Никаких мутаций состояния: `load` возвращает новое
> состояние целиком — чисто и предсказуемо.

- [ ] **Step 4: Запустить тесты — PASS**

Run: `npm run test -- EstimateFlow` затем `npm run test -- reviewState`
Expected: оба PASS. Затем `npm run typecheck` — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pages/estimate/EstimateFlow.tsx
git commit -m "feat(estimate): оркестратор потока + восстановление сессии + beforeunload guard"
```

---

### Task 12: Вход и AuthGate (мок)

**Files:**
- Create: `frontend/src/lib/mock/auth.ts`
- Create: `frontend/src/components/auth/LoginScreen.tsx`
- Create: `frontend/src/components/auth/AuthGate.tsx`
- Test: `frontend/src/components/auth/AuthGate.test.tsx`

**Interfaces:**
- Produces:
  - `lib/mock/auth.ts`: `const AUTH_KEY = "ciw.auth.v1"`; `login(email: string, password: string): Promise<boolean>` (мок: непустые → true, задержка 150мс); `isAuthed(): boolean`; `logout(): void`
  - `interface LoginScreenProps { onSuccess: () => void }` — `export function LoginScreen(props): JSX.Element`
  - `interface AuthGateProps { children: React.ReactNode }` — `export function AuthGate(props): JSX.Element`
- Поведение: `AuthGate` показывает `LoginScreen`, пока `isAuthed()` ложно; после успеха — `children`.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/components/auth/AuthGate.test.tsx
import { afterEach, describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AuthGate } from "@/components/auth/AuthGate"
import { logout } from "@/lib/mock/auth"

afterEach(() => logout())

describe("AuthGate", () => {
  it("показывает вход, затем контент после логина", async () => {
    render(<AuthGate><div>Секретный контент</div></AuthGate>)
    expect(screen.queryByText("Секретный контент")).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/логин/i), "operator")
    await userEvent.type(screen.getByLabelText(/пароль/i), "secret")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByText("Секретный контент")).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- AuthGate`
Expected: FAIL — модули не найдены.

- [ ] **Step 3: Реализовать `lib/mock/auth.ts`**

```typescript
// frontend/src/lib/mock/auth.ts
export const AUTH_KEY = "ciw.auth.v1"

export async function login(email: string, password: string): Promise<boolean> {
  await new Promise((r) => setTimeout(r, 150))
  if (email.trim() && password.trim()) {
    localStorage.setItem(AUTH_KEY, "mock-token")
    return true
  }
  return false
}

export function isAuthed(): boolean {
  return Boolean(localStorage.getItem(AUTH_KEY))
}

export function logout(): void {
  localStorage.removeItem(AUTH_KEY)
}
```

- [ ] **Step 4: Реализовать `LoginScreen.tsx`**

```tsx
// frontend/src/components/auth/LoginScreen.tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { login } from "@/lib/mock/auth"

interface LoginScreenProps { onSuccess: () => void }

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true); setError(false)
    const ok = await login(email, password)
    setBusy(false)
    if (ok) onSuccess()
    else setError(true)
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы</div>
      <div className="mb-5 text-xs text-muted-foreground">Автоматизатор строительных смет</div>
      <form onSubmit={submit} className="flex w-60 flex-col gap-3">
        <label className="text-xs text-[var(--ds-text-2)]">Логин
          <Input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" />
        </label>
        <label className="text-xs text-[var(--ds-text-2)]">Пароль
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1" />
        </label>
        {error && <p className="text-xs text-destructive">Неверный логин или пароль</p>}
        <Button type="submit" disabled={busy}>Войти</Button>
      </form>
    </div>
  )
}
```

- [ ] **Step 5: Реализовать `AuthGate.tsx`**

```tsx
// frontend/src/components/auth/AuthGate.tsx
import { useState } from "react"
import { isAuthed } from "@/lib/mock/auth"
import { LoginScreen } from "@/components/auth/LoginScreen"

interface AuthGateProps { children: React.ReactNode }

export function AuthGate({ children }: AuthGateProps) {
  const [authed, setAuthed] = useState(isAuthed())
  if (!authed) return <LoginScreen onSuccess={() => setAuthed(true)} />
  return <>{children}</>
}
```

- [ ] **Step 6: Запустить тест — PASS**

Run: `npm run test -- AuthGate`
Expected: PASS. Затем `npm run typecheck` — PASS.

- [ ] **Step 7: Commit**

```bash
git add src/lib/mock/auth.ts src/components/auth
git commit -m "feat(auth): мок-вход и AuthGate"
```

---

### Task 13: Оболочка приложения + сборка + переезд справочника

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx` (переписать)
- Modify: `frontend/src/pages/ArticlesPage.tsx` (переписать под мок-API + MR DS)
- Delete: `frontend/src/pages/EstimatePage.tsx`, `frontend/src/pages/EstimatePage.test.tsx`
- Create: `frontend/src/App.test.tsx`

**Interfaces:**
- Consumes: `AuthGate` (Task 12), `EstimateFlow` (Task 11), `MOCK_ARTICLES` (Task 2).
- Produces:
  - `interface AppShellProps { tab: "estimate" | "articles"; onTab: (t: "estimate" | "articles") => void; children: React.ReactNode }` — `export function AppShell(props): JSX.Element`
  - `export function App(): JSX.Element` — `AuthGate` → `AppShell` → активная вкладка.
  - `ArticlesPage` — список из `MOCK_ARTICLES` + форма добавления (локальный стейт, без сети) + удаление.

- [ ] **Step 1: Написать падающий тест**

```typescript
// frontend/src/App.test.tsx
import { afterEach, describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { App } from "@/App"
import { AUTH_KEY } from "@/lib/mock/auth"
import { clearReview } from "@/lib/session"

afterEach(() => { localStorage.clear(); clearReview() })

describe("App", () => {
  it("после входа показывает поток сметы и переключает на справочник", async () => {
    localStorage.setItem(AUTH_KEY, "mock-token") // считаем, что уже вошли
    render(<App />)
    // поток сметы стартует с dropzone
    expect(screen.getByLabelText(/файл сметы/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Справочник/ }))
    expect(screen.getByText(/Новая статья справочника/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — FAIL**

Run: `npm run test -- App`
Expected: FAIL — `@/App` экспортирует другое / `AppShell` не найден.

- [ ] **Step 3: Реализовать `AppShell.tsx`**

```tsx
// frontend/src/components/AppShell.tsx
import { FileSpreadsheet, Library } from "lucide-react"
import { logout } from "@/lib/mock/auth"

interface AppShellProps {
  tab: "estimate" | "articles"
  onTab: (t: "estimate" | "articles") => void
  children: React.ReactNode
}

export function AppShell({ tab, onTab, children }: AppShellProps) {
  const link = (key: "estimate" | "articles", label: string, Icon: typeof FileSpreadsheet) => (
    <button
      onClick={() => onTab(key)}
      className={"flex items-center gap-1.5 border-b-2 pb-2 text-sm " + (tab === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground")}
    >
      <Icon className="size-4" />{label}
    </button>
  )
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-5 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-6 py-3">
        <span className="font-display text-base">MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы</span>
        <nav className="flex gap-4">
          {link("estimate", "Смета", FileSpreadsheet)}
          {link("articles", "Справочник", Library)}
        </nav>
        <button onClick={() => { logout(); location.reload() }} className="ml-auto text-xs text-muted-foreground hover:text-foreground">Выйти</button>
      </header>
      <main>{children}</main>
    </div>
  )
}
```

- [ ] **Step 4: Переписать `ArticlesPage.tsx`** (мок-данные, без сети)

```tsx
// frontend/src/pages/ArticlesPage.tsx
import { useState } from "react"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Candidate } from "@/lib/types"
import { MOCK_ARTICLES } from "@/lib/mock/fixtures"

const EMPTY = { article_code: "", name: "", section_name: "" }

export function ArticlesPage() {
  const [articles, setArticles] = useState<Candidate[]>(MOCK_ARTICLES)
  const [form, setForm] = useState(EMPTY)

  function add(e: React.FormEvent) {
    e.preventDefault()
    if (!form.article_code || !form.name) return
    setArticles((a) => [{ ...form, score: 0 }, ...a])
    setForm(EMPTY)
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="font-display mb-1 text-lg">Новая статья справочника</h2>
      <p className="mb-3 text-sm text-muted-foreground">Эталонные статьи СМР. (Мок: добавление локальное, без сети.)</p>
      <form onSubmit={add} className="mb-6 grid gap-3 sm:grid-cols-[160px_1fr_1fr_auto]">
        <Input placeholder="Код (СМР-01-001)" value={form.article_code} onChange={(e) => setForm({ ...form, article_code: e.target.value })} />
        <Input placeholder="Наименование" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input placeholder="Раздел" value={form.section_name} onChange={(e) => setForm({ ...form, section_name: e.target.value })} />
        <Button type="submit"><Plus className="size-4" />Добавить</Button>
      </form>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2.5 font-normal">Код</th>
            <th className="px-4 py-2.5 font-normal">Наименование</th>
            <th className="px-4 py-2.5 font-normal">Раздел</th>
            <th className="w-10" />
          </tr>
        </thead>
        <tbody>
          {articles.map((a) => (
            <tr key={a.article_code} className="border-t border-[var(--ds-hairline)]">
              <td className="px-4 py-2 font-mono text-xs">{a.article_code}</td>
              <td className="px-4 py-2">{a.name}</td>
              <td className="px-4 py-2 text-muted-foreground">{a.section_name}</td>
              <td className="px-4 py-2">
                <button aria-label="Удалить" onClick={() => setArticles((arr) => arr.filter((x) => x.article_code !== a.article_code))}>
                  <Trash2 className="size-4 text-destructive" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ArticlesPage
```

- [ ] **Step 5: Переписать `App.tsx`**

```tsx
// frontend/src/App.tsx
import { useState } from "react"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"

export function App() {
  const [tab, setTab] = useState<"estimate" | "articles">("estimate")
  return (
    <AuthGate>
      <AppShell tab={tab} onTab={setTab}>
        {tab === "estimate" ? <EstimateFlow /> : <ArticlesPage />}
      </AppShell>
    </AuthGate>
  )
}

export default App
```

- [ ] **Step 6: Удалить старые файлы**

Run (из `frontend/`):
```bash
rm src/pages/EstimatePage.tsx src/pages/EstimatePage.test.tsx
```

- [ ] **Step 7: Запустить весь набор тестов + типы + линт + сборку**

Run:
```bash
npm run test && npm run typecheck && npm run lint && npm run build
```
Expected: всё PASS. (Если линт ругается на неиспользуемый `progress`-импорт или подобное — убрать неиспользуемое.)

- [ ] **Step 8: Ручная проверка всего потока**

Run: `npm run dev`. Проверить: вход → dropzone → загрузка `temp/Смета — копия.xlsx` (или любого) → экран обработки → проверка (раскрытие спорной, выбор 1·2·3, ручной поиск, фильтры, прогресс) → выгрузить (скачивается CSV) → готово → новая смета. Перезагрузить вкладку на этапе проверки — ревью восстанавливается.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(app): оболочка MR DS, AuthGate, переезд справочника на моки; удалён старый EstimatePage"
```

---

## Self-Review (выполнено автором плана)

**Покрытие спеки:**
- Экран 00 Вход → Task 12. 01 Старт → Task 9. 02 Обработка (ETA после поиска) → Task 9. 03 Проверка (таблица, фильтры, прогресс, раскрытие, кандидаты, rationale, score-вторичный, клавиатура, escape-hatch, подтверждение «без пары») → Tasks 5–8. 04 Выгрузка (формат, топ-3 альтернативы, score пустой для ручного) → Tasks 3, 10. 05 Справочник → Task 13.
- Визуальный язык MR DS (тема, шрифты, токены) → Task 1.
- Долговечность сессии (guard, очистка при «новой смете») → Tasks 4, 11. **Хранилище в прототипе — `sessionStorage` как осознанное упрощение (15 фикстур, нет бэкенда), а НЕ по разрешению спеки.** Спека требует IndexedDB для прода (тысячи строк). Помечено как production-гейт в Task 4.
- «Нет совпадения» требует подтверждения и входит в счётчик → Tasks 5, 7.
- Виртуализация — **условная**, в наблюдаемом диапазоне (десятки–сотни) не реализуется (спека); при тысячах строк — отдельная доработка, в план v1 не входит (зафиксировано здесь намеренно).
- Бэкенд-гейты (реальная выгрузка .xlsx, поиск статьи, rationale, прогон-замер распределения) — **вне плана** (моки), помечено в Global Constraints и примечаниях.

**Скан плейсхолдеров:** код приведён полностью в каждом шаге; «примечание по реинициализации reducer» сопровождается конкретным шагом 4 Task 11 с точной правкой.

**Согласованность типов:** `MatchRow`/`Candidate`/`Decision`/`ReviewState` определены в Task 2 и используются единообразно; `ReviewAction` определён в Task 5 и расширен в Task 11 (`load`); `Progress` определён в Task 3 и потребляется в Tasks 9, 11; имена функций (`initReview`, `reviewReducer`, `decisionFor`, `progress`, `filteredRows`, `statusLabel`, `matchEstimate`, `searchArticles`, `exportEstimateCsv`, `downloadCsv`, `saveReview`/`loadReview`/`clearReview`, `login`/`isAuthed`/`logout`) согласованы между задачами.

**Порядок исполнения:** 1 → 2 → 5 → 3 → 4 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13. (Task 3 зависит от Task 5 — отмечено явно.)
