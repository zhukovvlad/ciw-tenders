# Catalog Admin UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подключить фронтенд к реальному бэкенду в части аутентификации и справочника СМР: реальный логин (JWT), просмотр справочника из БД, admin-загрузка шаблона с превью, добавление/удаление статей и полная очистка.

**Architecture:** Тонкий реальный API-слой (`src/lib/api/*`) поверх `fetch` с единым `ApiError`; `AuthContext` хранит JWT в `sessionStorage` и регистрирует `onUnauthorized` в клиенте; страница справочника декомпозирована на presentational-компоненты (`ArticleTable`, `ManualAddForm`, `TemplateUpload`, `WipeCatalog`), оркеструемые `ArticlesPage`. Бэкенд получает один новый admin-роут `DELETE /api/articles`. Поток смет (`pages/estimate/`) остаётся на моках.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0, pytest, uv. Frontend — React + TypeScript + Vite, Tailwind v4 + shadcn/ui, vitest + React Testing Library + user-event.

**Spec:** [docs/superpowers/specs/2026-06-21-catalog-admin-ui-design.md](../specs/2026-06-21-catalog-admin-ui-design.md)

## Global Constraints

- Бэкенд: Clean Architecture `api → services → domain ← infrastructure`; домен без FastAPI/SQLAlchemy/SDK. Новая внешняя операция → порт, затем реализация. ruff line-length 100, target py311, `from __future__ import annotations` во всех модулях, type hints обязательны. Все команды через `uv run` из `backend/`. Юнит-тесты не ходят в реальную БД — фейки портов + `app.dependency_overrides`.
- Фронтенд: eslint строгий; shadcn-компоненты в `src/components/ui/` — вендорные, НЕ править; импорты через alias `@/`; иконки `lucide-react`; TypeScript strict. Тесты — vitest + RTL, мок API-модулей/`fetch` (без реальной сети). Команды из `frontend/`.
- Авторизация — ТОЛЬКО серверная (`require_admin`); клиентский гейтинг по роли — косметика.
- JWT в `sessionStorage` (ключ `ciw.auth.token`), не в localStorage. `client.ts` — единственный, кто читает токен из стораджа; `AuthContext` пишет/чистит тот же ключ.
- Эмбеддер/бэкенд-логика импорта НЕ меняется. `Candidate` (с `section_name`) используется estimate-моками — НЕ трогать. `MOCK_ARTICLES`/`fixtures` используются estimate-моком (`mock/api.ts`) — НЕ удалять.
- Windows PowerShell 5.1: в shell разделитель `;`, не `&&`.

---

### Task 1: Бэкенд — полная очистка справочника (`DELETE /api/articles`)

**Files:**
- Modify: `backend/app/domain/ports.py` (`ArticleRepository`: +`delete_all`)
- Modify: `backend/app/infrastructure/db/article_repository.py` (+`delete_all`)
- Modify: `backend/app/services/article_service.py` (+`delete_all`)
- Modify: `backend/app/api/schemas.py` (+`DeleteAllResponse`)
- Modify: `backend/app/api/routes/articles.py` (+`DELETE ""` роут)
- Modify: `backend/tests/fakes.py` (`FakeRepository`: +`delete_all`)
- Test: `backend/tests/test_article_service.py`, `backend/tests/test_authz_matrix.py`

**Interfaces:**
- Produces: `ArticleRepository.delete_all() -> int` (число удалённых); `ArticleService.delete_all() -> int`; роут `DELETE /api/articles` (admin) → `200 {"deleted": int}`; `DeleteAllResponse {deleted: int}`.

- [ ] **Step 1: Падающий тест сервиса**

В [backend/tests/test_article_service.py](../../../backend/tests/test_article_service.py) добавить:

```python
def test_delete_all_clears_and_returns_count() -> None:
    repo = FakeRepository()
    svc = ArticleService(repo)
    svc.create(article_code="1", name="Раздел")
    svc.create(article_code="2", name="Второй")
    assert svc.delete_all() == 2
    assert svc.list() == []
    assert svc.delete_all() == 0  # повторно — пусто, не ошибка
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_article_service.py::test_delete_all_clears_and_returns_count -v`
Expected: FAIL — `AttributeError: 'ArticleService' object has no attribute 'delete_all'` (или `FakeRepository`).

- [ ] **Step 3: Добавить `delete_all` в порт**

В [backend/app/domain/ports.py](../../../backend/app/domain/ports.py) в класс `ArticleRepository` добавить (после `delete`):

```python
    @abstractmethod
    def delete_all(self) -> int: ...
```

- [ ] **Step 4: Реализовать в фейке и сервисе**

В [backend/tests/fakes.py](../../../backend/tests/fakes.py) в `FakeRepository` добавить:

```python
    def delete_all(self) -> int:
        n = len(self._store)
        self._store = []
        return n
```

В [backend/app/services/article_service.py](../../../backend/app/services/article_service.py) в `ArticleService` добавить:

```python
    def delete_all(self) -> int:
        return self._repository.delete_all()
```

- [ ] **Step 5: Запустить — тест зелёный**

Run: `cd backend; uv run pytest tests/test_article_service.py -v`
Expected: PASS.

- [ ] **Step 6: SQL-реализация `delete_all`**

В [backend/app/infrastructure/db/article_repository.py](../../../backend/app/infrastructure/db/article_repository.py) добавить метод (импорт `delete` из sqlalchemy уже может отсутствовать — добавить в общий импорт `from sqlalchemy import ...`):

```python
    def delete_all(self) -> int:
        result = self._session.execute(delete(TemplateArticleModel))
        self._session.commit()
        return int(result.rowcount or 0)
```

Убедиться, что `delete` импортирован: `from sqlalchemy import Integer, cast, delete, func, select`.

- [ ] **Step 7: DTO ответа**

В [backend/app/api/schemas.py](../../../backend/app/api/schemas.py) добавить:

```python
class DeleteAllResponse(BaseModel):
    deleted: int
```

- [ ] **Step 8: Роут**

В [backend/app/api/routes/articles.py](../../../backend/app/api/routes/articles.py) добавить импорт `DeleteAllResponse` в существующий `from app.api.schemas import ...` и роут (перед `delete_article` по `/{article_id}`, чтобы путь `""` не конфликтовал):

```python
@router.delete("", response_model=DeleteAllResponse, dependencies=[Depends(require_admin)])
def delete_all_articles(
    service: ArticleService = Depends(get_article_service),
) -> DeleteAllResponse:
    return DeleteAllResponse(deleted=service.delete_all())
```

- [ ] **Step 9: Тест авторизации роута**

В [backend/tests/test_authz_matrix.py](../../../backend/tests/test_authz_matrix.py) добавить (точно по стилю файла: `_wire()` + `TestClient(app)` + bearer-токены `token::1` admin / `token::2` user):

