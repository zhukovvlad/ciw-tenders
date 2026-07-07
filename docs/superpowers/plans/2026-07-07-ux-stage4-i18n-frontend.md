# Этап 4 UX PR-2 — Фронтенд i18n (ru + tr) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Локализовать UI-хром фронтенда на русский и турецкий через `react-i18next`, с маппингом машинных кодов ошибок бэкенда (PR-1, уже в `main`) на локализованные тексты.

**Architecture:** `i18next` + `react-i18next` + `i18next-browser-languagedetector`, статические словари `ru.json`/`tr.json` (один файл на язык, секции по областям). Все русские UI-литералы уезжают в словарь 1:1 без редактуры формулировок. Не-React точки (`statusLabel`, `client.ts`) не зовут `t()` — они возвращают **ключи** или **коды**, а `t()` зовёт рендерящий компонент (чистые функции остаются чистыми, подписка на смену языка автоматическая). Показ ошибок API — единая цепочка фолбэков `t("errors."+code)` → русский `detail` бэка → `t("errors.generic")`. Извлечение — по экранам, с зелёными typecheck/тестами на каждом шаге.

**Tech Stack:** React 19.2, Vite 8, TypeScript ~6, react-router-dom 7, Vitest 3.2 + React Testing Library, Tailwind v4 + shadcn/ui, sonner (toasts), zod + react-hook-form.

**Спека:** [2026-07-06-ux-stage4-i18n-design.md](../specs/2026-07-06-ux-stage4-i18n-design.md) §4 — дизайн PR-2 (контракт кодов — таблица §3.4). PR-1 (бэкенд-коды) смержен в `main` (PR #32).

## Global Constraints

- **Ветка от `main`:** `feat/i18n-frontend` (PR-1 уже в `main`). Один PR → `main`.
- **Инвариант формулировок:** извлечение строк **1:1 без редактуры** — русский текст в словаре байт-в-байт как в коде. Редактура формулировок — отдельно, вне этого этапа (иначе краснеют существующие RTL-тесты, завязанные на тексты). Где тест ассертит русский текст — он остаётся зелёным (vitest инициализирует i18n на `ru`).
- **Не-React точки не зовут `t()`:** `statusLabel()` возвращает i18n-**ключ** (`"statuses.fromFund"`), `t()` зовёт рендерящий компонент; `client.ts`/`estimates.ts` бросают `ApiError` с **кодом**, текст резолвит компонент через хелпер. Любой не-React модуль, чей результат рендерится, обязывает рендерящий компонент звать `useTranslation()` хотя бы ради подписки на смену языка.
- **Один статус — один ключ:** тексты статусов только в секциях `statuses.*` / `structure.*`; `STATUS_META`, `statusLabel`, грид, полоса, StructureNotice ссылаются на общие ключи. Никаких `statuses.grid.*`/`statuses.strip.*`-дублей. Структуры бейджей (variant/clickable/тона) остаются на месте — переводится только текст.
- **Чётность словарей:** `ru.json` и `tr.json` имеют идентичные множества ключей и идентичные наборы интерполяций (`{{count}}`, `{{name}}`…) в парных строках. Гарантируется тестом `locales/parity.test.ts` (Task 1) — краснеет на «добавил в ru, забыл в tr».
- **Секция `errors.*` — без интерполяций:** `apiErrorText` зовёт `t(key)` без values → плейсхолдеры остались бы пустыми/сырыми. Тексты кодов — обобщённые формулировки без `{{...}}`; конкретика (значение) — в русском `detail` бэка (цепочка покажет его, если ключа нет) либо на экране формы.
- **Локализация `document.title`:** заголовок вкладки локализуется динамически (`document.title = t("common.appTitle")` в обработчике `languageChanged`, Task 1); статический `<title>` в `index.html` — лишь pre-hydration плейсхолдер. Task 9-grep кириллицы НЕ считает `index.html`-заголовок остатком.
- **Локализация confirm-word (WipeCatalog):** слово-подтверждение и инструкция — из словаря; сравнение с вводом читает `t()`-значение (tr-оператор вводит турецкое слово).
- **Имя экспортного файла:** нейтральный латинский суффикс `_matched.xlsx` (не локализуется, безопасно для файловых систем). Заменяет текущий кириллический `_сопоставлено.xlsx`.
- **Не извлекается:** `src/lib/mock/**` (тест-фикстуры), доменный контент (наименования работ/статей из API), `useAuth.ts:17` (dev-throw, не UI). Числа (`toFixed(2)`) — локаль-независимы, не трогаем.
- **Выбор языка:** `localStorage["ciw.ui.lang"]` (переживает логаут; правило «в sessionStorage только JWT» не нарушается). Детект: сохранённый выбор → язык браузера (`tr*` → tr, иначе ru), `fallbackLng: "ru"`, `supportedLngs: ["ru","tr"]`.
- **Соглашения фронта:** TypeScript strict + `erasableSyntaxOnly` (без enum/parameter properties); импорты через `@/`; Prettier `printWidth 80`, `endOfLine lf`; shadcn-компоненты в `src/components/ui/` — вендорные, НЕ править. `npm run typecheck` = `tsc -b`. Тесты: `npx vitest run <файл>`.
- **Windows PowerShell 5.1:** разделитель `;`, не `&&`. Команды фронта — из `frontend/`.
- **Трейлер коммита исполнителя:** `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## File Structure

**Создаются:**
- `frontend/src/lib/i18n.ts` — инициализация i18next (детект, ресурсы, `languageChanged` → `document.documentElement.lang`).
- `frontend/src/locales/ru.json`, `frontend/src/locales/tr.json` — словари. Секции: `common`, `nav`, `auth`, `estimates`, `review`, `articles`, `statuses`, `structure`, `errors`.
- `frontend/src/locales/parity.test.ts` — тест чётности ключей и интерполяций.
- `frontend/src/lib/api/errorText.ts` — хелпер `apiErrorText(err, t, fallbackKey)` (цепочка фолбэков показа ошибок).
- `frontend/src/lib/i18n.test.ts` — тест инициализации/детекта.
- `frontend/src/lib/formatDate.ts` — локале-зависимый форматтер дат.

**Модифицируются (по областям — детали в задачах):** `lib/api/client.ts`, `lib/api/estimates.ts`, `lib/reviewState.ts`, `lib/auth/AuthContext.tsx`, `main.tsx`, `test/setup.ts`, `index.html`, компоненты auth/estimates/articles/review/structure/AppShell + их `*.test.*`.

**Удаляются (Task 8, после миграции всех вызовов):** `frontend/src/lib/plural.ts`, `frontend/src/lib/plural.test.ts`.

---

### Task 1: Фундамент — установка i18next, инициализация, словари-скелет, тест чётности

**Files:**
- Create: `frontend/src/lib/i18n.ts`, `frontend/src/locales/ru.json`, `frontend/src/locales/tr.json`, `frontend/src/locales/parity.test.ts`, `frontend/src/lib/i18n.test.ts`
- Modify: `frontend/src/main.tsx`, `frontend/src/test/setup.ts`, `frontend/index.html`, `frontend/package.json`

**Interfaces:**
- Produces: default export `i18n` из `@/lib/i18n` (инстанс с `resources`, `fallbackLng:"ru"`, `supportedLngs:["ru","tr"]`, детект `localStorage["ciw.ui.lang"]`→navigator); словари `ru.json`/`tr.json` с 9 секциями (на этом шаге — только `common`/`nav`/`errors.generic`/`errors.network`, остальные секции заводятся пустыми объектами `{}`, наполняются в задачах 3–8).

- [ ] **Step 1: Установить зависимости**

Из `frontend/`:
```
npm install i18next@^25 react-i18next@^16 i18next-browser-languagedetector@^8
```
Проверить, что версии совместимы с React 19; зафиксировать в `package.json`.

- [ ] **Step 2: Написать падающий тест инициализации** (`frontend/src/lib/i18n.test.ts`)

```ts
import { describe, expect, it } from "vitest"
import i18n from "@/lib/i18n"

describe("i18n", () => {
  it("инициализирован с ru и поддерживает ru/tr", () => {
    expect(i18n.options.fallbackLng).toContain("ru")
    expect(i18n.options.supportedLngs).toEqual(
      expect.arrayContaining(["ru", "tr"])
    )
  })

  it("резолвит общий ключ и падает на ru как fallback", async () => {
    await i18n.changeLanguage("ru")
    expect(i18n.t("common.cancel")).toBe("Отмена")
    await i18n.changeLanguage("tr")
    expect(i18n.t("common.cancel")).toBe("İptal")
  })

  it("нормализует регион-вариант tr-TR → tr (load: languageOnly)", async () => {
    await i18n.changeLanguage("tr-TR")
    expect(i18n.resolvedLanguage).toBe("tr")
    expect(i18n.t("common.cancel")).toBe("İptal") // турецкий, не fallback ru
    await i18n.changeLanguage("ru")
  })

  it("синхронизирует document.documentElement.lang и title при смене языка", async () => {
    await i18n.changeLanguage("tr")
    expect(document.documentElement.lang).toBe("tr")
    expect(document.title).toBe("MR · Keşifler")
    await i18n.changeLanguage("ru")
    expect(document.title).toBe("MR · Сметы")
  })
})
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/i18n.test.ts`
Expected: FAIL (модуль `@/lib/i18n` не существует).

- [ ] **Step 4: Создать `frontend/src/lib/i18n.ts`**

```ts
import LanguageDetector from "i18next-browser-languagedetector"
import i18n from "i18next"
import { initReactI18next } from "react-i18next"

import ru from "@/locales/ru.json"
import tr from "@/locales/tr.json"

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { ru: { translation: ru }, tr: { translation: tr } },
    fallbackLng: "ru",
    supportedLngs: ["ru", "tr"],
    load: "languageOnly", // tr-TR / ru-RU → базовый tr / ru (иначе регион-вариант
    // не найдётся в supportedLngs и упадёт на fallback ru — турецкий браузер дал бы русский)
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "ciw.ui.lang",
      caches: ["localStorage"],
    },
    interpolation: { escapeValue: false }, // React уже экранирует
  })

