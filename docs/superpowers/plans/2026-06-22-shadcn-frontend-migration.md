# shadcn Frontend Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поэтапно заменить кастомные UI-решения в auth + справочнике + AppShell на штатные компоненты shadcn.

**Architecture:** Снизу вверх: сначала ставим недостающие примитивы shadcn и зависимости форм/тостов (Этап 0), затем по одному переводим участки — навигация, каркас страницы, подтверждения, формы, загрузка шаблона. Каждый этап самодостаточен, заканчивается зелёными `typecheck`/`lint`/`test` и отдельным коммитом.

**Tech Stack:** React 19, Vite, TypeScript (strict, `erasableSyntaxOnly`), Tailwind v4, shadcn/ui (стиль `radix-nova`, пакет `radix-ui`), react-hook-form + zod (новое), sonner (новое), vitest + React Testing Library.

## Global Constraints

- Работаем **только из** `frontend/`. Команды npm/npx — оттуда.
- shadcn-компоненты в `src/components/ui/` — **вендорные, не править** (CLAUDE.md). Единственное исключение в этом плане — адаптация `ui/sonner.tsx` под локальный `useTheme` (Этап 0, Шаг 4), т.к. сгенерированный файл импортит отсутствующий `next-themes`.
- Зависимости фронта ставим через `npm install` (бэк — отдельно через `uv`, его не трогаем).
- Импорты только через alias `@/`. Иконки — `lucide-react`.
- Prettier: `printWidth 80`, `endOfLine lf`. Перед коммитом — `npm run lint` (eslint + prettier --check) и `npm run typecheck` (`tsc -b`).
- **Вне охвата:** `pages/estimate/*`, `lib/mock/`, `Candidate`, `MOCK_*` — не трогать.
- Тестовый раннер: `npm run test` = `vitest run`. Точечно: `npx vitest run <path>`.
- Поведение фич сохраняется; меняется только реализация UI и канал обратной связи (inline → тост/диалог/Alert).

---

## File Structure

**Создаются (через `npx shadcn add`, не редактируем кроме sonner.tsx):**
- `src/components/ui/{label,checkbox,alert,tabs,alert-dialog,dropdown-menu,sonner,skeleton,form,collapsible}.tsx`

**Создаются вручную:**
- `src/components/AppShell.test.tsx` — тесты навигации/меню (сейчас отсутствуют).

**Модифицируются:**
- `src/App.tsx` — монтаж `<Toaster />`.
- `src/test/setup.ts` — полифиллы jsdom для Radix-оверлеев.
- `src/components/ui/sonner.tsx` — локальный `useTheme`.
- `src/components/AppShell.tsx` — Tabs + DropdownMenu.
- `src/pages/ArticlesPage.tsx` — Card/Skeleton/Alert, удаление через тост.
- `src/components/articles/ArticleTable.tsx` (+ `.test.tsx`) — AlertDialog на удаление.
- `src/components/articles/WipeCatalog.tsx` (+ `.test.tsx`) — AlertDialog + тост.
- `src/components/auth/LoginScreen.tsx` (+ `.test.tsx`) — Form+RHF+zod + тост.
- `src/components/articles/ManualAddForm.tsx` (+ `.test.tsx`) — Form+RHF+zod + тост.
- `src/components/articles/TemplateUpload.tsx` (+ `.test.tsx`) — Input file + Checkbox + Alert + Collapsible + тост.

---

## Task 0: Фундамент — примитивы, зависимости, Toaster, полифиллы

**Files:**
- Install deps: `react-hook-form`, `@hookform/resolvers`, `zod`, `sonner`
- Create (CLI): `src/components/ui/{label,checkbox,alert,tabs,alert-dialog,dropdown-menu,sonner,skeleton,form,collapsible}.tsx`
- Modify: `src/components/ui/sonner.tsx`, `src/App.tsx`, `src/test/setup.ts`

**Interfaces:**
- Produces: смонтированный `<Toaster />` в корне; компоненты `@/components/ui/*` доступны для импорта; `toast` из `"sonner"` доступен в компонентах.

- [ ] **Step 1: Поставить зависимости форм**

Run:
```bash
npm install react-hook-form @hookform/resolvers zod
```
Expected: пакеты появились в `dependencies` (`package.json`), без ошибок.

- [ ] **Step 2: Добавить примитивы shadcn**

Run:
```bash
npx shadcn@latest add label checkbox alert tabs alert-dialog dropdown-menu sonner skeleton form collapsible
```
Expected: созданы файлы в `src/components/ui/`; `sonner` добавлен в `dependencies`. На вопрос про overwrite существующих (button/input и т.п.) отвечать **No** — их не трогаем.

- [ ] **Step 3: Проверить, что есть незакоммиченные новые файлы**

Run:
```bash
git status --short
```
Expected: новые `src/components/ui/*.tsx` и изменённый `package.json`/`package-lock.json`.

- [ ] **Step 4: Адаптировать `ui/sonner.tsx` под локальный useTheme**