```python
def test_delete_all_articles_forbidden_for_user() -> None:
    _wire()
    client = TestClient(app)
    resp = client.delete("/api/articles", headers={"Authorization": "Bearer token::2"})
    assert resp.status_code == 403


def test_delete_all_articles_allowed_for_admin() -> None:
    _wire()
    client = TestClient(app)
    resp = client.delete("/api/articles", headers={"Authorization": "Bearer token::1"})
    assert resp.status_code == 200
    assert "deleted" in resp.json()
```

- [ ] **Step 10: Прогон и линт**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: всё PASS, ruff чисто.

- [ ] **Step 11: Commit**

```bash
git add backend/app/domain/ports.py backend/app/infrastructure/db/article_repository.py backend/app/services/article_service.py backend/app/api/schemas.py backend/app/api/routes/articles.py backend/tests/fakes.py backend/tests/test_article_service.py backend/tests/test_authz_matrix.py
git commit -m "feat(api): DELETE /api/articles — полная очистка справочника (admin)"
```

---

### Task 2: Frontend — типы + API-клиент (`client.ts`)

**Files:**
- Modify: `frontend/src/lib/types.ts` (+`Article`, `AuthUser`, `ImportReport`)
- Create: `frontend/src/lib/api/client.ts`
- Test: `frontend/src/lib/api/client.test.ts`

**Interfaces:**
- Produces: `AUTH_TOKEN_KEY` (`"ciw.auth.token"`); `class ApiError extends Error { status: number }`; `setOnUnauthorized(cb: (() => void) | null): void`; `apiGet<T>(path): Promise<T>`; `apiSend<T>(method, path, body?): Promise<T>`; `apiUpload<T>(path, file): Promise<T>`. Все шлют на `/api${path}`, подставляют `Authorization: Bearer <token>` из `sessionStorage`. На `401` зовут `onUnauthorized` и бросают `ApiError`. Сетевой сбой → `ApiError(0, …)`.

- [ ] **Step 1: Добавить типы**

В [frontend/src/lib/types.ts](../../../frontend/src/lib/types.ts) добавить (НЕ трогая существующий `Candidate`):

```ts
export interface Article {
  id: number
  article_code: string
  name: string
  parent_id: number | null
}

export interface AuthUser {
  id: number
  email: string
  role: "user" | "admin"
  is_active: boolean
}

export interface ImportReport {
  created: number
  updated: number
  deleted: number
  unchanged: number
  skipped: string[]
  pending_embeddings: number
  dry_run: boolean
  force_required: boolean
}
```

- [ ] **Step 2: Падающий тест клиента**

Создать `frontend/src/lib/api/client.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiGet, apiSend, apiUpload, AUTH_TOKEN_KEY, setOnUnauthorized } from "./client"

function mockFetch(status: number, body: unknown, ok = status < 400) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "x",
    json: async () => body,
  } as Response)
}

afterEach(() => {
  sessionStorage.clear()
  setOnUnauthorized(null)
  vi.restoreAllMocks()
})

describe("api client", () => {
  it("apiGet шлёт Bearer-токен и парсит JSON", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")
    const f = mockFetch(200, [{ id: 1 }])
    vi.stubGlobal("fetch", f)
    const out = await apiGet<{ id: number }[]>("/articles")
    expect(out).toEqual([{ id: 1 }])
    const [url, init] = f.mock.calls[0]
    expect(url).toBe("/api/articles")
    expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer tok" })
  })

  it("на 401 зовёт onUnauthorized и бросает ApiError", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { detail: "no" }, false))
    const onUnauth = vi.fn()
    setOnUnauthorized(onUnauth)
    await expect(apiSend("POST", "/x", {})).rejects.toBeInstanceOf(ApiError)
    expect(onUnauth).toHaveBeenCalledOnce()
  })

  it("вытягивает detail.message из тела 409", async () => {
    vi.stubGlobal("fetch", mockFetch(409, { detail: { message: "конфликт", deleted: 3 } }, false))
    await expect(apiSend("POST", "/x", {})).rejects.toMatchObject({ status: 409, message: "конфликт" })
  })

  it("сетевой сбой → ApiError(0)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")))
    await expect(apiGet("/x")).rejects.toMatchObject({ status: 0 })
  })

  it("apiUpload шлёт FormData без ручного Content-Type", async () => {
    const f = mockFetch(200, { created: 1 })
    vi.stubGlobal("fetch", f)
    await apiUpload("/articles/import?dry_run=true&force=false", new File(["x"], "t.xlsx"))
    const [, init] = f.mock.calls[0]
    const headers = (init as RequestInit).headers as Record<string, string>
    expect(headers["Content-Type"]).toBeUndefined()
    expect((init as RequestInit).body).toBeInstanceOf(FormData)
  })
})
```

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/api/client.test.ts`
Expected: FAIL — модуль `./client` не существует.

- [ ] **Step 4: Реализовать клиент**

Создать `frontend/src/lib/api/client.ts`:

```ts
export const AUTH_TOKEN_KEY = "ciw.auth.token"

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

let onUnauthorized: (() => void) | null = null
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorized = cb
}

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError(0, "Сеть недоступна — проверьте подключение")
  }
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      const detail = body?.detail
      if (typeof detail === "string") message = detail
      else if (detail && typeof (detail as { message?: unknown }).message === "string")
        message = (detail as { message: string }).message
    } catch {
      // тело не JSON — оставляем statusText
    }
    if (res.status === 401) onUnauthorized?.()
    throw new ApiError(res.status, message)
  }
  return res
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await request(path, { headers: { ...authHeaders() } })
  return res.json() as Promise<T>
}

export async function apiSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await request(path, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append("file", file)
  // Content-Type НЕ ставим — браузер сам выставит multipart boundary.
  const res = await request(path, { method: "POST", headers: { ...authHeaders() }, body: form })
  return res.json() as Promise<T>
}
```

- [ ] **Step 5: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/lib/api/client.test.ts`
Expected: PASS (5 тестов).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api/client.ts frontend/src/lib/api/client.test.ts
git commit -m "feat(web): API-клиент (ApiError, Bearer из sessionStorage, onUnauthorized, multipart)"
```

---

### Task 3: Frontend — API-модули `auth` и `articles`

**Files:**
- Create: `frontend/src/lib/api/auth.ts`
- Create: `frontend/src/lib/api/articles.ts`
- Test: `frontend/src/lib/api/articles.test.ts`

**Interfaces:**
- Consumes: `apiGet/apiSend/apiUpload` (Task 2), `Article`/`AuthUser`/`ImportReport` (Task 2).
- Produces: `auth.login(email, password): Promise<string>`; `auth.me(): Promise<AuthUser>`; `articles.listArticles(): Promise<Article[]>`; `articles.createArticle({article_code, name, parent_code?}): Promise<Article>`; `articles.deleteArticle(id): Promise<void>`; `articles.deleteAllArticles(): Promise<number>`; `articles.importTemplate(file, {dryRun, force}): Promise<ImportReport>`.

- [ ] **Step 1: Падающий тест articles-модуля**

Создать `frontend/src/lib/api/articles.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest"
import * as client from "./client"
import {
  createArticle,
  deleteAllArticles,
  deleteArticle,
  importTemplate,
  listArticles,
} from "./articles"