i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng
  document.title = i18n.t("common.appTitle") // локализуем title (§ниже)
})
document.documentElement.lang = i18n.language
document.title = i18n.t("common.appTitle")

export default i18n
```

- [ ] **Step 5: Создать `frontend/src/locales/ru.json`** (скелет — секции заводятся, наполняются в задачах 3–8)

```json
{
  "common": {
    "cancel": "Отмена",
    "delete": "Удалить",
    "retry": "Повторить",
    "loading": "Загрузка…",
    "appTitle": "MR · Сметы"
  },
  "nav": {},
  "auth": {},
  "estimates": {},
  "review": {},
  "articles": {},
  "statuses": {},
  "structure": {},
  "errors": {
    "generic": "Что-то пошло не так",
    "network": "Сеть недоступна — проверьте подключение"
  }
}
```

- [ ] **Step 6: Создать `frontend/src/locales/tr.json`** (те же ключи, турецкий черновик)

```json
{
  "common": {
    "cancel": "İptal",
    "delete": "Sil",
    "retry": "Tekrar dene",
    "loading": "Yükleniyor…",
    "appTitle": "MR · Keşifler"
  },
  "nav": {},
  "auth": {},
  "estimates": {},
  "review": {},
  "articles": {},
  "statuses": {},
  "structure": {},
  "errors": {
    "generic": "Bir şeyler ters gitti",
    "network": "Ağ kullanılamıyor — bağlantınızı kontrol edin"
  }
}
```

- [ ] **Step 7: Написать тест чётности** (`frontend/src/locales/parity.test.ts`)

```ts
import { describe, expect, it } from "vitest"

import ru from "./ru.json"
import tr from "./tr.json"

type Json = { [k: string]: string | Json }

function leafPaths(obj: Json, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k
    return typeof v === "string" ? [path] : leafPaths(v, path)
  })
}

function leafValue(obj: Json, path: string): string {
  return path.split(".").reduce<Json | string>((acc, k) => {
    return (acc as Json)[k]
  }, obj) as string
}

function placeholders(s: string): string[] {
  return [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()
}

describe("словари ru/tr", () => {
  it("имеют идентичные множества ключей", () => {
    expect(leafPaths(tr as Json).sort()).toEqual(leafPaths(ru as Json).sort())
  })

  it("имеют совпадающие интерполяции в парных строках", () => {
    for (const path of leafPaths(ru as Json)) {
      expect(placeholders(leafValue(tr as Json, path))).toEqual(
        placeholders(leafValue(ru as Json, path))
      )
    }
  })
})
```

- [ ] **Step 8: Подключить i18n в `main.tsx` и вписать инициализацию в тест-setup**

В `frontend/src/main.tsx` — импортировать `@/lib/i18n` **до** рендера (side-effect init) и обернуть приложение в `I18nextProvider`:
```tsx
import { I18nextProvider } from "react-i18next"
import i18n from "@/lib/i18n"
// ...внутри createRoot(...).render:
<I18nextProvider i18n={i18n}>
  {/* существующее дерево (StrictMode/BrowserRouter/App) */}
</I18nextProvider>
```
В `frontend/src/test/setup.ts` добавить (после существующих импортов):
```ts
import i18n from "@/lib/i18n"

beforeAll(async () => {
  await i18n.changeLanguage("ru")
})
```

- [ ] **Step 9: Поправить `frontend/index.html`** — `<html lang="ru">` (вместо `en`; далее перезаписывается динамически) и `<title>` на осмысленный (заменить плейсхолдер `vite-app`):
```html
<html lang="ru">
<title>MR · Сметы</title>
```

- [ ] **Step 10: Запустить тесты и typecheck**

Run: `cd frontend; npx vitest run src/lib/i18n.test.ts src/locales/parity.test.ts; npm run typecheck`
Expected: PASS (все), typecheck 0 ошибок. Затем полный прогон `npx vitest run` — существующие тесты зелёные (i18n на ru, ключей экранов ещё нет — компоненты пока с литералами).

- [ ] **Step 11: Commit**

```
git add frontend/src/lib/i18n.ts frontend/src/locales frontend/src/lib/i18n.test.ts frontend/src/main.tsx frontend/src/test/setup.ts frontend/index.html frontend/package.json frontend/package-lock.json
git commit -m "feat(i18n): бутстрап react-i18next, словари-скелет ru/tr, тест чётности"
```

---

### Task 2: Контракт ошибок — `ApiError.code`, парсинг в client.ts, хелпер показа

**Files:**
- Modify: `frontend/src/lib/api/client.ts`, `frontend/src/lib/api/estimates.ts`
- Create: `frontend/src/lib/api/errorText.ts`
- Test: `frontend/src/lib/api/client.test.ts` (существует — дополнить), `frontend/src/lib/api/errorText.test.ts` (новый)
- Modify словарь: `errors` секция ru/tr — добавить `estimate_processing_blocked` + ключи всех backend-кодов из §3.4 (см. Step 6).

**Interfaces:**
- Consumes: `i18n` TFunction (тип `TFunction` из `i18next`).
- Produces: `class ApiError extends Error { status: number; code?: string; constructor(status, message, code?) }`; `apiErrorText(err: unknown, t: TFunction, fallbackKey: string): string`.

- [ ] **Step 1: Дополнить `client.test.ts` — падающий тест на парсинг `code`**

```ts
it("парсит code из тела ошибки рядом с detail", async () => {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "Смета не найдена", code: "estimate_not_found" }), {
      status: 404,
      headers: { "content-type": "application/json" },
    })
  )
  await expect(api.get("/estimates/1")).rejects.toMatchObject({
    status: 404,
    message: "Смета не найдена",
    code: "estimate_not_found",
  })
})