Открыть `src/components/ui/sonner.tsx`. Заменить импорт темы. Было (примерно):
```tsx
import { useTheme } from "next-themes"
import { Toaster as Sonner, type ToasterProps } from "sonner"
```
Стало:
```tsx
import { useTheme } from "@/components/theme-provider"
import { Toaster as Sonner, type ToasterProps } from "sonner"
```
Остальное тело компонента (где берётся `const { theme = "system" } = useTheme()`) оставить как есть — наш `useTheme` возвращает `{ theme, setTheme }`, поле `theme` совпадает по форме (`"dark" | "light" | "system"`).

- [ ] **Step 5: Смонтировать Toaster в App**

Изменить `src/App.tsx`:
```tsx
import { useState } from "react"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"
import { Toaster } from "@/components/ui/sonner"

export function App() {
  const [tab, setTab] = useState<"estimate" | "articles">("estimate")
  return (
    <AuthProvider>
      <AuthGate>
        <AppShell tab={tab} onTab={setTab}>
          {tab === "estimate" ? <EstimateFlow /> : <ArticlesPage />}
        </AppShell>
      </AuthGate>
      <Toaster />
    </AuthProvider>
  )
}

export default App
```

- [ ] **Step 6: Добавить полифиллы jsdom для Radix-оверлеев**

В `src/test/setup.ts` дописать ПОСЛЕ существующих импортов (Radix DropdownMenu/AlertDialog/Checkbox используют Pointer Capture API и `scrollIntoView`, которых нет в jsdom):
```ts
import "@testing-library/jest-dom/vitest"

import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// jsdom не реализует Pointer Capture / scrollIntoView, которые дёргает Radix.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {}
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {}
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

afterEach(() => {
  cleanup()
})
```

- [ ] **Step 7: Прогнать проверки — поведение не изменилось**

Run:
```bash
npm run typecheck && npm run lint && npm run test
```
Expected: всё зелёное (UI визуально без изменений, тосты ещё никто не вызывает).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "build(front): подключить примитивы shadcn, sonner, rhf+zod; смонтировать Toaster

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: AppShell → Tabs + DropdownMenu

**Files:**
- Modify: `src/components/AppShell.tsx`
- Create: `src/components/AppShell.test.tsx`

**Interfaces:**
- Consumes: `useAuth()` → `{ user, role, logout }`; `clearReview()` из `@/lib/session`.
- Produces: `AppShell` с тем же контрактом пропсов `{ tab, onTab, children }`.

- [ ] **Step 1: Написать падающие тесты навигации/меню**

Создать `src/components/AppShell.test.tsx`:
```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { AuthUser } from "@/lib/types"
import * as authCtx from "@/lib/auth/useAuth"
import * as session from "@/lib/session"
import { AppShell } from "./AppShell"

const USER: AuthUser = { id: 1, email: "a@mr.kz", role: "admin", is_active: true }
const logout = vi.fn()

function mockAuth() {
  vi.spyOn(authCtx, "useAuth").mockReturnValue({
    user: USER,
    role: USER.role,
    loading: false,
    error: null,
    login: vi.fn(),
    logout,
  })
}

afterEach(() => vi.restoreAllMocks())

describe("AppShell", () => {
  it("клик по вкладке зовёт onTab", async () => {
    mockAuth()
    const onTab = vi.fn()
    render(
      <AppShell tab="estimate" onTab={onTab}>
        контент
      </AppShell>
    )
    await userEvent.click(screen.getByRole("tab", { name: /справочник/i }))
    expect(onTab).toHaveBeenCalledWith("articles")
  })

  it("из меню пользователя выходит (clearReview + logout)", async () => {
    mockAuth()
    const clearReview = vi
      .spyOn(session, "clearReview")
      .mockImplementation(() => {})
    render(
      <AppShell tab="estimate" onTab={vi.fn()}>
        контент
      </AppShell>
    )
    await userEvent.click(screen.getByRole("button", { name: /a@mr\.kz/i }))
    await userEvent.click(screen.getByRole("menuitem", { name: /выйти/i }))
    expect(clearReview).toHaveBeenCalledOnce()
    expect(logout).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Прогнать — тесты падают**

Run: `npx vitest run src/components/AppShell.test.tsx`
Expected: FAIL (нет роли `tab`/`menuitem` — навигация пока на голых `<button>`).

- [ ] **Step 3: Переписать AppShell на Tabs + DropdownMenu**

Заменить `src/components/AppShell.tsx` целиком:
```tsx
// frontend/src/components/AppShell.tsx
import { ChevronDown, FileSpreadsheet, Library } from "lucide-react"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth/useAuth"
import { clearReview } from "@/lib/session"

interface AppShellProps {
  tab: "estimate" | "articles"
  onTab: (t: "estimate" | "articles") => void
  children: React.ReactNode
}