afterEach(() => vi.restoreAllMocks())

describe("articles api", () => {
  it("listArticles тянет с limit=1000", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue([])
    await listArticles()
    expect(spy).toHaveBeenCalledWith("/articles?limit=1000")
  })

  it("createArticle шлёт POST с телом", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue({ id: 1 })
    await createArticle({ article_code: "1.1", name: "n", parent_code: "1" })
    expect(spy).toHaveBeenCalledWith("POST", "/articles", {
      article_code: "1.1",
      name: "n",
      parent_code: "1",
    })
  })

  it("deleteAllArticles возвращает число", async () => {
    vi.spyOn(client, "apiSend").mockResolvedValue({ deleted: 7 })
    expect(await deleteAllArticles()).toBe(7)
  })

  it("deleteArticle шлёт DELETE по id", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await deleteArticle(42)
    expect(spy).toHaveBeenCalledWith("DELETE", "/articles/42")
  })

  it("importTemplate кодирует dry_run/force в query", async () => {
    const spy = vi.spyOn(client, "apiUpload").mockResolvedValue({} as never)
    const file = new File(["x"], "t.xlsx")
    await importTemplate(file, { dryRun: true, force: false })
    expect(spy).toHaveBeenCalledWith("/articles/import?dry_run=true&force=false", file)
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/api/articles.test.ts`
Expected: FAIL — модуль `./articles` не существует.

- [ ] **Step 3: Реализовать `auth.ts`**

Создать `frontend/src/lib/api/auth.ts`:

```ts
import type { AuthUser } from "@/lib/types"
import { apiGet, apiSend } from "./client"

export function login(email: string, password: string): Promise<string> {
  return apiSend<{ access_token: string }>("POST", "/auth/login", { email, password }).then(
    (r) => r.access_token,
  )
}

export function me(): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me")
}
```

- [ ] **Step 4: Реализовать `articles.ts`**

Создать `frontend/src/lib/api/articles.ts`:

```ts
import type { Article, ImportReport } from "@/lib/types"
import { apiGet, apiSend, apiUpload } from "./client"

export function listArticles(): Promise<Article[]> {
  return apiGet<Article[]>("/articles?limit=1000")
}

export function createArticle(input: {
  article_code: string
  name: string
  parent_code?: string | null
}): Promise<Article> {
  return apiSend<Article>("POST", "/articles", input)
}

export function deleteArticle(id: number): Promise<void> {
  return apiSend<void>("DELETE", `/articles/${id}`)
}

export function deleteAllArticles(): Promise<number> {
  return apiSend<{ deleted: number }>("DELETE", "/articles").then((r) => r.deleted)
}

export function importTemplate(
  file: File,
  opts: { dryRun: boolean; force: boolean },
): Promise<ImportReport> {
  return apiUpload<ImportReport>(
    `/articles/import?dry_run=${opts.dryRun}&force=${opts.force}`,
    file,
  )
}
```

- [ ] **Step 5: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/lib/api/articles.test.ts`
Expected: PASS (5 тестов).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api/auth.ts frontend/src/lib/api/articles.ts frontend/src/lib/api/articles.test.ts
git commit -m "feat(web): API-модули auth и articles"
```

---

### Task 4: Frontend — AuthContext

**Files:**
- Create: `frontend/src/lib/auth/AuthContext.tsx`
- Test: `frontend/src/lib/auth/AuthContext.test.tsx`

**Interfaces:**
- Consumes: `auth.login`/`auth.me` (Task 3), `AUTH_TOKEN_KEY`/`ApiError`/`setOnUnauthorized` (Task 2).
- Produces: `<AuthProvider>`; `useAuth(): { user: AuthUser | null; role: "user"|"admin"|null; loading: boolean; error: string | null; login(email,password): Promise<void>; logout(): void }`. Логин кладёт токен в `sessionStorage` и заполняет `user` через `me()`. Стартовая валидация: `401 → logout`; сеть/`5xx → токен сохранён`, `error` выставлен. `logout` чистит токен и `user`.

- [ ] **Step 1: Падающий тест контекста**

Создать `frontend/src/lib/auth/AuthContext.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError, AUTH_TOKEN_KEY } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import { AuthProvider, useAuth } from "./AuthContext"

const ADMIN = { id: 1, email: "a@mr.kz", role: "admin" as const, is_active: true }