it("сетевая ошибка несёт code=network", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("fail"))
  await expect(api.get("/x")).rejects.toMatchObject({ status: 0, code: "network" })
})
```
(Использовать существующий в `client.test.ts` способ мока `fetch` — сверить имена.)

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/api/client.test.ts`
Expected: FAIL (`code` отсутствует на ApiError).

- [ ] **Step 3: Расширить `ApiError` и парсинг в `client.ts`**

```ts
export class ApiError extends Error {
  status: number
  code?: string
  constructor(status: number, message: string, code?: string) {
    super(message)
    this.status = status
    this.code = code
    this.name = "ApiError"
  }
}
```
В обработке `!res.ok`: после чтения `detail` прочитать `code` из того же JSON-тела (если строка) и передать третьим аргументом: `throw new ApiError(res.status, message, typeof body?.code === "string" ? body.code : undefined)`. Сетевой catch — **сохранить прежний русский `message` И добавить код** (та же логика PR-1 «текст не трогаем, code — добавка»): `throw new ApiError(0, "Сеть недоступна — проверьте подключение", "network")`. Цепочка `apiErrorText` предпочтёт ключ `errors.network`; `message` остаётся совместимым фолбэком для ещё-не-мигрированных экранов (Task 3–8) и существующих тестов, ассертящих этот текст (иначе они покраснели бы на Task 2 несанкционированно).

- [ ] **Step 4: Мигрировать `estimates.ts:216`** — poll blocked: **сохранить прежний русский `message` + добавить код** (та же логика, что сетевой случай — иначе тесты/немигрированные экраны увидят пусто):
```ts
import { ApiError } from "./client"
// ...
reject(new ApiError(0, "Обработка сметы заблокирована", "estimate_processing_blocked"))
```

- [ ] **Step 5: Создать хелпер `frontend/src/lib/api/errorText.ts`**

```ts
import type { TFunction } from "i18next"

import { ApiError } from "./client"

/**
 * Единая цепочка показа ошибки API (спека §4.4):
 *   код есть в словаре → русский detail бэка → errors.generic;
 *   не ApiError → экранный fallbackKey.
 */
export function apiErrorText(
  err: unknown,
  t: TFunction,
  fallbackKey: string
): string {
  if (err instanceof ApiError) {
    if (err.code) {
      const key = `errors.${err.code}`
      const translated = t(key)
      if (translated !== key) return translated
    }
    if (err.message) return err.message
    return t("errors.generic")
  }
  return t(fallbackKey)
}
```

- [ ] **Step 6: Наполнить секцию `errors` в ru.json/tr.json** ключами всех backend-кодов из §3.4 + frontend-локальные

ru.json `errors.*` (тексты — на основе столбца «Сегодняшний текст» §3.4; про динамические тексты — см. правило ниже):
`not_authenticated`, `admin_required`, `invalid_credentials`, `account_disabled`, `user_email_exists`, `article_code_exists`, `article_code_not_numeric`, `article_code_would_be_ancestor`, `article_parent_not_found`, `search_query_too_short`, `template_duplicate_code`, `template_orphan_parent`, `template_deletion_guard`, `estimate_not_found`, `estimate_row_not_found`, `file_not_xlsx`, `file_not_zip`, `file_too_large`, `estimate_missing_columns`, `estimate_completed_readonly`, `row_not_matched`, `row_not_reviewable`, `review_unknown_action`, `review_confirm_no_recommendation`, `review_pick_requires_article`, `review_article_not_found`, `estimate_not_completable`, `export_unreviewed_rows`, `storage_unavailable`, `validation_error` + frontend-локальные `estimate_processing_blocked` («Обработка сметы заблокирована»), `network`, `generic`.
**Секция `errors.*` — БЕЗ интерполяций** (`{{...}}` запрещены): `apiErrorText` зовёт `t(key)` без values (значение живёт внутри русского `detail` бэка, а не структурно — хелперу оно недоступно по построению). Тексты с бэковыми подстановками (`article_code_exists` «Статья с кодом … уже существует», `template_duplicate_code` «Дубликат кода в файле: …», `file_too_large` «Файл больше N МБ», `export_unreviewed_rows` «Не просмотрено строк: N» и т.п.) — **обобщённые формулировки без плейсхолдера** (напр. «Статья с таким кодом уже существует», «Дубликат кода в файле», «Файл слишком большой», «Есть непросмотренные строки»). Обоснование: если ключ есть — обобщённый перевод лучше сломанного `{{code}}`; конкретика при необходимости доступна оператору в самой форме. (Динамические значения, известные ФРОНТУ и нужные в UI, локализуются на своих экранах — не в `errors.*`.) Добавить те же ключи в tr.json (турецкий черновик).

- [ ] **Step 7: Тест хелпера** (`frontend/src/lib/api/errorText.test.ts`)

```ts
import type { TFunction } from "i18next"
import { describe, expect, it } from "vitest"

import { ApiError } from "./client"
import { apiErrorText } from "./errorText"

const t = ((k: string) =>
  k === "errors.estimate_not_found"
    ? "Смета не найдена"
    : k === "errors.generic"
      ? "Что-то пошло не так"
      : k === "screen.fallback"
        ? "Не удалось"
        : k) as unknown as TFunction

describe("apiErrorText", () => {
  it("код есть в словаре → перевод по коду", () => {
    expect(apiErrorText(new ApiError(404, "Смета не найдена", "estimate_not_found"), t, "screen.fallback")).toBe("Смета не найдена")
  })
  it("код неизвестен, есть detail → русский detail бэка", () => {
    expect(apiErrorText(new ApiError(400, "Спец-текст бэка", "some_new_code"), t, "screen.fallback")).toBe("Спец-текст бэка")
  })
  it("ApiError без detail и без известного кода → errors.generic", () => {
    expect(apiErrorText(new ApiError(500, "", undefined), t, "screen.fallback")).toBe("Что-то пошло не так")
  })
  it("не ApiError → экранный fallback", () => {
    expect(apiErrorText(new Error("boom"), t, "screen.fallback")).toBe("Не удалось")
  })
})
```

- [ ] **Step 8: Запустить тесты + typecheck**

Run: `cd frontend; npx vitest run src/lib/api/client.test.ts src/lib/api/errorText.test.ts src/locales/parity.test.ts; npm run typecheck`
Expected: PASS. (Вызовы `apiErrorText` в компонентах подключаются по экранам в задачах 3–8; здесь только контракт + хелпер.)

- [ ] **Step 9: Commit**

```
git add frontend/src/lib/api/client.ts frontend/src/lib/api/estimates.ts frontend/src/lib/api/errorText.ts frontend/src/lib/api/errorText.test.ts frontend/src/lib/api/client.test.ts frontend/src/locales
git commit -m "feat(i18n): ApiError.code + парсинг + цепочка apiErrorText, коды §3.4 в словаре"
```