export function AppShell({ tab, onTab, children }: AppShellProps) {
  const { user, role, logout } = useAuth()
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-5 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-6 py-3">
        <span className="font-display text-base">
          MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
        </span>
        <Tabs
          value={tab}
          onValueChange={(v) => onTab(v as "estimate" | "articles")}
        >
          <TabsList>
            <TabsTrigger value="estimate">
              <FileSpreadsheet className="size-4" />
              Смета
            </TabsTrigger>
            <TabsTrigger value="articles">
              <Library className="size-4" />
              Справочник
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger className="ml-auto flex items-center gap-1 text-xs text-muted-foreground outline-none hover:text-foreground">
              {user.email}
              <ChevronDown className="size-3.5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {role === "admin" ? "Администратор" : "Пользователь"}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  clearReview()
                  logout()
                }}
              >
                Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </header>
      <main>{children}</main>
    </div>
  )
}
```

- [ ] **Step 4: Прогнать — тесты проходят**

Run: `npx vitest run src/components/AppShell.test.tsx`
Expected: PASS (2 теста).

- [ ] **Step 5: Полные проверки + коммит**

Run: `npm run typecheck && npm run lint && npm run test`
Expected: всё зелёное.
```bash
git add -A
git commit -m "feat(front): AppShell на Tabs + DropdownMenu вместо кастомной навигации

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: ArticlesPage — Card + Skeleton + Alert

**Files:**
- Modify: `src/pages/ArticlesPage.tsx`
- Test (без изменений, должен остаться зелёным): `src/pages/ArticlesPage.test.tsx`

**Interfaces:**
- Consumes: `Card`/`CardHeader`/`CardTitle`/`CardContent`, `Skeleton`, `Alert`/`AlertTitle` из `@/components/ui/*`.
- Produces: тот же `ArticlesPage` (export default + named).

> Примечание: на этом этапе `actionError`/`handleDelete` НЕ трогаем (он уходит в Task 3). Меняем только админ-панели, загрузку и ошибку загрузки списка.

- [ ] **Step 1: Убедиться, что текущие тесты зелёные (базовая линия)**

Run: `npx vitest run src/pages/ArticlesPage.test.tsx`
Expected: PASS (5 тестов). Тесты ищут текст «загрузить шаблон», «справочник пуст», «не удалось загрузить», кнопку «повторить» — все они сохранятся.

- [ ] **Step 2: Переписать каркас разметки ArticlesPage**

Заменить `src/pages/ArticlesPage.tsx`. Импорты сверху:
```tsx
import { useCallback, useEffect, useState } from "react"
import { AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { ArticleTable } from "@/components/articles/ArticleTable"
import { ManualAddForm } from "@/components/articles/ManualAddForm"
import { WipeCatalog } from "@/components/articles/WipeCatalog"
import { TemplateUpload } from "@/components/articles/TemplateUpload"
import { listArticles, deleteArticle } from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/useAuth"
import type { Article } from "@/lib/types"
```
Тело компонента (state/effect/handleDelete оставить как в текущем файле — НЕ менять в этом этапе) и заменить только `return (...)`:
```tsx
  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">Справочник СМР</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Эталонные статьи строительных работ.
      </p>

      {isAdmin && (
        <div className="mb-6 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Загрузить шаблон
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TemplateUpload onApplied={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Добавить статью вручную
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ManualAddForm onCreated={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Опасная зона</CardTitle>
            </CardHeader>
            <CardContent>
              <WipeCatalog onWiped={() => void reload()} />
            </CardContent>
          </Card>
        </div>
      )}

      {status === "loading" && (
        <div className="space-y-2" aria-label="Загрузка">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
      {status === "error" && (
        <div>
          <Alert variant="destructive" className="mb-3">
            <AlertCircle className="size-4" />
            <AlertTitle>Не удалось загрузить справочник.</AlertTitle>
          </Alert>
          <Button onClick={() => void reload()}>Повторить</Button>
        </div>
      )}
      {status === "ready" && articles.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Справочник пуст{isAdmin ? " — загрузите шаблон." : "."}
        </p>
      )}
      {actionError && (
        <p className="mb-3 text-sm text-destructive">{actionError}</p>
      )}
      {status === "ready" && articles.length > 0 && (
        <ArticleTable
          articles={articles}
          isAdmin={isAdmin}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
```

- [ ] **Step 3: Прогнать — тесты остаются зелёными**

Run: `npx vitest run src/pages/ArticlesPage.test.tsx`
Expected: PASS (текст «загрузить шаблон» теперь в `CardTitle`, «не удалось загрузить» в `AlertTitle`, кнопка «повторить» на месте).

- [ ] **Step 4: Полные проверки + коммит**