function Probe() {
  const { user, role, loading, error, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="state">
        {loading ? "loading" : user ? `${user.email}:${role}` : error ? `err:${error}` : "anon"}
      </span>
      <button onClick={() => login("a@mr.kz", "pw")}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe("AuthContext", () => {
  it("без токена — anon, не loading", async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
  })

  it("login кладёт токен и заполняет user", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue("tok")
    vi.spyOn(authApi, "me").mockResolvedValue(ADMIN)
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    await userEvent.click(screen.getByText("login"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("a@mr.kz:admin"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("tok")
  })

  it("стартовый 401 на me() → logout (токен очищен)", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "stale")
    vi.spyOn(authApi, "me").mockRejectedValue(new ApiError(401, "no"))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })

  it("стартовая сеть/5xx на me() → токен СОХРАНЁН, показана ошибка", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "good")
    vi.spyOn(authApi, "me").mockRejectedValue(new ApiError(503, "down"))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("err:"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("good")
  })

  it("logout чистит токен и user", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue("tok")
    vi.spyOn(authApi, "me").mockResolvedValue(ADMIN)
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText("login"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("a@mr.kz:admin"))
    await userEvent.click(screen.getByText("logout"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/lib/auth/AuthContext.test.tsx`
Expected: FAIL — модуль `./AuthContext` не существует.

- [ ] **Step 3: Реализовать AuthContext**

Создать `frontend/src/lib/auth/AuthContext.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useState } from "react"
import { ApiError, AUTH_TOKEN_KEY, setOnUnauthorized } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import type { AuthUser } from "@/lib/types"

interface AuthContextValue {
  user: AuthUser | null
  role: "user" | "admin" | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const logout = useCallback(() => {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    setOnUnauthorized(logout)
    return () => setOnUnauthorized(null)
  }, [logout])

  useEffect(() => {
    const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
    if (!token) {
      setLoading(false)
      return
    }
    let cancelled = false
    authApi
      .me()
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 401) logout()
        else setError("Бэкенд недоступен — попробуйте позже")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    setError(null)
    const token = await authApi.login(email, password)
    sessionStorage.setItem(AUTH_TOKEN_KEY, token)
    setUser(await authApi.me())
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, role: user?.role ?? null, loading, error, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth вызван вне AuthProvider")
  return ctx
}
```

- [ ] **Step 4: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/lib/auth/AuthContext.test.tsx`
Expected: PASS (5 тестов).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/auth/AuthContext.tsx frontend/src/lib/auth/AuthContext.test.tsx
git commit -m "feat(web): AuthContext (JWT в sessionStorage, старт 401→logout / 5xx→сохранить)"
```

---

### Task 5: Frontend — реальный логин, AuthGate, AppShell, монтаж

**Files:**
- Modify: `frontend/src/components/auth/LoginScreen.tsx`
- Modify: `frontend/src/components/auth/AuthGate.tsx`
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/lib/mock/auth.ts`
- Modify/Delete tests: `frontend/src/components/auth/AuthGate.test.tsx`, `frontend/src/App.test.tsx`
- Test: `frontend/src/components/auth/LoginScreen.test.tsx`

**Interfaces:**
- Consumes: `useAuth`/`AuthProvider` (Task 4), `ApiError` (Task 2).
- Produces: `LoginScreen` (без пропсов, берёт `login` из контекста); `AuthGate` (ждёт `loading`, показывает `LoginScreen` или children); `AppShell` (email+роль из контекста, `logout` из контекста); `App` оборачивает всё в `AuthProvider`.

- [ ] **Step 1: Падающий тест LoginScreen**

Создать `frontend/src/components/auth/LoginScreen.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError } from "@/lib/api/client"
import { AuthProvider } from "@/lib/auth/AuthContext"
import * as authApi from "@/lib/api/auth"
import { LoginScreen } from "./LoginScreen"

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

it("на 401 показывает «неверный логин или пароль»", async () => {
  vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "bad"))
  render(<AuthProvider><LoginScreen /></AuthProvider>)
  await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
  await userEvent.type(screen.getByLabelText(/пароль/i), "x")
  await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
  expect(await screen.findByText(/неверный логин или пароль/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/auth/LoginScreen.test.tsx`
Expected: FAIL (LoginScreen ещё ждёт проп `onSuccess` / использует мок).

- [ ] **Step 3: Переписать LoginScreen на контекст**

Заменить содержимое [frontend/src/components/auth/LoginScreen.tsx](../../../frontend/src/components/auth/LoginScreen.tsx):

```tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/AuthContext"

export function LoginScreen() {
  const { login } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Неверный логин или пароль"
          : "Не удалось войти, попробуйте позже",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
      </div>
      <div className="mb-5 text-xs text-muted-foreground">Автоматизатор строительных смет</div>
      <form onSubmit={submit} className="flex w-60 flex-col gap-3">
        <label className="text-xs text-[var(--ds-text-2)]">
          Логин
          <Input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" />
        </label>
        <label className="text-xs text-[var(--ds-text-2)]">
          Пароль
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1"
          />
        </label>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" disabled={busy}>
          Войти
        </Button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Переписать AuthGate на контекст**

Заменить содержимое [frontend/src/components/auth/AuthGate.tsx](../../../frontend/src/components/auth/AuthGate.tsx):

```tsx
import { useAuth } from "@/lib/auth/AuthContext"
import { LoginScreen } from "@/components/auth/LoginScreen"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading)
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Загрузка…
      </div>
    )
  if (!user) return <LoginScreen />
  return <>{children}</>
}
```

- [ ] **Step 5: Обновить AppShell (email/роль + logout из контекста)**

В [frontend/src/components/AppShell.tsx](../../../frontend/src/components/AppShell.tsx) заменить импорт `import { logout } from "@/lib/mock/auth"` на `import { useAuth } from "@/lib/auth/AuthContext"`, добавить в начало компонента `const { user, role, logout } = useAuth()`, и заменить кнопку «Выйти»:

```tsx
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {user && (
            <span>
              {user.email} · {role === "admin" ? "админ" : "пользователь"}
            </span>
          )}
          <button
            onClick={() => {
              clearReview()
              logout()
            }}
            className="hover:text-foreground"
          >
            Выйти
          </button>
        </div>
```

(Убрать `location.reload()` — контекст сам перерисует на `LoginScreen`. Импорт `clearReview` оставить.)

- [ ] **Step 6: Обернуть App в AuthProvider**

Заменить содержимое [frontend/src/App.tsx](../../../frontend/src/App.tsx):

```tsx
import { useState } from "react"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"

export function App() {
  const [tab, setTab] = useState<"estimate" | "articles">("estimate")
  return (
    <AuthProvider>
      <AuthGate>
        <AppShell tab={tab} onTab={setTab}>
          {tab === "estimate" ? <EstimateFlow /> : <ArticlesPage />}
        </AppShell>
      </AuthGate>
    </AuthProvider>
  )
}

export default App
```

- [ ] **Step 7: Удалить мок-auth и починить его тесты**

Удалить `frontend/src/lib/mock/auth.ts`.

Заменить содержимое [frontend/src/components/auth/AuthGate.test.tsx](../../../frontend/src/components/auth/AuthGate.test.tsx):

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { AUTH_TOKEN_KEY } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { AuthGate } from "./AuthGate"

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe("AuthGate", () => {
  it("без токена показывает форму входа, не контент", async () => {
    render(
      <AuthProvider>
        <AuthGate>
          <div>Секрет</div>
        </AuthGate>
      </AuthProvider>,
    )
    expect(await screen.findByRole("button", { name: /Войти/ })).toBeInTheDocument()
    expect(screen.queryByText("Секрет")).not.toBeInTheDocument()
  })

  it("с валидным токеном показывает контент", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "admin",
      is_active: true,
    })
    render(
      <AuthProvider>
        <AuthGate>
          <div>Секрет</div>
        </AuthGate>
      </AuthProvider>,
    )
    expect(await screen.findByText("Секрет")).toBeInTheDocument()
  })
})
```

Открыть `frontend/src/App.test.tsx`: оно импортирует `AUTH_KEY` из удалённого мока. Если тест проверяет мок-флоу логина — переписать под `AuthProvider` + мок `authApi.me` (по образцу выше) либо, если он лишь дымовой, упростить до проверки рендера `LoginScreen` без токена. Конкретно: заменить `import { AUTH_KEY } from "@/lib/mock/auth"` и установку `localStorage.setItem(AUTH_KEY,...)` на `sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")` + `vi.spyOn(authApi,"me").mockResolvedValue(<admin>)`, обернуть рендер в `<AuthProvider>`.

- [ ] **Step 8: Прогон тестов + typecheck**

Run: `cd frontend; npx vitest run src/components src/App.test.tsx; npm run typecheck`
Expected: PASS; типы чисты. (Если `App.test.tsx` всё ещё на моке — доправить по Step 7.)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/auth/LoginScreen.tsx frontend/src/components/auth/LoginScreen.test.tsx frontend/src/components/auth/AuthGate.tsx frontend/src/components/auth/AuthGate.test.tsx frontend/src/components/AppShell.tsx frontend/src/App.tsx frontend/src/App.test.tsx
git rm frontend/src/lib/mock/auth.ts
git commit -m "feat(web): реальный логин/AuthGate/AppShell на AuthContext, удалить mock/auth"
```

---

### Task 6: Frontend — таблица справочника + страница (список, отступ, поиск, состояния, роль)

**Files:**
- Create: `frontend/src/components/articles/ArticleTable.tsx`
- Modify: `frontend/src/pages/ArticlesPage.tsx` (полная замена мок-версии)
- Test: `frontend/src/components/articles/ArticleTable.test.tsx`, `frontend/src/pages/ArticlesPage.test.tsx`

**Interfaces:**
- Consumes: `Article` (Task 2), `listArticles` (Task 3), `useAuth` (Task 4).
- Produces: `ArticleTable({ articles, isAdmin, onDelete }: { articles: Article[]; isAdmin: boolean; onDelete?: (id: number) => void })` — таблица с отступом по глубине + клиентский поиск. `ArticlesPage` — грузит список, держит `reload()`, состояния loading/error/empty, прокидывает `isAdmin`. (Admin-формы добавятся в Task 7-9.)

- [ ] **Step 1: Падающий тест ArticleTable**

Создать `frontend/src/components/articles/ArticleTable.test.tsx`:

```tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { Article } from "@/lib/types"
import { ArticleTable } from "./ArticleTable"

const ARTS: Article[] = [
  { id: 1, article_code: "1", name: "Подготовка", parent_id: null },
  { id: 2, article_code: "1.1", name: "Котлован", parent_id: 1 },
  { id: 3, article_code: "2", name: "Фасады", parent_id: null },
]

describe("ArticleTable", () => {
  it("рендерит все строки", () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    expect(screen.getByText("Подготовка")).toBeInTheDocument()
    expect(screen.getByText("Котлован")).toBeInTheDocument()
    expect(screen.getByText("Фасады")).toBeInTheDocument()
  })

  it("фильтрует по коду или имени", async () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    await userEvent.type(screen.getByPlaceholderText(/поиск/i), "фасад")
    expect(screen.getByText("Фасады")).toBeInTheDocument()
    expect(screen.queryByText("Подготовка")).not.toBeInTheDocument()
  })

  it("у не-админа нет кнопок удаления", () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    expect(screen.queryByLabelText(/удалить/i)).not.toBeInTheDocument()
  })

  it("у админа клик по удалению зовёт onDelete с id", async () => {
    const onDelete = vi.fn()
    render(<ArticleTable articles={ARTS} isAdmin onDelete={onDelete} />)
    await userEvent.click(screen.getAllByLabelText(/удалить/i)[0])
    expect(onDelete).toHaveBeenCalledWith(1)
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/articles/ArticleTable.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать ArticleTable**

Создать `frontend/src/components/articles/ArticleTable.tsx`:

```tsx
import { useMemo, useState } from "react"
import { Trash2 } from "lucide-react"
import { Input } from "@/components/ui/input"
import type { Article } from "@/lib/types"

interface ArticleTableProps {
  articles: Article[]
  isAdmin: boolean
  onDelete?: (id: number) => void
}

export function ArticleTable({ articles, isAdmin, onDelete }: ArticleTableProps) {
  const [query, setQuery] = useState("")
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return articles
    return articles.filter(
      (a) => a.article_code.toLowerCase().includes(q) || a.name.toLowerCase().includes(q),
    )
  }, [articles, query])

  return (
    <div>
      <Input
        placeholder="Поиск по коду или наименованию"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="mb-3 max-w-sm"
      />
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs tracking-wide text-muted-foreground uppercase">
            <th className="px-4 py-2.5 font-normal">Код</th>
            <th className="px-4 py-2.5 font-normal">Наименование</th>
            {isAdmin && <th className="w-10" />}
          </tr>
        </thead>
        <tbody>
          {filtered.map((a) => {
            const depth = a.article_code.split(".").length - 1
            return (
              <tr key={a.id} className="border-t border-[var(--ds-hairline)]">
                <td className="px-4 py-2 font-mono text-xs">{a.article_code}</td>
                <td className="px-4 py-2" style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
                  {a.name}
                </td>
                {isAdmin && (
                  <td className="px-4 py-2">
                    <button aria-label="Удалить" onClick={() => onDelete?.(a.id)}>
                      <Trash2 className="size-4 text-destructive" />
                    </button>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 4: Запустить — тесты ArticleTable зелёные**

Run: `cd frontend; npx vitest run src/components/articles/ArticleTable.test.tsx`
Expected: PASS (4 теста).

- [ ] **Step 5: Падающий тест ArticlesPage (загрузка/состояния/роль)**

Создать `frontend/src/pages/ArticlesPage.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import type { AuthUser } from "@/lib/types"
import * as articlesApi from "@/lib/api/articles"
import * as authCtx from "@/lib/auth/AuthContext"
import { ArticlesPage } from "./ArticlesPage"

const USER: AuthUser = { id: 2, email: "u@mr.kz", role: "user", is_active: true }
const ADMIN: AuthUser = { id: 1, email: "a@mr.kz", role: "admin", is_active: true }

function mockAuth(user: AuthUser) {
  vi.spyOn(authCtx, "useAuth").mockReturnValue({
    user,
    role: user.role,
    loading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
  })
}

afterEach(() => vi.restoreAllMocks())

describe("ArticlesPage", () => {
  it("показывает список после загрузки", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([
      { id: 1, article_code: "1", name: "Подготовка", parent_id: null },
    ])
    render(<ArticlesPage />)
    expect(await screen.findByText("Подготовка")).toBeInTheDocument()
  })

  it("пустой справочник — подсказка", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    expect(await screen.findByText(/справочник пуст/i)).toBeInTheDocument()
  })

  it("ошибка загрузки — сообщение + повтор", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockRejectedValue(new Error("fail"))
    render(<ArticlesPage />)
    expect(await screen.findByText(/не удалось загрузить/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /повторить/i })).toBeInTheDocument()
  })

  it("не-админ не видит admin-секций (загрузка шаблона)", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    await screen.findByText(/справочник пуст/i)
    expect(screen.queryByText(/загрузить шаблон/i)).not.toBeInTheDocument()
  })

  it("админ видит секцию загрузки шаблона", async () => {
    mockAuth(ADMIN)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    expect(await screen.findByText(/загрузить шаблон/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Реализовать ArticlesPage**

Заменить содержимое [frontend/src/pages/ArticlesPage.tsx](../../../frontend/src/pages/ArticlesPage.tsx):

```tsx
import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { ArticleTable } from "@/components/articles/ArticleTable"
import { listArticles, deleteArticle } from "@/lib/api/articles"
import { useAuth } from "@/lib/auth/AuthContext"
import type { Article } from "@/lib/types"

export function ArticlesPage() {
  const { role } = useAuth()
  const isAdmin = role === "admin"
  const [articles, setArticles] = useState<Article[]>([])
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading")

  const reload = useCallback(async () => {
    setStatus("loading")
    try {
      setArticles(await listArticles())
      setStatus("ready")
    } catch {
      setStatus("error")
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  async function handleDelete(id: number) {
    if (!window.confirm("Удалить статью?")) return
    await deleteArticle(id)
    await reload()
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">Справочник СМР</h2>
      <p className="mb-4 text-sm text-muted-foreground">Эталонные статьи строительных работ.</p>

      {/* Admin-секции загрузки/добавления/очистки добавляются в Task 7-9 */}
      {isAdmin && (
        <div className="mb-6 rounded-md border border-[var(--ds-hairline)] p-4">
          <h3 className="mb-2 text-sm font-medium">Загрузить шаблон</h3>
          <p className="text-xs text-muted-foreground">
            Доступно в следующих задачах плана (Task 8).
          </p>
        </div>
      )}

      {status === "loading" && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {status === "error" && (
        <div className="text-sm">
          <p className="mb-2 text-destructive">Не удалось загрузить справочник.</p>
          <Button onClick={() => void reload()}>Повторить</Button>
        </div>
      )}
      {status === "ready" && articles.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Справочник пуст{isAdmin ? " — загрузите шаблон." : "."}
        </p>
      )}
      {status === "ready" && articles.length > 0 && (
        <ArticleTable articles={articles} isAdmin={isAdmin} onDelete={handleDelete} />
      )}
    </div>
  )
}

export default ArticlesPage
```

Примечание: `window.confirm` в тесте удаления (Task 7) мокается через `vi.spyOn(window, "confirm")`.

- [ ] **Step 7: Запустить — тесты ArticlesPage зелёные**

Run: `cd frontend; npx vitest run src/pages/ArticlesPage.test.tsx`
Expected: PASS (5 тестов).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/articles/ArticleTable.tsx frontend/src/components/articles/ArticleTable.test.tsx frontend/src/pages/ArticlesPage.tsx frontend/src/pages/ArticlesPage.test.tsx
git commit -m "feat(web): справочник из БД — таблица с отступом, поиск, состояния, роль"
```

---

### Task 7: Frontend — ручное добавление статьи (admin)

**Files:**
- Create: `frontend/src/components/articles/ManualAddForm.tsx`
- Modify: `frontend/src/pages/ArticlesPage.tsx` (подключить форму для admin)
- Test: `frontend/src/components/articles/ManualAddForm.test.tsx`

**Interfaces:**
- Consumes: `createArticle` (Task 3), `ApiError` (Task 2).
- Produces: `ManualAddForm({ onCreated }: { onCreated: () => void })` — поля `article_code`, `name`, `parent_code?`; на успех зовёт `onCreated` и чистит поля; на `ApiError` (400/409) показывает `message`.

- [ ] **Step 1: Падающий тест формы**

Создать `frontend/src/components/articles/ManualAddForm.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { ManualAddForm } from "./ManualAddForm"

afterEach(() => vi.restoreAllMocks())

describe("ManualAddForm", () => {
  it("создаёт статью и зовёт onCreated", async () => {
    const onCreated = vi.fn()
    const spy = vi
      .spyOn(articlesApi, "createArticle")
      .mockResolvedValue({ id: 1, article_code: "1", name: "Раздел", parent_id: null })
    render(<ManualAddForm onCreated={onCreated} />)
    await userEvent.type(screen.getByLabelText(/код/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Раздел")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(spy).toHaveBeenCalledWith({ article_code: "1", name: "Раздел", parent_code: null })
    expect(onCreated).toHaveBeenCalledOnce()
  })

  it("показывает ошибку бэкенда (409 дубликат)", async () => {
    vi.spyOn(articlesApi, "createArticle").mockRejectedValue(new ApiError(409, "уже существует"))
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/код/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Дубль")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(await screen.findByText(/уже существует/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/articles/ManualAddForm.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать ManualAddForm**

Создать `frontend/src/components/articles/ManualAddForm.tsx`:

```tsx
import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { createArticle } from "@/lib/api/articles"

const EMPTY = { article_code: "", name: "", parent_code: "" }

export function ManualAddForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.article_code.trim() || !form.name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await createArticle({
        article_code: form.article_code.trim(),
        name: form.name.trim(),
        parent_code: form.parent_code.trim() || null,
      })
      setForm(EMPTY)
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось добавить статью")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[160px_1fr_160px_auto]">
      <label className="text-xs text-[var(--ds-text-2)]">
        Код
        <Input
          value={form.article_code}
          onChange={(e) => setForm({ ...form, article_code: e.target.value })}
          className="mt-1"
        />
      </label>
      <label className="text-xs text-[var(--ds-text-2)]">
        Наименование
        <Input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="mt-1"
        />
      </label>
      <label className="text-xs text-[var(--ds-text-2)]">
        Код родителя (необязательно)
        <Input
          value={form.parent_code}
          onChange={(e) => setForm({ ...form, parent_code: e.target.value })}
          className="mt-1"
        />
      </label>
      <Button type="submit" disabled={busy} className="self-end">
        <Plus className="size-4" />
        Добавить
      </Button>
      {error && <p className="text-xs text-destructive sm:col-span-4">{error}</p>}
    </form>
  )
}
```

- [ ] **Step 4: Подключить форму в ArticlesPage (admin)**

В [frontend/src/pages/ArticlesPage.tsx](../../../frontend/src/pages/ArticlesPage.tsx) добавить импорт `import { ManualAddForm } from "@/components/articles/ManualAddForm"` и внутри `isAdmin`-блока (под заглушкой/секцией) вставить:

```tsx
        <div className="mt-4 border-t border-[var(--ds-hairline)] pt-4">
          <h3 className="mb-2 text-sm font-medium">Добавить статью вручную</h3>
          <ManualAddForm onCreated={() => void reload()} />
        </div>
```

- [ ] **Step 5: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/components/articles/ManualAddForm.test.tsx src/pages/ArticlesPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/articles/ManualAddForm.tsx frontend/src/components/articles/ManualAddForm.test.tsx frontend/src/pages/ArticlesPage.tsx
git commit -m "feat(web): ручное добавление статьи справочника (admin, 400/409)"
```

---

### Task 8: Frontend — загрузка шаблона (превью → согласие → применение)

**Files:**
- Create: `frontend/src/components/articles/TemplateUpload.tsx`
- Modify: `frontend/src/pages/ArticlesPage.tsx` (заменить заглушку секции загрузки на компонент)
- Test: `frontend/src/components/articles/TemplateUpload.test.tsx`

**Interfaces:**
- Consumes: `importTemplate` (Task 3), `ImportReport` (Task 2), `ApiError`.
- Produces: `TemplateUpload({ onApplied }: { onApplied: () => void })` — выбор файла → dry-run превью → (если `force_required` — обязательный чекбокс) → «Применить» → `onApplied`. Смена файла сбрасывает превью и согласие. Финальный отчёт без повторного force-ворнинга.

- [ ] **Step 1: Падающий тест загрузки**

Создать `frontend/src/components/articles/TemplateUpload.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { ImportReport } from "@/lib/types"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { TemplateUpload } from "./TemplateUpload"

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
  return userEvent.upload(screen.getByLabelText(/файл шаблона/i), new File(["x"], name))
}

afterEach(() => vi.restoreAllMocks())

describe("TemplateUpload", () => {
  it("превью (dry_run) затем применение (dry_run=false)", async () => {
    const spy = vi
      .spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ created: 362, pending_embeddings: 362 }))
      .mockResolvedValueOnce(report({ created: 362, dry_run: false, pending_embeddings: 362 }))
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    expect(await screen.findByText(/создано/i)).toBeInTheDocument()
    expect(spy.mock.calls[0][1]).toEqual({ dryRun: true, force: false })
    await userEvent.click(screen.getByRole("button", { name: /применить/i }))
    await waitFor(() => expect(spy.mock.calls[1][1]).toEqual({ dryRun: false, force: false }))
  })

  it("force_required: «Применить» заблокирована до чекбокса, затем шлёт force:true", async () => {
    vi.spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ deleted: 5, force_required: true }))
      .mockResolvedValueOnce(report({ deleted: 5, dry_run: false, force_required: true }))
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
        (articlesApi.importTemplate as unknown as { mock: { calls: unknown[][] } }).mock.calls[1][1],
      ).toEqual({ dryRun: false, force: true }),
    )
  })

  it("смена файла сбрасывает согласие и заново снимает превью", async () => {
    // оба файла требуют force → проверяем, что согласие сбрасывается при смене файла
    vi.spyOn(articlesApi, "importTemplate").mockResolvedValue(
      report({ deleted: 5, force_required: true }),
    )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick("a.xlsx")
    await screen.findByText(/удалит/i)
    await userEvent.click(screen.getByRole("checkbox"))
    expect(screen.getByRole("checkbox")).toBeChecked()
    await pick("b.xlsx") // смена файла
    await screen.findByText(/удалит/i)
    // согласие сброшено, dry-run перезапущен (2 вызова)
    expect(screen.getByRole("checkbox")).not.toBeChecked()
    expect(articlesApi.importTemplate).toHaveBeenCalledTimes(2)
  })

  it("показывает 400-ошибку файла", async () => {
    vi.spyOn(articlesApi, "importTemplate").mockRejectedValue(new ApiError(400, "плохой файл"))
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    expect(await screen.findByText(/плохой файл/i)).toBeInTheDocument()
  })
})
```

Примечание: для детерминизма обе ветки `pick` используют мок с синхронным резолвом; ассерты опираются на наблюдаемое состояние (сброшенный чекбокс + счётчик вызовов), а не на гонку рендера. Добавить `import { ApiError } from "@/lib/api/client"` в начало теста.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/articles/TemplateUpload.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать TemplateUpload**

Создать `frontend/src/components/articles/TemplateUpload.tsx`:

```tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api/client"
import { importTemplate } from "@/lib/api/articles"
import type { ImportReport } from "@/lib/types"

export function TemplateUpload({ onApplied }: { onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportReport | null>(null)
  const [consent, setConsent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [doneMsg, setDoneMsg] = useState<string | null>(null)

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    // смена файла сбрасывает предыдущее превью и согласие
    setPreview(null)
    setConsent(false)
    setError(null)
    setDoneMsg(null)
    setFile(f)
    if (!f) return
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось прочитать файл")
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!file || !preview) return
    setBusy(true)
    setError(null)
    try {
      const res = await importTemplate(file, { dryRun: false, force: preview.force_required })
      setDoneMsg(
        `Готово: создано ${res.created}, обновлено ${res.updated}, удалено ${res.deleted}, ` +
          `без изменений ${res.unchanged}, ожидают эмбеддинга ${res.pending_embeddings}.`,
      )
      setPreview(null)
      setConsent(false)
      onApplied()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось применить импорт")
    } finally {
      setBusy(false)
    }
  }

  const applyDisabled = busy || !preview || (preview.force_required && !consent)

  return (
    <div className="text-sm">
      <label className="text-xs text-[var(--ds-text-2)]">
        Файл шаблона (.xlsx)
        <input
          type="file"
          accept=".xlsx"
          onChange={onPick}
          className="mt-1 block text-xs"
        />
      </label>

      {busy && <p className="mt-2 text-muted-foreground">Обработка…</p>}

      {preview && (
        <div className="mt-3 rounded-md border border-[var(--ds-hairline)] p-3">
          <p>
            Создано {preview.created}, обновлено {preview.updated}, удалено {preview.deleted}, без
            изменений {preview.unchanged}, ожидают эмбеддинга {preview.pending_embeddings}.
          </p>
          {preview.skipped.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Пропущено строк: {preview.skipped.length}
              </summary>
              <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted-foreground">
                {preview.skipped.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </details>
          )}
          {preview.force_required && (
            <div className="mt-2 rounded bg-destructive/10 p-2 text-destructive">
              <p className="text-xs">
                Импорт удалит {preview.deleted} строк (снос корня или большой доли). Это
                необратимо.
              </p>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                Да, применить принудительно
              </label>
            </div>
          )}
          <Button onClick={() => void apply()} disabled={applyDisabled} className="mt-3">
            Применить
          </Button>
        </div>
      )}

      {doneMsg && <p className="mt-2 text-foreground">{doneMsg}</p>}
      {error && <p className="mt-2 text-destructive">{error}</p>}
    </div>
  )
}
```

- [ ] **Step 4: Подключить TemplateUpload в ArticlesPage**

В [frontend/src/pages/ArticlesPage.tsx](../../../frontend/src/pages/ArticlesPage.tsx) импортировать `import { TemplateUpload } from "@/components/articles/TemplateUpload"` и заменить заглушку секции «Загрузить шаблон» (из Task 6, текст «Доступно в следующих задачах…») на:

```tsx
          <TemplateUpload onApplied={() => void reload()} />
```

(Заголовок «Загрузить шаблон» оставить — тесты Task 6 на него опираются.)

- [ ] **Step 5: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/components/articles/TemplateUpload.test.tsx src/pages/ArticlesPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/articles/TemplateUpload.tsx frontend/src/components/articles/TemplateUpload.test.tsx frontend/src/pages/ArticlesPage.tsx
git commit -m "feat(web): загрузка шаблона — превью (dry_run) → согласие на force → применение"
```

---

### Task 9: Frontend — полная очистка справочника (admin, подтверждение вводом)

**Files:**
- Create: `frontend/src/components/articles/WipeCatalog.tsx`
- Modify: `frontend/src/pages/ArticlesPage.tsx` (подключить для admin)
- Test: `frontend/src/components/articles/WipeCatalog.test.tsx`

**Interfaces:**
- Consumes: `deleteAllArticles` (Task 3), `ApiError`.
- Produces: `WipeCatalog({ onWiped }: { onWiped: () => void })` — кнопка «Очистить» активна ТОЛЬКО когда в поле введено слово `УДАЛИТЬ`; на успех показывает «Удалено N» и зовёт `onWiped`.

- [ ] **Step 1: Падающий тест очистки**

Создать `frontend/src/components/articles/WipeCatalog.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as articlesApi from "@/lib/api/articles"
import { WipeCatalog } from "./WipeCatalog"

afterEach(() => vi.restoreAllMocks())

describe("WipeCatalog", () => {
  it("кнопка активна только после ввода слова-подтверждения", async () => {
    render(<WipeCatalog onWiped={vi.fn()} />)
    const btn = screen.getByRole("button", { name: /очистить справочник/i })
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    expect(btn).toBeEnabled()
  })

  it("очищает и показывает «Удалено N»", async () => {
    const onWiped = vi.fn()
    vi.spyOn(articlesApi, "deleteAllArticles").mockResolvedValue(362)
    render(<WipeCatalog onWiped={onWiped} />)
    await userEvent.type(screen.getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    await userEvent.click(screen.getByRole("button", { name: /очистить справочник/i }))
    expect(await screen.findByText(/удалено 362/i)).toBeInTheDocument()
    expect(onWiped).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd frontend; npx vitest run src/components/articles/WipeCatalog.test.tsx`
Expected: FAIL — модуль не существует.

- [ ] **Step 3: Реализовать WipeCatalog**

Создать `frontend/src/components/articles/WipeCatalog.tsx`:

```tsx
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { deleteAllArticles } from "@/lib/api/articles"

const CONFIRM_WORD = "УДАЛИТЬ"

export function WipeCatalog({ onWiped }: { onWiped: () => void }) {
  const [word, setWord] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function wipe() {
    setBusy(true)
    setError(null)
    setMsg(null)
    try {
      const n = await deleteAllArticles()
      setMsg(`Удалено ${n}`)
      setWord("")
      onWiped()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось очистить справочник")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        Полностью удалит все статьи. Введите «{CONFIRM_WORD}», чтобы подтвердить.
      </p>
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="wipe-confirm">
          Подтверждение
        </label>
        <Input
          id="wipe-confirm"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          placeholder={CONFIRM_WORD}
          className="max-w-[160px]"
        />
        <Button
          variant="destructive"
          disabled={busy || word !== CONFIRM_WORD}
          onClick={() => void wipe()}
        >
          Очистить справочник
        </Button>
      </div>
      {msg && <p className="mt-2 text-foreground">{msg}</p>}
      {error && <p className="mt-2 text-destructive">{error}</p>}
    </div>
  )
}
```

Примечание: если у `Button` нет варианта `destructive` — использовать обычный + `className="bg-destructive text-white"`; открыть `src/components/ui/button.tsx` и взять доступный variant.

- [ ] **Step 4: Подключить WipeCatalog в ArticlesPage (admin)**

В [frontend/src/pages/ArticlesPage.tsx](../../../frontend/src/pages/ArticlesPage.tsx) импортировать `import { WipeCatalog } from "@/components/articles/WipeCatalog"` и в `isAdmin`-блоке после `ManualAddForm` добавить:

```tsx
        <div className="mt-4 border-t border-[var(--ds-hairline)] pt-4">
          <h3 className="mb-2 text-sm font-medium">Опасная зона</h3>
          <WipeCatalog onWiped={() => void reload()} />
        </div>
```

- [ ] **Step 5: Запустить — тесты зелёные**

Run: `cd frontend; npx vitest run src/components/articles/WipeCatalog.test.tsx src/pages/ArticlesPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/articles/WipeCatalog.tsx frontend/src/components/articles/WipeCatalog.test.tsx frontend/src/pages/ArticlesPage.tsx
git commit -m "feat(web): полная очистка справочника (admin, подтверждение вводом слова)"
```

---

### Task 10: Финальная интеграция — гейт качества

**Files:**
- Modify (при необходимости): любые точечные правки по результатам гейта.

**Interfaces:** —

- [ ] **Step 1: Полный фронт-гейт**

Run: `cd frontend; npm run typecheck; npm run lint; npx vitest run`
Expected: typecheck без ошибок; eslint чисто; все тесты зелёные. Чинить точечно до зелёного (без отключения правил).

- [ ] **Step 2: Полный бэк-гейт**

Run: `cd backend; uv run pytest; uv run ruff check .`
Expected: всё PASS, ruff чисто.

- [ ] **Step 3: Ручной дымовой прогон (опишите, не автоматизируйте)**

С запущенными `just dev-back` и `just dev-front`: войти реальным admin-аккаунтом (из `ADMIN_EMAIL`/`ADMIN_PASSWORD` в `backend/.env`), открыть «Справочник» → убедиться, что грузится из БД без `section_name`-шума; загрузить `temp/Шаблон.xlsx` через превью→применение; проверить, что не-админ (если есть тестовый user) видит read-only. Зафиксировать результат в отчёте задачи. Примечание: справочник в тест-БД уже наполнен (Task 9 ingestion-плана) — для чистой проверки можно «Очистить справочник» и импортировать заново.

- [ ] **Step 4: Commit (если были правки гейта)**

```bash
git add -A
git commit -m "chore(web): зелёный гейт catalog-admin-ui (typecheck/lint/tests)"
```

---

## Заметки по реализации

- **Не трогать** `pages/estimate/**`, `lib/mock/api.ts`, `lib/mock/fixtures.ts` (estimate-моки живут дальше), `Candidate` в `types.ts`, `components/ui/**` (вендорные).
- Каждая фронт-задача: TDD-цикл, мок API-модулей через `vi.spyOn`/`vi.mock`, без реальной сети.
- Команды фронта — из `frontend/`; для одиночного файла `npx vitest run <path>`, весь прогон `npx vitest run`.
- Бэкенд — `uv run` из `backend/`; ORM/миграции не меняются (новый роут использует существующую модель).