---

### Task 3: Экран авторизации (LoginScreen, AuthGate, AuthContext)

**Files:**
- Modify: `frontend/src/components/auth/LoginScreen.tsx`, `frontend/src/components/auth/AuthGate.tsx`, `frontend/src/lib/auth/AuthContext.tsx`
- Test: соответствующие `*.test.tsx` (`LoginScreen.test.tsx`, `AuthGate.test.tsx`, `AuthContext.test.tsx`) — обновить ассерты на ключи/тексты через рендер
- Modify словарь: секция `auth` + `common.loading` (AuthGate)

**Interfaces:**
- Consumes: `useTranslation` из `react-i18next`; `apiErrorText` (Task 2).

Строки → ключи (`auth.*`, тексты 1:1):
`enterLogin`="Введите логин", `enterPassword`="Введите пароль", `invalidCredentials`="Неверный логин или пароль", `loginFailed`="Не удалось войти, попробуйте позже", `brandHeading`="MR · Сметы", `subtitle`="Автоматизатор строительных смет", `loginLabel`="Логин", `passwordLabel`="Пароль", `submit`="Войти", `backendUnavailable`="Бэкенд недоступен — попробуйте позже". AuthGate `Загрузка…` → `common.loading`.

- [ ] **Step 1: Обновить тест LoginScreen** — оставить ассерты на русский текст (i18n на ru в тестах), убедиться что после извлечения тексты те же. Добавить/сохранить: `getByRole("button", { name: "Войти" })`, `findByText("Неверный логин или пароль")`. (Тексты не меняются 1:1 — существующие ассерты остаются.)

- [ ] **Step 2: Запустить — базлайн зелёный до правок**

Run: `cd frontend; npx vitest run src/components/auth/LoginScreen.test.tsx`
Expected: PASS (до правок — тексты в коде совпадают с ассертами).

- [ ] **Step 3: Извлечь строки в LoginScreen.tsx** — `const { t } = useTranslation()`; zod-сообщения через `t("auth.enterLogin")` и т.д.; JSX-литералы на `t("auth.*")`. Ошибку входа (было L42-43) — через `apiErrorText(err, t, "auth.loginFailed")` (401 → бэк-код `invalid_credentials` из словаря; иначе fallback). **Внимание:** zod-resolver вызывается вне рендера — схему собирать внутри компонента (замыкание на `t`) или через `useMemo`, чтобы сообщения переключались с языком.

- [ ] **Step 4: Извлечь AuthGate.tsx** (`common.loading`) и AuthContext.tsx L36 (`t("auth.backendUnavailable")`) — AuthContext это провайдер; звать `useTranslation` внутри него (React-компонент, хук доступен).

- [ ] **Step 5: Наполнить `auth` в ru.json/tr.json** (ключи выше; tr — черновик).

- [ ] **Step 6: Запустить тесты + typecheck**

Run: `cd frontend; npx vitest run src/components/auth src/lib/auth src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```
git commit -am "feat(i18n): локализация экрана авторизации (auth-секция)"
```

---

### Task 4: Список смет (EstimateList, EstimatesPage) — STATUS_META, даты

**Files:**
- Modify: `frontend/src/components/estimate/EstimateList.tsx`, `frontend/src/pages/estimate/EstimatesPage.tsx`
- Create: `frontend/src/lib/formatDate.ts` (+ `formatDate.test.ts`)
- Test: `EstimateList.test.tsx`, `EstimatesPage.test.tsx` — обновить (STATUS_META теперь ключи → тесты рендерят через t; ассерты русских текстов остаются валидными)
- Modify словарь: `estimates` + `statuses` (общие ключи)

**Interfaces:**
- Consumes: `useTranslation`, `apiErrorText`, `formatDate`.
- Produces: `STATUS_META[status].labelKey: string` (ключ вместо `label`); `formatDate(iso: string, locale: string): string`.

Строки → ключи:
- `statuses.*` (общие, §Global Constraints): `ready`="Готово", `partialError`="Готово с ошибками", `processing`="В обработке" (для `pending` и `running`), `blocked`="Отклонено".
- `estimates.*`: `loadFailed`="Не удалось загрузить сметы", `deleted`="Смета удалена", `deleteFailed`="Не удалось удалить смету", `empty`="Пока нет разобранных смет — загрузите файл выше.", `colFile`="Файл", `colStatus`="Статус", `colReview`="Проверка", `colNodes`="Узлов", `colDate`="Дата", `completed`="Завершена", `reviewedOf`="{{reviewed}} из {{total}}", `deleteAria`="Удалить {{filename}}", `deleteTitle`="Удалить смету?", `deleteBody`="«{{filename}}» будет удалена безвозвратно.", `showMore`="Показать ещё". EstimatesPage: `estimates.openFailed`="Не удалось загрузить смету".

- [ ] **Step 1: Написать тест formatDate** (`frontend/src/lib/formatDate.test.ts`)

```ts
import { describe, expect, it } from "vitest"
import { formatDate } from "./formatDate"