Run: `npm run typecheck && npm run lint && npm run test`
```bash
git add -A
git commit -m "feat(front): ArticlesPage на Card + Skeleton + Alert

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Подтверждения через AlertDialog + тосты

**Files:**
- Modify: `src/components/articles/ArticleTable.tsx` (+ `.test.tsx`)
- Modify: `src/components/articles/WipeCatalog.tsx` (+ `.test.tsx`)
- Modify: `src/pages/ArticlesPage.tsx` (удаление → тост, убрать `window.confirm` и `actionError`)

**Interfaces:**
- Consumes: `AlertDialog` и его части из `@/components/ui/alert-dialog`; `toast` из `"sonner"`; `Label` из `@/components/ui/label`.
- Produces: `ArticleTable` вызывает `onDelete(id)` только после подтверждения в диалоге; `WipeCatalog` подтверждает ввод слова внутри диалога; `ArticlesPage.handleDelete` без `window.confirm`.

### 3a. ArticleTable — удаление через AlertDialog

- [ ] **Step 1: Обновить тест ArticleTable под диалог**

Заменить в `src/components/articles/ArticleTable.test.tsx` последний тест и импорты `render, screen` → добавить `within`:
```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { Article } from "@/lib/types"
import { ArticleTable } from "./ArticleTable"
```
И тест удаления:
```tsx
  it("у админа подтверждение в диалоге зовёт onDelete с id", async () => {
    const onDelete = vi.fn()
    render(<ArticleTable articles={ARTS} isAdmin onDelete={onDelete} />)
    await userEvent.click(screen.getAllByLabelText(/удалить/i)[0])
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(within(dialog).getByRole("button", { name: /удалить/i }))
    expect(onDelete).toHaveBeenCalledWith(1)
  })
```
Остальные три теста ArticleTable не трогать.

- [ ] **Step 2: Прогнать — падает**

Run: `npx vitest run src/components/articles/ArticleTable.test.tsx`
Expected: FAIL (нет `alertdialog` — кнопка зовёт onDelete сразу).

- [ ] **Step 3: Обернуть удаление в AlertDialog**

В `src/components/articles/ArticleTable.tsx` добавить импорт:
```tsx
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
```
Заменить ячейку с кнопкой удаления (блок `{isAdmin && (<td>...<button>...</td>)}`):
```tsx
                {isAdmin && (
                  <td className="px-4 py-2">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button type="button" aria-label="Удалить">
                          <Trash2 className="size-4 text-destructive" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Удалить статью?</AlertDialogTitle>
                          <AlertDialogDescription>
                            «{a.name}» ({a.article_code}) будет удалена.
                            Действие необратимо.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Отмена</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete?.(a.id)}>
                            Удалить
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </td>
                )}
```

- [ ] **Step 4: Прогнать — проходит**

Run: `npx vitest run src/components/articles/ArticleTable.test.tsx`
Expected: PASS (4 теста).

### 3b. ArticlesPage — удаление без confirm, через тост

- [ ] **Step 5: Заменить handleDelete и убрать actionError**

В `src/pages/ArticlesPage.tsx`:
- добавить импорт `import { toast } from "sonner"`;
- удалить состояние `const [actionError, setActionError] = useState<string | null>(null)`;
- в `reload` убрать строку `setActionError(null)`;
- заменить `handleDelete`:
```tsx
  async function handleDelete(id: number) {
    try {
      await deleteArticle(id)
      toast.success("Статья удалена")
      reload()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось удалить статью"
      )
    }
  }
```
- удалить из JSX блок `{actionError && (<p ...>{actionError}</p>)}`.

- [ ] **Step 6: Прогнать ArticlesPage-тесты**

Run: `npx vitest run src/pages/ArticlesPage.test.tsx`
Expected: PASS (тесты удаление не покрывают; `reload` без `setActionError` валиден).

### 3c. WipeCatalog — AlertDialog + тост

- [ ] **Step 7: Переписать тест WipeCatalog**

Заменить `src/components/articles/WipeCatalog.test.tsx` целиком:
```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import * as articlesApi from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { WipeCatalog } from "./WipeCatalog"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => vi.restoreAllMocks())

async function openDialog() {
  await userEvent.click(
    screen.getByRole("button", { name: /очистить справочник/i })
  )
  return screen.findByRole("alertdialog")
}

describe("WipeCatalog", () => {
  it("кнопка подтверждения активна только после ввода слова", async () => {
    render(<WipeCatalog onWiped={vi.fn()} />)
    const dialog = await openDialog()
    const confirm = within(dialog).getByRole("button", {
      name: /очистить справочник/i,
    })
    expect(confirm).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    expect(confirm).toBeEnabled()
  })

  it("очищает и шлёт тост «Удалено N»", async () => {
    const onWiped = vi.fn()
    vi.spyOn(articlesApi, "deleteAllArticles").mockResolvedValue(362)
    render(<WipeCatalog onWiped={onWiped} />)
    const dialog = await openDialog()
    await userEvent.type(within(dialog).getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /очистить справочник/i })
    )
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/удалено 362/i)
      )
    )
    expect(onWiped).toHaveBeenCalledOnce()
  })

  it("на ошибке ApiError шлёт тост и сбрасывает слово", async () => {
    vi.spyOn(articlesApi, "deleteAllArticles").mockRejectedValue(
      new ApiError(500, "сбой очистки")
    )
    render(<WipeCatalog onWiped={vi.fn()} />)
    const dialog = await openDialog()
    const input = within(dialog).getByLabelText(/подтверждени/i)
    await userEvent.type(input, "УДАЛИТЬ")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /очистить справочник/i })
    )
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/сбой очистки/i)
      )
    )
    expect(input).toHaveValue("")
  })
})
```

- [ ] **Step 8: Прогнать — падает**

Run: `npx vitest run src/components/articles/WipeCatalog.test.tsx`
Expected: FAIL (нет диалога/тостов в текущей реализации).

- [ ] **Step 9: Переписать WipeCatalog**

Заменить `src/components/articles/WipeCatalog.tsx` целиком:
```tsx
import { useState } from "react"
import { toast } from "sonner"
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api/client"
import { deleteAllArticles } from "@/lib/api/articles"