describe("formatDate", () => {
  const iso = "2026-07-07T09:05:00Z"
  it("форматирует по ru-RU", () => {
    expect(formatDate(iso, "ru")).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
  it("форматирует по tr-TR", () => {
    expect(formatDate(iso, "tr")).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
  it("невалидную дату возвращает как есть", () => {
    expect(formatDate("нет", "ru")).toBe("нет")
  })
})
```

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/lib/formatDate.test.ts`
Expected: FAIL (модуль не существует).

- [ ] **Step 3: Создать `frontend/src/lib/formatDate.ts`**

```ts
const LOCALE: Record<string, string> = { ru: "ru-RU", tr: "tr-TR" }

export function formatDate(iso: string, locale: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return new Intl.DateTimeFormat(LOCALE[locale] ?? "ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d)
}
```

- [ ] **Step 4: Мигрировать EstimateList.tsx** — `STATUS_META[x].label` → `labelKey` (значения — ключи `statuses.ready` и т.д.; `pending`/`running` → `statuses.processing`); в рендере бейджа `t(meta.labelKey)` (компонент зовёт `useTranslation`). `metaFor` fallback — вернуть `{ labelKey: undefined }` и в рендере при отсутствии ключа показывать сырой `status`. Таблица/диалог/пусто/«Показать ещё» → `t("estimates.*")`; `reviewedCount из total` → `t("estimates.reviewedOf", { reviewed, total })`; тосты/ошибки → `apiErrorText(err, t, "estimates.loadFailed"/"estimates.deleteFailed")` и `toast.success(t("estimates.deleted"))`. Дата: `formatDate(item.createdAt, i18n.language)` (взять `i18n` из `useTranslation`).

- [ ] **Step 5: Мигрировать EstimatesPage.tsx** (`estimates.openFailed` через apiErrorText).

- [ ] **Step 6: Наполнить `estimates` + `statuses` в ru/tr.**

- [ ] **Step 7: Обновить `EstimateList.test.tsx`** — `STATUS_META` теперь экспортирует `labelKey`; если тест сверял `.label`, переключить на рендер-ассерт (`getByText("Готово")`). Ассерты русских текстов («Готово»,«Отклонено»,«3 из 7»,«Завершена») остаются — тесты на ru.

- [ ] **Step 8: Запустить тесты + typecheck**

Run: `cd frontend; npx vitest run src/components/estimate/EstimateList.test.tsx src/pages/estimate/EstimatesPage.test.tsx src/lib/formatDate.test.ts src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 9: Commit**

```
git commit -am "feat(i18n): список смет + STATUS_META-ключи + локале-зависимые даты"
```

---

### Task 5: Экран сметы — оболочка и фазы (EstimatePage, ProcessingScreen, DoneScreen, QueueDone)

**Files:**
- Modify: `frontend/src/pages/estimate/EstimatePage.tsx`, `ProcessingScreen.tsx`, `DoneScreen.tsx`, `QueueDone.tsx`
- Test: соответствующие `*.test.tsx`
- Modify словарь: секция `estimates` (расширение) / `review` (общие для экрана)

**Interfaces:** Consumes `useTranslation`, `apiErrorText`. Расширяет `DetailDto`/доменную модель детали сметы полем `status_code`→`statusCode` (PR-1 добавил `EstimateDetailOut.status_code`; фронт его пока НЕ читает — `estimates.ts:38-46` DetailDto без него, маппинг `:140-147` без `statusCode`).

Ключи (`estimates.*`/`review.*`, 1:1):
- EstimatePage: `openFailed` (уже), `rowSaveFailed`="Не удалось сохранить решение по строке «{{name}}»", `exportFailed`="Экспорт не удался", `statusChangeFailed`="Не удалось изменить статус сметы", `loadingAria`="Загрузка", `rejected`="Смета отклонена", `errorTitle`="Ошибка", `notFound`="Смета не найдена", `backToAll`="← Ко всем сметам". **Имя файла экспорта:** заменить кириллический суффикс на нейтральный — `` `${base}_matched.xlsx` `` (константа, НЕ из словаря, §Global Constraints).
- **Персист-статус баннера (§4.4)** — заголовок баннера из `statuses.{status_code}`; ключи (тексты — человекочитаемые заголовки, не сырой diagnostic): `statuses.matching_partial_error`="Готово с ошибками", `statuses.matching_unexpected`="Непредвиденная ошибка", `statuses.matching_blocked_dictionary`="Справочник не готов", `statuses.matching_reset_after_crash`="Перезапущено после сбоя". (Ключ ищется динамически строкой-кодом — snake_case, в отличие от camelCase-ключей статусов; это осознанно, т.к. `status_code` из БД — snake_case.)
- ProcessingScreen: `stepSelect`="Отбор строк СМР", `stepVectorize`="Векторизация", `stepMatch`="Поиск + LLM-арбитр", `etaLeft`="≈ {{sec}} сек осталось".
- DoneScreen: `fundUndetermined`="Не удалось определить смету для добавления в фонд", `fundNoDecisions`="Смета не добавлена в фонд: нет подтверждённых решений. Подтвердите или выберите статьи на шаге проверки и включите тумблер снова.", `fundUpdateFailed`="Не удалось обновить фонд решений", `matched`="сопоставлено", `noMatch`="без пары", `exportHint`="Исходный Excel + колонки: код статьи, наименование, score, статус, топ-3 альтернативы.", `downloadXlsx`="Скачать обогащённый .xlsx", `referenceToggle`="Эталонная смета — добавить в фонд решений", `fundHint`="Фонд пополняют решения, принятые оператором при проверке — подтвердите или выберите статьи и вернитесь сюда.", `resumeReview`="Возобновить проверку", `viewRows`="Просмотреть строки", `uploadNext`="＋ Загрузить следующую смету".
- QueueDone: `allResolved`="Все спорные строки решены", `resolvedOf`="Решено {{reviewed}} из {{total}}", `matched`/`noMatch` (общие), `finishReview`="Завершить проверку", `viewTable`="Посмотреть таблицу", `backToLast`="← Вернуться к последнему решению".

- [ ] **Step 1: Обновить тесты этих экранов** — сохранить ассерты русских текстов (i18n ru); где тест ждёт имя скачиваемого файла с `_сопоставлено` — **обновить на `_matched.xlsx`** (санкционированное изменение поведения по решению пользователя).

- [ ] **Step 2: Базлайн — тесты на именах файлов покраснеют на суффиксе**

Run: `cd frontend; npx vitest run src/pages/estimate/EstimatePage.test.tsx`
Expected: возможен FAIL на ассерте имени файла (до правки строки в тесте на `_matched.xlsx`).

- [ ] **Step 3: Извлечь строки** во всех четырёх файлах (`useTranslation`, `t(...)`, ошибки через `apiErrorText`, плюрализованных строк тут нет). Имя файла → `_matched.xlsx`.

- [ ] **Step 3a: Протянуть `status_code` в модель детали** (`estimates.ts`)

В `DetailDto` (после `status_detail`, L43) добавить `status_code?: string | null`. В маппинге доменной детали (рядом с `statusDetail: dto.status_detail ?? null`, L145) добавить `statusCode: dto.status_code ?? null`. Расширить доменный тип детали полем `statusCode: string | null`. (Старый бэк без поля → `null`, фолбэк на текущее поведение.)

- [ ] **Step 3b: Баннер blocked/partial_error по `status_code`** (EstimatePage.tsx, §4.4)

Протянуть `statusCode`/`statusDetail` в объект `meta` (найти его деривацию — маппинг статус→экран в EstimatePage/хелпере — и добавить поля). В ветке баннера (`meta.kind === "blocked" || "error"`, сейчас L227-234) заголовок из кода, сырой detail — вторичным:
```tsx
<AlertTitle>
  {meta.statusCode
    ? t(`statuses.${meta.statusCode}`, {
        defaultValue: meta.kind === "blocked" ? t("estimates.rejected") : t("estimates.errorTitle"),
      })
    : meta.kind === "blocked"
      ? t("estimates.rejected")
      : t("estimates.errorTitle")}
</AlertTitle>
<AlertDescription>
  {/* сырой status_detail как диагностика; при null — текущее поведение */}
  {meta.statusDetail ?? (meta.kind === "blocked" ? (meta.detail ?? "—") : meta.message)}
</AlertDescription>
```
(`defaultValue` в `t()` — фолбэк, если ключа под конкретный код нет: неизвестный будущий `status_code` не покажет сырой ключ.)

- [ ] **Step 4: Наполнить словарь (ru/tr)** — включая `statuses.matching_*` (заголовки баннера).

- [ ] **Step 5: Тесты + typecheck**

Добавить в `EstimatePage.test.tsx` кейс: деталь со `status_code: "matching_partial_error"` → баннер с заголовком `t("statuses.matching_partial_error")` («Готово с ошибками») и сырым `status_detail` в описании; и кейс `status_code: null` → текущее поведение (сырой текст).

Run: `cd frontend; npx vitest run src/pages/estimate/EstimatePage.test.tsx src/pages/estimate/ProcessingScreen.test.tsx src/pages/estimate/DoneScreen.test.tsx src/pages/estimate/QueueDone.test.tsx src/lib/api/estimates.test.ts src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 6: Commit**

```
git commit -am "feat(i18n): оболочка и фазы экрана сметы; экспортное имя _matched.xlsx"
```

---

### Task 6: Ядро ревью — statusLabel→ключи, ReviewScreen (плюрализация), ReviewCard, ReviewGrid, ContextStrip

**Files:**
- Modify: `frontend/src/lib/reviewState.ts` (`statusLabel`), `frontend/src/pages/estimate/ReviewScreen.tsx`, `ReviewCard.tsx`, `ReviewGrid.tsx`, `ContextStrip.tsx`
- Test: `reviewState.test.ts` (ассерты → ключи), `ReviewScreen.test.tsx`, `ReviewCard.test.tsx`, `ReviewGrid.test.tsx`, `ContextStrip.test.tsx`
- Modify словарь: `statuses` (общие), `review`

**Interfaces:**
- Produces: `statusLabel(row, d): string` теперь возвращает **i18n-ключ** (`"statuses.context"` | `"statuses.processing"` | `"statuses.noMatch"` | `"statuses.needsReview"` | `"statuses.manual"` | `"statuses.fromFund"` | `"statuses.confirmedByOperator"`).
- Consumes: `useTranslation`, `pluralizeRu` (пока; native-плюрализация — Step 5).

Ключи статусов (общие с §Global Constraints; тексты 1:1): `statuses.context`="Контекст", `statuses.processing`="В обработке", `statuses.noMatch`="Нет совпадения", `statuses.needsReview`="Требует проверки", `statuses.manual`="Ручной выбор", `statuses.fromFund`="Из фонда", `statuses.confirmedByOperator`="Подтверждено оператором".

- [ ] **Step 1: Переписать `reviewState.test.ts` — ассерты на ключи**

Заменить `expect(statusLabel(...)).toBe("Нет совпадения")` → `.toBe("statuses.noMatch")`, `"Контекст"` → `"statuses.context"`, `"В обработке"` → `"statuses.processing"` и т.д. для всех ветвей (L147/L170/L303/L304 и др.).

- [ ] **Step 2: Запустить — падает**

Run: `cd frontend; npx vitest run src/lib/reviewState.test.ts`
Expected: FAIL (функция ещё возвращает русские строки).

- [ ] **Step 3: Переписать `statusLabel` на возврат ключей**

```ts
export function statusLabel(row: MatchRow, d: Decision): string {
  if (row.status === "excluded") return "statuses.context"
  if (row.status === "pending") return "statuses.processing"
  if (d.kind === "no_match") return "statuses.noMatch"
  if (d.kind === "pending") return "statuses.needsReview"
  if (d.manual) return "statuses.manual"
  if (row.status === "matched_fund") return "statuses.fromFund"
  return "statuses.confirmedByOperator"
}
```

- [ ] **Step 4: Обновить потребителей statusLabel**
- `ReviewGrid.tsx`: `const label = statusLabel(r, decision)` — рендер `{t(label)}`; связка иконки фонда `label === "Из фонда"` → **`label === "statuses.fromFund"`**; в контекст-ветке `<Badge>{t(label)}</Badge>`. Прочие литералы грида: `review.filterAll`="Все · {{n}}" (или сохранить формат `chip("all", …)` через `t`), `review.filterReview`, `review.filterNoMatch`, колонки `review.colSection`="№ раздела", `review.colWork`="Работа из сметы", `review.colArticle`="Статья справочника СМР", `review.colStatus`="Статус", `review.noPairInline`="— без пары —".
- `ContextStrip.tsx`: `statusLabel` результат `{ text: statusLabel(r, d) }` — потребитель рендерит `t(text)`; заводит `useTranslation`. Литералы: `review.envInEstimate`="Окружение в смете", `review.section`="Раздел — {{label}}", `review.youAreHere`="вы здесь" (aria-label).

- [ ] **Step 5: ReviewScreen.tsx — извлечь + native-плюрализация**

Литералы: `review.disputedResolved`="· спорных решено {{reviewed}} из {{total}}", `review.tabQueue`="Очередь", `review.tabTable`="Таблица", `review.toAllEstimates`="Ко всем сметам", `review.exportExcel`="Выгрузить Excel", `review.finish`="Завершить", `review.pendingTitle`="Остались нерешённые строки", `review.finishAnyway`="Завершить всё равно". Плюрализацию `pluralizeRu(pending, ["спорная строка","спорные строки","спорных строк"])` заменить на native i18next: ключ `review.pendingRows` с формами:
```json
"pendingRows_one": "Без решения — {{count}} спорная строка",
"pendingRows_few": "Без решения — {{count}} спорные строки",
"pendingRows_many": "Без решения — {{count}} спорных строк"
```
вызов `t("review.pendingRows", { count: pending })` + хвост `review.finishAnywayBody`=". Завершить всё равно? Возобновить можно в любой момент." (либо целиком одной интерполированной строкой). tr — формы `_one`/`_other`.

- [ ] **Step 6: ReviewCard.tsx — извлечь** (13 литералов): `review.errorProcessing`="Ошибка обработки", `statuses.fromFund` (переиспользовать для «Из фонда» L161/L218), `review.aiRecommendation`="Рекомендация AI", `review.searchPlaceholder`="Нет верного — искать в справочнике…", `review.nothingFound`="Ничего не найдено", `review.leaveNoPair`="Оставить без пары", легенда `review.hintPick`="выбрать кандидата", `review.hintNoPair`="без пары", `review.hintConfirm`="подтвердить рекомендацию", `review.hintSkip`="пропустить", `review.hintBack`="вернуться".
  **Error-строка (§4.4):** заголовок `t("review.errorProcessing")` (локализован), сырой `row.matchError` (уже в модели, `estimates.ts:103`) показывается вторичным текстом-диагностикой рядом с заголовком (если непустой). `match_error` НЕ переводится (произвольный `str(exc)` LLM-матчера — спека §2, «строки — без кода»).

- [ ] **Step 7: Наполнить `review` + `statuses` в ru/tr** (включая plural-формы).

- [ ] **Step 8: Обновить тесты экранов ревью** — ассерты русских текстов остаются (ru); где тест сверял `statusLabel`-строку напрямую (не через рендер) — уже покрыто Step 1. Проверить `ReviewGrid.test.tsx` на иконку фонда (связка через ключ).

- [ ] **Step 8a: Тест плюрализации ru + tr** (§4.7) — `frontend/src/locales/plural.test.ts`

```ts
import { afterAll, describe, expect, it } from "vitest"
import i18n from "@/lib/i18n"

describe("плюрализация review.pendingRows", () => {
  afterAll(async () => { await i18n.changeLanguage("ru") })
  it("ru: one/few/many", async () => {
    await i18n.changeLanguage("ru")
    expect(i18n.t("review.pendingRows", { count: 1 })).toContain("спорная строка")
    expect(i18n.t("review.pendingRows", { count: 3 })).toContain("спорные строки")
    expect(i18n.t("review.pendingRows", { count: 5 })).toContain("спорных строк")
  })
  it("tr: one/other резолвятся без падения", async () => {
    await i18n.changeLanguage("tr")
    const one = i18n.t("review.pendingRows", { count: 1 })
    const other = i18n.t("review.pendingRows", { count: 5 })
    expect(one).not.toBe("review.pendingRows")   // ключ разрешился
    expect(other).not.toBe("review.pendingRows")
  })
})
```

- [ ] **Step 9: Тесты + typecheck**

Run: `cd frontend; npx vitest run src/lib/reviewState.test.ts src/pages/estimate/ReviewScreen.test.tsx src/pages/estimate/ReviewCard.test.tsx src/pages/estimate/ReviewGrid.test.tsx src/pages/estimate/ContextStrip.test.tsx src/locales/plural.test.ts src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 10: Commit**

```
git commit -am "feat(i18n): ядро ревью — statusLabel-ключи, native-плюрализация, review-секция"
```

---

### Task 7: Справочник (ArticlesPage, ArticleTable, ManualAddForm, TemplateUpload, WipeCatalog)

**Files:**
- Modify: `frontend/src/pages/ArticlesPage.tsx`, `frontend/src/components/articles/ArticleTable.tsx`, `ManualAddForm.tsx`, `TemplateUpload.tsx`, `WipeCatalog.tsx`
- Test: соответствующие `*.test.tsx`
- Modify словарь: секция `articles`

**Interfaces:** Consumes `useTranslation`, `apiErrorText`, `pluralizeRu` (TemplateUpload — заменить на native).

Ключи (`articles.*`, 1:1) — ключевые: `deleted`="Статья удалена", `deleteFailed`="Не удалось удалить статью", `title`="Справочник СМР", `subtitle`="Эталонные статьи строительных работ.", `uploadTemplate`="Загрузить шаблон", `addManual`="Добавить статью вручную", `dangerZone`="Опасная зона", `loadFailed`="Не удалось загрузить справочник.", `emptyAdmin`="Справочник пуст — загрузите шаблон.", `empty`="Справочник пуст.", таблица: `searchAria`/`searchPlaceholder`="Поиск по коду или наименованию", `colCode`="Код", `colName`="Наименование", `deleteAria`="Удалить", `deleteTitle`="Удалить статью?", `deleteBody`="«{{name}}» ({{code}}) будет удалена. Действие необратимо.". ManualAddForm: `enterCode`="Введите код статьи", `enterName`="Введите наименование", `added`="Статья «{{code}}» добавлена", `addFailed`="Не удалось добавить статью", `codeLabel`="Код", `nameLabel`="Наименование", `parentLabel`="Код родителя (необязательно)", `add`="Добавить". TemplateUpload: `readFailed`="Не удалось прочитать файл", `importDone`="Готово: создано {{created}}, обновлено {{updated}}, удалено {{deleted}}, без изменений {{unchanged}}, ожидают эмбеддинга {{pending}}.", `applyFailed`="Не удалось применить импорт", `fileLabel`="Файл шаблона", `dropIdle`="Перетащите .xlsx-шаблон или выберите файл", `hint`="XLSX-шаблон справочника", `fileName`="Файл: {{name}}", `processing`="Обработка…", `skipped`="Пропущено строк: {{n}}", `staleForce`="Состояние справочника изменилось с момента превью — для применения нужен принудительный режим.", `forceConfirmBody` (native plural на `count` строк, см. ниже), `applyForce`="Да, применить принудительно", `apply`="Применить". WipeCatalog: см. Step 3.

- [ ] **Step 1: Обновить тесты справочника** — тексты 1:1 (ru), кроме WipeCatalog confirm-word (Step 3) — тест ввода слова обновить на чтение из словаря (для ru — «УДАЛИТЬ», ассерт не меняется).

- [ ] **Step 2: Извлечь ArticlesPage/ArticleTable/ManualAddForm** — `useTranslation`, `t(...)`, ошибки через `apiErrorText(err, t, "articles.deleteFailed")` и т.п.; zod-сообщения ManualAddForm — схема в замыкании на `t`.

- [ ] **Step 3: WipeCatalog — локализованный confirm-word**

Слово-подтверждение и инструкция — из словаря; сравнение читает `t`:
```tsx
const { t } = useTranslation()
const confirmWord = t("articles.wipeConfirmWord") // ru: "УДАЛИТЬ", tr: "SİL"
// ...
const canConfirm = input.trim() === confirmWord
```
Ключи: `articles.wipeConfirmWord`="УДАЛИТЬ", `articles.wipeDesc`="Полностью удалит все статьи. Потребуется подтверждение вводом слова.", `articles.wipeButton`="Очистить справочник", `articles.wipeTitle`="Очистить весь справочник?", `articles.wipeBody`="Все статьи будут удалены безвозвратно. Введите «{{word}}», чтобы подтвердить." (интерполяция `{{word}}` = `confirmWord`), `articles.wipeInputLabel`="Подтверждение", `articles.wiped`="Удалено {{n}}", `articles.wipeFailed`="Не удалось очистить справочник". tr: `wipeConfirmWord`="SİL", body с `{{word}}`.

- [ ] **Step 4: TemplateUpload — native-плюрализация force-confirm**

`pluralizeRu(count, ["строку","строки","строк"])` → ключ `articles.forceConfirmBody` с формами `_one/_few/_many` (ru) и `_one/_other` (tr): `"Импорт удалит {{count}} строку (снос корня или большой доли). Это необратимо."` и т.д.; вызов `t("articles.forceConfirmBody", { count })`.

- [ ] **Step 5: Наполнить `articles` в ru/tr** (все ключи + plural-формы + `wipeConfirmWord`).

- [ ] **Step 6: Тесты + typecheck**

Run: `cd frontend; npx vitest run src/pages/ArticlesPage.test.tsx src/components/articles src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 7: Commit**

```
git commit -am "feat(i18n): справочник — извлечение строк, локализованный confirm-word, native-плюрализация импорта"
```

---

### Task 8: Структура, common-компоненты, навигация, переключатель языка; удаление plural.ts

**Files:**
- Modify: `frontend/src/components/estimate/StructureNotice.tsx` (KIND_LABELS + plural), `frontend/src/components/Dropzone.tsx` (дефолт-пропсы), `frontend/src/components/AppShell.tsx` (nav + бренд + переключатель RU/TR)
- Delete: `frontend/src/lib/plural.ts`, `frontend/src/lib/plural.test.ts`
- Test: `StructureNotice.test.tsx`, `Dropzone.test.tsx`, `AppShell.test.tsx`
- Modify словарь: `structure`, `nav`, `common`

**Interfaces:** Consumes `useTranslation`, `i18n.changeLanguage`.

Ключи:
- `structure.*`: `kindDuplicate`="Дубль кода", `kindParentBelow`="Родитель ниже", `kindParentMissing`="Нет родителя", `kindDepthJump`="Скачок глубины", `title`="Структура сметы: {{count}} замечание/замечания/замечаний" (native plural `_one/_few/_many`), `titlePlain`="Структура сметы", `colType`="Тип", `colCode`="Код", `colName`="Наименование", `colDetails`="Детали", `outlineNote`="В {{count}} строке/строках вложенность взята из группировки" (native plural).
- `KIND_LABELS` → `kindLabel(kind)` возвращает **ключ** (`structure.kindDuplicate` …); рендер через `t()`. (Или маппинг kind→ключ; fallback — сырой kind.)
- `nav.*`: `brand`="MR · Сметы" (переиспользовать `common.appTitle`?), `tabEstimate`="Смета", `tabArticles`="Справочник", `roleAdmin`="Администратор", `roleUser`="Пользователь", `logout`="Выйти", `langRu`="Русский", `langTr`="Türkçe".
- `Dropzone.tsx` дефолт-пропсы `idleText`/`hotText`: заменить строковые дефолты на **undefined** и рендерить `t("common.dropIdle")`/`t("common.dropHot")` при отсутствии пропа — но Dropzone может быть вне контекста? Он рендерится внутри приложения → `useTranslation` доступен. Ключи `common.dropIdle`="Перетащите файл или выберите", `common.dropHot`="Отпустите файл". (Вызовы StartScreen/TemplateUpload уже передают свои тексты пропсами — их извлечь в задачах 5/7 соответственно; здесь только дефолты.)

- [ ] **Step 1: Обновить тесты StructureNotice/AppShell/Dropzone** — тексты 1:1 (ru). Добавить в `AppShell.test.tsx` тест переключателя (см. Step 5).

- [ ] **Step 2: Извлечь StructureNotice** — `kindLabel` → ключи; `pluralizeRu` → native (`structure.title`, `structure.outlineNote` с `{{count}}`); заголовки таблицы.

- [ ] **Step 3: Извлечь Dropzone дефолт-пропсы** (`common.dropIdle`/`dropHot`).

- [ ] **Step 4: Извлечь AppShell nav** — бренд/табы/роль/выход через `t("nav.*")`.

- [ ] **Step 5: Добавить переключатель языка в AppShell**

В `DropdownMenuContent`, между `DropdownMenuLabel` (роль) и `Выйти`: `DropdownMenuSeparator` + два `DropdownMenuItem` (или `DropdownMenuRadioGroup` с `value={i18n.language}`), пункты RU/TR:
```tsx
const { t, i18n } = useTranslation()
// ...
<DropdownMenuSeparator />
<DropdownMenuRadioGroup
  value={i18n.language.startsWith("tr") ? "tr" : "ru"}
  onValueChange={(lng) => void i18n.changeLanguage(lng)}
>
  <DropdownMenuRadioItem value="ru">{t("nav.langRu")}</DropdownMenuRadioItem>
  <DropdownMenuRadioItem value="tr">{t("nav.langTr")}</DropdownMenuRadioItem>
</DropdownMenuRadioGroup>
<DropdownMenuSeparator />
<DropdownMenuItem onSelect={() => logout()}>{t("nav.logout")}</DropdownMenuItem>
```
(Проверить наличие `DropdownMenuRadioGroup`/`DropdownMenuRadioItem` в `components/ui/dropdown-menu.tsx`; если нет — два обычных `DropdownMenuItem` с галочкой `Check` у активного.) Смена языка → детектор сам пишет в `localStorage["ciw.ui.lang"]` (caches), `languageChanged` обновляет `document.documentElement.lang`.

- [ ] **Step 6: Тест переключателя** (`AppShell.test.tsx`)

Рендерит AppShell, открывает меню, кликает «Türkçe», ассертит что видимый nav-текст сменился на турецкий (напр. таб «Справочник» → tr-перевод) и `localStorage.getItem("ciw.ui.lang") === "tr"` и `document.documentElement.lang === "tr"`. Вернуть язык на ru в `afterEach`.

- [ ] **Step 7: Удалить plural.ts + plural.test.ts** — подтвердить, что вызовов не осталось:

Run: `cd frontend; npx grep -r "pluralizeRu" src` (или Grep-инструмент)
Expected: 0 совпадений (все мигрированы: StructureNotice/ReviewScreen/TemplateUpload). Затем:
```
git rm frontend/src/lib/plural.ts frontend/src/lib/plural.test.ts
```

- [ ] **Step 8: Наполнить `structure`/`nav`/`common` в ru/tr.**

- [ ] **Step 9: Тесты + typecheck**

Run: `cd frontend; npx vitest run src/components/estimate/StructureNotice.test.tsx src/components/AppShell.test.tsx src/components/Dropzone.test.tsx src/locales/parity.test.ts; npm run typecheck`
Expected: PASS.

- [ ] **Step 10: Commit**

```
git commit -am "feat(i18n): структура/навигация/Dropzone, переключатель RU/TR, удаление plural.ts"
```

---

### Task 9: Полный охват tr, вычитка-маркер, финальный гейт, devlog

**Files:**
- Modify: `frontend/src/locales/tr.json` (полный проход терминологии), `docs/TECH_DEBT.md`, создать devlog.
- Проверка: полный прогон vitest + typecheck + lint + build.

- [ ] **Step 1: Проверить полноту извлечения** — grep остаточной кириллицы в UI-позициях:

Grep кириллицы (`[А-Яа-яЁё]`) по `frontend/src` с исключением `lib/mock/**`, `*.test.*`, комментариев. Каждое совпадение в JSX/aria/placeholder/toast — либо извлечь (доработать задачу-источник), либо явно обосновать (доменные данные/dev-throw). Ноль необоснованных остатков.

- [ ] **Step 2: Пройтись по tr.json — профессиональная сметная терминология**

Заменить машинный черновик на выверенный словарь (keşif=смета, poz=позиция/статья, metraj=объёмы). Полное покрытие без пропусков (fallback ru есть, но цель — полнота).
**Смысловые дубли — переводить согласованно:** одно и то же состояние выражено двумя ключами (список vs баннер одной и той же сметы) — `statuses.partialError` (бейдж списка) и `statuses.matching_partial_error` (заголовок баннера EstimatePage) оба = «Готово с ошибками»; их tr-переводы ОБЯЗАНЫ совпадать, иначе список и баннер разъедутся на одной смете. Свериться при вычитке.

- [ ] **Step 3: Тест чётности после полного tr — зелёный**

Run: `cd frontend; npx vitest run src/locales/parity.test.ts`
Expected: PASS (ключи и интерполяции совпадают).

- [ ] **Step 4: Полный гейт**

Run: `cd frontend; npm run typecheck; npx vitest run; npm run build`
Дополнительно из корня: `just lint` (eslint + prettier --check).
Expected: typecheck 0 ошибок; все тесты PASS; build успешен; lint чист (или только известный pre-existing warning `useVirtualizer`).

- [ ] **Step 5: Маркер вычитки tr + devlog**

В `docs/TECH_DEBT.md` — пункт 🟢 «tr.json не вычитан носителями» (follow-up вне этапа, спека §4.6). Создать `docs/devlog/2026-07-07-ux-stage4-i18n-frontend.md`: что сделано, охват (N файлов), контракт кодов ↔ словарь, ключевые решения (ключи вместо строк в не-React точках, `_matched.xlsx`, локализованный confirm-word), верификация, вне скоупа (вычитка tr, доменные данные, экспорт .xlsx).

- [ ] **Step 6: Commit**

```
git add frontend/src/locales/tr.json docs/TECH_DEBT.md docs/devlog/2026-07-07-ux-stage4-i18n-frontend.md
git commit -m "feat(i18n): полный tr, маркер вычитки, devlog PR-2"
```

---

## Self-Review Checklist (для контролёра — пройти после реализации)

- [ ] §4.1 стек/инициализация: i18next + detector, `localStorage["ciw.ui.lang"]`→navigator, `fallbackLng:ru`, `supportedLngs` — Task 1.
- [ ] §4.2 извлечение всех ~23 файлов + не-React точки (`statusLabel`→ключи, `client.ts` не зовёт `t()`); один статус — один ключ — Tasks 3–8; исключения (mock/домен/dev-throw) соблюдены.
- [ ] §4.3 native-плюрализация (ru one/few/many, tr one/other), `plural.ts` удалён; `formatDate` локале-зависимый, `Intl…("ru-RU")` мигрирован — Tasks 4/6/7/8.
- [ ] §4.4 `ApiError.code`, цепочка `apiErrorText`, `errors.network`, баннер blocked/partial_error по `status_code`, error-строка — Task 2 + экраны.
- [ ] §4.5 переключатель RU/TR в AppShell-меню, `document.documentElement.lang` — Task 8/1.
- [ ] §4.6 tr полный + маркер вычитки — Task 9.
- [ ] §4.7 vitest init ru; **тест чётности словарей (обязательный)**; тесты `code`-парсинга, цепочки фолбэков, переключателя+персист, плюрализации ru/tr, `formatDate`, `statusLabel`-ключей — Tasks 1/2/4/6/8.
- [ ] Инвариант формулировок: тексты 1:1, существующие RTL-тексты-ассерты зелёные (кроме санкционированного `_matched.xlsx`).
- [ ] `ReviewGrid` связка иконки фонда переведена на сравнение ключа `statuses.fromFund`, не строки.

## Execution Handoff

(Заполняется контролёром при запуске — см. ниже.)