const CONFIRM_WORD = "УДАЛИТЬ"

export function WipeCatalog({ onWiped }: { onWiped: () => void }) {
  const [open, setOpen] = useState(false)
  const [word, setWord] = useState("")
  const [busy, setBusy] = useState(false)

  async function wipe() {
    setBusy(true)
    try {
      const n = await deleteAllArticles()
      toast.success(`Удалено ${n}`)
      setWord("")
      setOpen(false)
      onWiped()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось очистить справочник"
      )
      setWord("")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        Полностью удалит все статьи. Потребуется подтверждение вводом слова.
      </p>
      <AlertDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) setWord("")
        }}
      >
        <AlertDialogTrigger asChild>
          <Button variant="destructive">Очистить справочник</Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Очистить весь справочник?</AlertDialogTitle>
            <AlertDialogDescription>
              Все статьи будут удалены безвозвратно. Введите «{CONFIRM_WORD}»,
              чтобы подтвердить.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Label htmlFor="wipe-confirm" className="sr-only">
            Подтверждение
          </Label>
          <Input
            id="wipe-confirm"
            value={word}
            onChange={(e) => setWord(e.target.value)}
            placeholder={CONFIRM_WORD}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={busy || word !== CONFIRM_WORD}
              onClick={() => void wipe()}
            >
              Очистить справочник
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
```

- [ ] **Step 10: Прогнать — проходит**

Run: `npx vitest run src/components/articles/WipeCatalog.test.tsx`
Expected: PASS (3 теста).

- [ ] **Step 11: Полные проверки + коммит**

Run: `npm run typecheck && npm run lint && npm run test`
```bash
git add -A
git commit -m "feat(front): подтверждения удаления через AlertDialog, результаты через тосты

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Формы LoginScreen и ManualAddForm на Form + RHF + zod

**Files:**
- Modify: `src/components/auth/LoginScreen.tsx` (+ `.test.tsx`)
- Modify: `src/components/articles/ManualAddForm.tsx` (+ `.test.tsx`)

**Interfaces:**
- Consumes: `useForm` (react-hook-form), `zodResolver` (`@hookform/resolvers/zod`), `z` (zod), `Form`/`FormField`/`FormItem`/`FormLabel`/`FormControl`/`FormMessage` из `@/components/ui/form`, `toast` из `"sonner"`.
- Produces: те же экспортируемые компоненты с тем же контрактом пропсов.

### 4a. LoginScreen

- [ ] **Step 1: Переписать тест LoginScreen (тост + валидация)**

Заменить `src/components/auth/LoginScreen.test.tsx`:
```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { ApiError } from "@/lib/api/client"
import { AuthProvider } from "@/lib/auth/AuthContext"
import * as authApi from "@/lib/api/auth"
import { LoginScreen } from "./LoginScreen"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

function renderLogin() {
  render(
    <AuthProvider>
      <LoginScreen />
    </AuthProvider>
  )
}

describe("LoginScreen", () => {
  it("на 401 шлёт тост «неверный логин или пароль»", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "bad"))
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /войти/i }))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/неверный логин или пароль/i)
      )
    )
  })

  it("пустая форма показывает ошибки валидации, login не зовётся", async () => {
    const spy = vi.spyOn(authApi, "login")
    renderLogin()
    await userEvent.click(screen.getByRole("button", { name: /войти/i }))
    expect(await screen.findByText(/введите логин/i)).toBeInTheDocument()
    expect(screen.getByText(/введите пароль/i)).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Прогнать — падает**

Run: `npx vitest run src/components/auth/LoginScreen.test.tsx`
Expected: FAIL (нет тостов/валидации в текущей реализации).

- [ ] **Step 3: Переписать LoginScreen**

Заменить `src/components/auth/LoginScreen.tsx` целиком:
```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/useAuth"

const schema = z.object({
  email: z.string().min(1, "Введите логин"),
  password: z.string().min(1, "Введите пароль"),
})
type Values = z.infer<typeof schema>

export function LoginScreen() {
  const { login } = useAuth()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  })

  async function onSubmit(values: Values) {
    try {
      await login(values.email, values.password)
    } catch (err) {
      toast.error(
        err instanceof ApiError && err.status === 401
          ? "Неверный логин или пароль"
          : "Не удалось войти, попробуйте позже"
      )
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
      </div>
      <div className="mb-5 text-xs text-muted-foreground">
        Автоматизатор строительных смет
      </div>
      <Card className="w-64">
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="flex flex-col gap-3"
            >
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Логин</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Пароль</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button type="submit" disabled={form.formState.isSubmitting}>
                Войти
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 4: Прогнать — проходит**

Run: `npx vitest run src/components/auth/LoginScreen.test.tsx`
Expected: PASS (2 теста).

### 4b. ManualAddForm

- [ ] **Step 5: Переписать тест ManualAddForm (тост вместо inline-ошибки)**

Заменить `src/components/articles/ManualAddForm.test.tsx`:
```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { ManualAddForm } from "./ManualAddForm"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => vi.restoreAllMocks())

describe("ManualAddForm", () => {
  it("создаёт статью и зовёт onCreated", async () => {
    const onCreated = vi.fn()
    const spy = vi.spyOn(articlesApi, "createArticle").mockResolvedValue({
      id: 1,
      article_code: "1",
      name: "Раздел",
      parent_id: null,
    })
    render(<ManualAddForm onCreated={onCreated} />)
    // /^Код$/ — иначе матчит и «Код родителя» (multiple elements)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Раздел")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({
        article_code: "1",
        name: "Раздел",
        parent_code: null,
      })
    )
    expect(onCreated).toHaveBeenCalledOnce()
  })

  it("показывает тост на ошибке бэкенда (409 дубликат)", async () => {
    vi.spyOn(articlesApi, "createArticle").mockRejectedValue(
      new ApiError(409, "уже существует")
    )
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Дубль")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/уже существует/i)
      )
    )
  })

  it("пустой код/имя блокируют сабмит (валидация)", async () => {
    const spy = vi.spyOn(articlesApi, "createArticle")
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(await screen.findByText(/введите код/i)).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 6: Прогнать — падает**

Run: `npx vitest run src/components/articles/ManualAddForm.test.tsx`
Expected: FAIL.

- [ ] **Step 7: Переписать ManualAddForm**

Заменить `src/components/articles/ManualAddForm.tsx` целиком:
```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { createArticle } from "@/lib/api/articles"

const schema = z.object({
  article_code: z.string().trim().min(1, "Введите код"),
  name: z.string().trim().min(1, "Введите наименование"),
  parent_code: z.string().optional(),
})
type Values = z.infer<typeof schema>

export function ManualAddForm({ onCreated }: { onCreated: () => void }) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { article_code: "", name: "", parent_code: "" },
  })

  async function onSubmit(values: Values) {
    try {
      await createArticle({
        article_code: values.article_code.trim(),
        name: values.name.trim(),
        parent_code: values.parent_code?.trim() || null,
      })
      toast.success("Статья добавлена")
      form.reset()
      onCreated()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось добавить статью"
      )
    }
  }

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="grid gap-3 sm:grid-cols-[160px_1fr_160px_auto]"
      >
        <FormField
          control={form.control}
          name="article_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Код</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Наименование</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="parent_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Код родителя (необязательно)</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button
          type="submit"
          disabled={form.formState.isSubmitting}
          className="self-end"
        >
          <Plus className="size-4" />
          Добавить
        </Button>
      </form>
    </Form>
  )
}
```

- [ ] **Step 8: Прогнать — проходит**

Run: `npx vitest run src/components/articles/ManualAddForm.test.tsx`
Expected: PASS (3 теста).

- [ ] **Step 9: Полные проверки + коммит**

Run: `npm run typecheck && npm run lint && npm run test`
```bash
git add -A
git commit -m "feat(front): LoginScreen и ManualAddForm на Form + react-hook-form + zod

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: TemplateUpload — Input file + Checkbox + Alert + Collapsible + тост

**Files:**
- Modify: `src/components/articles/TemplateUpload.tsx` (+ `.test.tsx`)

**Interfaces:**
- Consumes: `Input` (`type="file"`), `Label`, `Checkbox`, `Alert`/`AlertDescription`, `Collapsible`/`CollapsibleTrigger`/`CollapsibleContent`, `toast`.
- Produces: тот же `TemplateUpload` с пропом `onApplied`.

> Логика dry-run/force/409 сохраняется один-в-один; меняются только: file-input → `Input type=file`, чекбокс → `Checkbox`, предупреждение → `Alert`, `<details>` → `Collapsible`, итог/ошибки → тосты. Сводка превью (created/updated/...) остаётся inline-текстом.

- [ ] **Step 1: Обновить тест TemplateUpload (тост на итог/ошибку)**

Заменить `src/components/articles/TemplateUpload.test.tsx`. Сохранить хелперы `report`/`pick` и 4 теста про dry-run/force/409/смену файла как есть, но: добавить мок sonner и переписать тест-ошибку под тост. Полный файл:
```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import type { ImportReport } from "@/lib/types"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { TemplateUpload } from "./TemplateUpload"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

function report(over: Partial<ImportReport> = {}): ImportReport {
  return {
    created: 0,
    updated: 0,
    deleted: 0,
    unchanged: 0,
    skipped: [],
    pending_embeddings: 0,
    dry_run: true,
    force_required: false,
    ...over,
  }
}

function pick(name = "Шаблон.xlsx") {
  return userEvent.upload(
    screen.getByLabelText(/файл шаблона/i),
    new File(["x"], name)
  )
}

afterEach(() => vi.restoreAllMocks())

describe("TemplateUpload", () => {
  it("превью (dry_run) затем применение (dry_run=false)", async () => {
    const spy = vi
      .spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ created: 362, pending_embeddings: 362 }))
      .mockResolvedValueOnce(
        report({ created: 362, dry_run: false, pending_embeddings: 362 })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    expect(await screen.findByText(/создано/i)).toBeInTheDocument()
    expect(spy.mock.calls[0][1]).toEqual({ dryRun: true, force: false })
    await userEvent.click(screen.getByRole("button", { name: /применить/i }))
    await waitFor(() =>
      expect(spy.mock.calls[1][1]).toEqual({ dryRun: false, force: false })
    )
  })

  it("force_required: «Применить» заблокирована до чекбокса, затем шлёт force:true", async () => {
    vi.spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ deleted: 5, force_required: true }))
      .mockResolvedValueOnce(
        report({ deleted: 5, dry_run: false, force_required: true })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    await screen.findByText(/удалит/i)
    const apply = screen.getByRole("button", { name: /применить/i })
    expect(apply).toBeDisabled()
    await userEvent.click(screen.getByRole("checkbox"))
    expect(apply).toBeEnabled()
    await userEvent.click(apply)
    await waitFor(() =>
      expect(
        (
          articlesApi.importTemplate as unknown as {
            mock: { calls: unknown[][] }
          }
        ).mock.calls[1][1]
      ).toEqual({ dryRun: false, force: true })
    )
  })

  it("на 409-дрейф поднимает чекбокс force, затем шлёт force:true", async () => {
    vi.spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ force_required: false }))
      .mockRejectedValueOnce(new ApiError(409, "состояние изменилось"))
      .mockResolvedValueOnce(
        report({ deleted: 3, dry_run: false, force_required: false })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    const apply = await screen.findByRole("button", { name: /применить/i })
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    await userEvent.click(apply)
    expect(await screen.findByText(/принудительный режим/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /применить/i })).toBeDisabled()
    await userEvent.click(screen.getByRole("checkbox"))
    await userEvent.click(screen.getByRole("button", { name: /применить/i }))
    await waitFor(() =>
      expect(
        (
          articlesApi.importTemplate as unknown as {
            mock: { calls: unknown[][] }
          }
        ).mock.calls[2][1]
      ).toEqual({ dryRun: false, force: true })
    )
  })

  it("смена файла сбрасывает согласие и заново снимает превью", async () => {
    vi.spyOn(articlesApi, "importTemplate").mockResolvedValue(
      report({ deleted: 5, force_required: true })
    )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick("a.xlsx")
    await screen.findByText(/удалит/i)
    await userEvent.click(screen.getByRole("checkbox"))
    expect(screen.getByRole("checkbox")).toBeChecked()
    await pick("b.xlsx")
    await screen.findByText(/удалит/i)
    expect(screen.getByRole("checkbox")).not.toBeChecked()
    expect(articlesApi.importTemplate).toHaveBeenCalledTimes(2)
  })

  it("на 400-ошибке файла шлёт тост", async () => {
    vi.spyOn(articlesApi, "importTemplate").mockRejectedValue(
      new ApiError(400, "плохой файл")
    )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/плохой файл/i)
      )
    )
  })
})
```

- [ ] **Step 2: Прогнать — часть падает**

Run: `npx vitest run src/components/articles/TemplateUpload.test.tsx`
Expected: FAIL (минимум тест 400→тост; чекбокс Radix ещё не на месте — возможны падения force-тестов).

- [ ] **Step 3: Переписать TemplateUpload**

Заменить `src/components/articles/TemplateUpload.tsx` целиком:
```tsx
import { useState } from "react"
import { toast } from "sonner"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api/client"
import { importTemplate } from "@/lib/api/articles"
import type { ImportReport } from "@/lib/types"

export function TemplateUpload({ onApplied }: { onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportReport | null>(null)
  const [consent, setConsent] = useState(false)
  const [conflict, setConflict] = useState(false) // 409: состояние БД разошлось с превью
  const [busy, setBusy] = useState(false)

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    // смена файла сбрасывает предыдущее превью, согласие и флаг конфликта
    setPreview(null)
    setConsent(false)
    setConflict(false)
    setFile(f)
    if (!f) return
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось прочитать файл"
      )
    } finally {
      setBusy(false)
    }
  }

  // force требуется, если план превью просит его ИЛИ применение упёрлось в 409-дрейф
  const needsForce = !!preview && (preview.force_required || conflict)

  async function apply() {
    if (busy) return
    if (!file || !preview) return
    setBusy(true)
    try {
      const res = await importTemplate(file, {
        dryRun: false,
        force: needsForce,
      })
      toast.success(
        `Готово: создано ${res.created}, обновлено ${res.updated}, удалено ${res.deleted}, ` +
          `без изменений ${res.unchanged}, ожидают эмбеддинга ${res.pending_embeddings}.`
      )
      setPreview(null)
      setConsent(false)
      setConflict(false)
      onApplied()
    } catch (err) {
      // 409: состояние БД изменилось между превью и применением — поднимаем согласие на force.
      if (err instanceof ApiError && err.status === 409) {
        setConflict(true)
        setConsent(false)
      }
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось применить импорт"
      )
    } finally {
      setBusy(false)
    }
  }

  const applyDisabled = busy || !preview || (needsForce && !consent)

  return (
    <div className="text-sm">
      <Label htmlFor="tpl-file" className="text-xs text-[var(--ds-text-2)]">
        Файл шаблона (.xlsx)
      </Label>
      <Input
        id="tpl-file"
        type="file"
        accept=".xlsx"
        onChange={onPick}
        className="mt-1"
      />

      {busy && <p className="mt-2 text-muted-foreground">Обработка…</p>}

      {preview && (
        <div className="mt-3 rounded-md border border-[var(--ds-hairline)] p-3">
          <p>
            Создано {preview.created}, обновлено {preview.updated}, удалено{" "}
            {preview.deleted}, без изменений {preview.unchanged}, ожидают
            эмбеддинга {preview.pending_embeddings}.
          </p>
          {preview.skipped.length > 0 && (
            <Collapsible className="mt-2">
              <CollapsibleTrigger className="cursor-pointer text-xs text-muted-foreground">
                Пропущено строк: {preview.skipped.length}
              </CollapsibleTrigger>
              <CollapsibleContent>
                <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted-foreground">
                  {preview.skipped.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          )}
          {needsForce && (
            <Alert variant="destructive" className="mt-2">
              <AlertDescription>
                <span>
                  {conflict && !preview.force_required
                    ? "Состояние справочника изменилось с момента превью — для применения нужен принудительный режим."
                    : `Импорт удалит ${preview.deleted} строк (снос корня или большой доли). Это необратимо.`}
                </span>
                <label className="mt-1 flex items-center gap-2 text-xs">
                  <Checkbox
                    checked={consent}
                    onCheckedChange={(c) => setConsent(c === true)}
                  />
                  Да, применить принудительно
                </label>
              </AlertDescription>
            </Alert>
          )}
          <Button
            onClick={() => void apply()}
            disabled={applyDisabled}
            className="mt-3"
          >
            Применить
          </Button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Прогнать — проходит**

Run: `npx vitest run src/components/articles/TemplateUpload.test.tsx`
Expected: PASS (5 тестов).

> Если тест с `screen.getByRole("checkbox")` упадёт из-за того, что `Checkbox` обёрнут в `<label>` и клик ловит label — заменить в тесте `userEvent.click(screen.getByRole("checkbox"))` остаётся валидным (Radix Checkbox имеет `role="checkbox"`); label лишь связывает текст. Если возникнет двойное переключение, убрать обёртку `<label>` и связать через `id`/`htmlFor`: `<Checkbox id="force-consent" .../>` + `<Label htmlFor="force-consent">…</Label>`.

- [ ] **Step 5: Полные проверки + коммит**

Run: `npm run typecheck && npm run lint && npm run test`
```bash
git add -A
git commit -m "feat(front): TemplateUpload на Input file + Checkbox + Alert + Collapsible, итог через тост

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Финал

- [ ] **Прогнать сборку и весь набор проверок**

Run:
```bash
npm run typecheck && npm run lint && npm run test && npm run build
```
Expected: всё зелёное, прод-сборка успешна.

- [ ] **Проверить отсутствие остаточного кастома в охваченных файлах**

Run:
```bash
grep -rn "window.confirm" src/components src/pages/ArticlesPage.tsx || echo "OK: нет window.confirm"
grep -rn "type=\"checkbox\"\|type=\"file\"" src/components/articles || echo "OK: нет сырых input"
```
Expected: подтверждений и сырых input не осталось (в охваченных файлах).

- [ ] **Девлог**

Добавить отчёт в `docs/devlog/` по итогам миграции (кратко: что переведено, какие компоненты добавлены, какие тест-паттерны изменились — моки `sonner`, полифиллы Radix в jsdom).

---

## Self-Review (выполнено при написании плана)

1. **Spec coverage:** Этапы 0–5 покрывают все пункты спеки — примитивы+Toaster (Этап 0), AppShell→Tabs/DropdownMenu (1), Card/Skeleton/Alert (2), AlertDialog+тосты+слово-подтверждение (3), Form+RHF+zod (4), Input file/Checkbox/Alert/Collapsible (5). Estimate не затронут.
2. **Placeholder scan:** плейсхолдеров нет — везде полный код компонентов и тестов.
3. **Type consistency:** `Values`/`schema` определены в каждой форме отдельно; `onDelete?.(a.id)`, `onApplied`, `onCreated`, `onWiped` совпадают с существующими контрактами; импорты из `@/components/ui/*` соответствуют добавляемым в Этапе 0 файлам.
4. **Известные риски:** (а) форма shadcn полагается на ref-as-prop React 19 — у проекта React 19.2, ОК; (б) Radix-оверлеи в jsdom закрыты полифиллами в Этапе 0; (в) `ui/sonner.tsx` правится осознанно (next-themes отсутствует).
