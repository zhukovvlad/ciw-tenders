# Список разобранных смет на фронтенде — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вывести список разобранных смет на стартовом экране — с открытием конкретной сметы (по статусу) и удалением с подтверждением.

**Architecture:** Добавляем `listEstimates`/`deleteEstimate` в существующий API-слой (`lib/api/estimates.ts`), новый самодостаточный компонент `EstimateList` (сам грузит данные, рисует таблицу со статус-бейджами и удалением), монтируем его в `StartScreen` под дропзоной. `EstimateFlow` получает `handleOpen(item)`, который по статусу ведёт в `review` (готовые) или возобновляет poll в `processing` (ещё считаются).

**Tech Stack:** React + TypeScript, Vite, Tailwind v4, shadcn/ui (table, badge, alert-dialog, skeleton, button), sonner (toast), vitest + React Testing Library.

## Global Constraints

- TypeScript strict; проверка типов — `npm run typecheck` (= `tsc -b`).
- ESLint строгий + Prettier (`printWidth 80`, `endOfLine lf`). Импорты через alias `@/`. Иконки — `lucide-react`.
- shadcn-компоненты в `src/components/ui/` — вендорные, не править.
- Токен/авторизация — только через `lib/api/client.ts` (`apiGet`/`apiSend`). Сетевые ошибки прилетают как `ApiError`.
- Поток смет на моках (`lib/mock/`) и `Candidate`/`MOCK_*` — не трогать.
- Команды фронта запускать из `frontend/`: `cd frontend && npm run test`, `npm run typecheck`, `npm run lint`.
- Файлы держать в LF.

---

### Task 1: API — `listEstimates` и `deleteEstimate`

**Files:**
- Modify: `frontend/src/lib/api/estimates.ts` (добавить тип и две функции в конец файла)
- Test: `frontend/src/lib/api/estimates.test.ts` (добавить describe-блок)

**Interfaces:**
- Consumes: `apiGet`, `apiSend` из `./client` (уже импортированы в `estimates.ts`).
- Produces:
  - `export interface EstimateListItem { id: number; filename: string; status: string; nodesCount: number; createdAt: string }`
  - `export async function listEstimates(): Promise<EstimateListItem[]>`
  - `export async function deleteEstimate(id: number): Promise<void>`

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `frontend/src/lib/api/estimates.test.ts`. Обновить импорты вверху файла — сейчас там только `import { rowFromDto } from "@/lib/api/estimates"`; заменить на:

```ts
import { vi } from "vitest"
import * as client from "@/lib/api/client"
import {
  deleteEstimate,
  listEstimates,
  rowFromDto,
} from "@/lib/api/estimates"
```

(строка `import { describe, expect, it } from "vitest"` остаётся; `vi` можно добавить в неё вместо отдельной строки — на усмотрение, лишь бы проходил линт.)

Добавить новый блок:

```ts
describe("estimates api list/delete", () => {
  it("listEstimates маппит snake_case DTO в camelCase", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      {
        id: 1,
        filename: "a.xlsx",
        status: "ready",
        nodes_count: 12,
        created_at: "2026-06-24T10:00:00Z",
      },
    ])
    const items = await listEstimates()
    expect(items).toEqual([
      {
        id: 1,
        filename: "a.xlsx",
        status: "ready",
        nodesCount: 12,
        createdAt: "2026-06-24T10:00:00Z",
      },
    ])
  })

  it("listEstimates ходит на GET /estimates", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue([])
    await listEstimates()
    expect(spy).toHaveBeenCalledWith("/estimates")
  })

  it("deleteEstimate шлёт DELETE по id", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await deleteEstimate(7)
    expect(spy).toHaveBeenCalledWith("DELETE", "/estimates/7")
  })
})
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `cd frontend && npm run test -- src/lib/api/estimates.test.ts`
Expected: FAIL — `listEstimates`/`deleteEstimate` не экспортируются (`No "listEstimates" export is defined`).

- [ ] **Step 3: Реализовать функции**

Добавить в конец `frontend/src/lib/api/estimates.ts`:

```ts
interface SummaryDto {
  id: number
  filename: string
  status: string
  nodes_count: number
  created_at: string // ISO
}

export interface EstimateListItem {
  id: number
  filename: string
  status: string
  nodesCount: number
  createdAt: string // ISO — форматируется в UI
}

export async function listEstimates(): Promise<EstimateListItem[]> {
  const dtos = await apiGet<SummaryDto[]>("/estimates")
  return dtos.map((d) => ({
    id: d.id,
    filename: d.filename,
    status: d.status,
    nodesCount: d.nodes_count,
    createdAt: d.created_at,
  }))
}

export async function deleteEstimate(id: number): Promise<void> {
  await apiSend("DELETE", `/estimates/${id}`)
}
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd frontend && npm run test -- src/lib/api/estimates.test.ts`
Expected: PASS (все тесты, включая существующий `rowFromDto`).

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/lib/api/estimates.ts frontend/src/lib/api/estimates.test.ts
git commit -m "feat(estimates): API listEstimates + deleteEstimate"
```

---

### Task 2: Компонент `EstimateList`

**Files:**
- Create: `frontend/src/components/estimate/EstimateList.tsx`
- Test: `frontend/src/components/estimate/EstimateList.test.tsx`

**Interfaces:**
- Consumes: `listEstimates`, `deleteEstimate`, `EstimateListItem` (Task 1); `ApiError` из `@/lib/api/client`; shadcn `table`/`badge`/`alert-dialog`/`button`/`skeleton`; `toast` из `sonner`.
- Produces:
  - `export interface EstimateListProps { onOpen: (item: EstimateListItem) => void }`
  - `export function EstimateList(props: EstimateListProps): JSX.Element`
  - `export const STATUS_META: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive"; clickable: boolean }>` — карта статус→бейдж (тестируется и переиспользуется).

Поведение статусов (`STATUS_META`):

| Статус | label | variant | clickable |
|---|---|---|---|
| `ready` | «Готово» | default | true |
| `partial_error` | «Готово с ошибками» | outline | true |
| `pending` | «В обработке» | secondary | true |
| `running` | «В обработке» | secondary | true |
| `blocked` | «Отклонено» | destructive | false |

Неизвестный статус → fallback `{ label: статус, variant: "secondary", clickable: false }`.

- [ ] **Step 1: Написать падающие тесты**

Создать `frontend/src/components/estimate/EstimateList.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import * as estimatesApi from "@/lib/api/estimates"
import { ApiError } from "@/lib/api/client"
import { EstimateList } from "./EstimateList"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(() => vi.restoreAllMocks())

const ITEMS: estimatesApi.EstimateListItem[] = [
  {
    id: 1,
    filename: "ready.xlsx",
    status: "ready",
    nodesCount: 10,
    createdAt: "2026-06-24T10:00:00Z",
  },
  {
    id: 2,
    filename: "blocked.xlsx",
    status: "blocked",
    nodesCount: 0,
    createdAt: "2026-06-24T11:00:00Z",
  },
]

describe("EstimateList", () => {
  it("показывает пустое состояние, когда смет нет", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue([])
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText(/пока нет разобранных смет/i)).toBeInTheDocument()
  })

  it("рисует строки и бейджи статусов", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText("ready.xlsx")).toBeInTheDocument()
    expect(screen.getByText("Готово")).toBeInTheDocument()
    expect(screen.getByText("Отклонено")).toBeInTheDocument()
  })

  it("клик по готовой смете зовёт onOpen с item", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    const onOpen = vi.fn()
    render(<EstimateList onOpen={onOpen} />)
    await userEvent.click(await screen.findByText("ready.xlsx"))
    expect(onOpen).toHaveBeenCalledWith(ITEMS[0])
  })

  it("blocked-смета не кликабельна (onOpen не зовётся)", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    const onOpen = vi.fn()
    render(<EstimateList onOpen={onOpen} />)
    await userEvent.click(await screen.findByText("blocked.xlsx"))
    expect(onOpen).not.toHaveBeenCalled()
  })

  it("удаление через диалог зовёт deleteEstimate и рефетчит список", async () => {
    const listSpy = vi
      .spyOn(estimatesApi, "listEstimates")
      .mockResolvedValueOnce(ITEMS)
      .mockResolvedValueOnce([ITEMS[1]])
    const delSpy = vi
      .spyOn(estimatesApi, "deleteEstimate")
      .mockResolvedValue(undefined)
    render(<EstimateList onOpen={vi.fn()} />)
    await screen.findByText("ready.xlsx")
    // у строки с id=1 жмём кнопку удаления (aria-label содержит имя файла)
    await userEvent.click(
      screen.getByRole("button", { name: /удалить ready\.xlsx/i })
    )
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /^удалить$/i })
    )
    await vi.waitFor(() => expect(delSpy).toHaveBeenCalledWith(1))
    expect(listSpy).toHaveBeenCalledTimes(2)
  })

  it("на ошибке загрузки показывает сообщение", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockRejectedValue(
      new ApiError(500, "сбой загрузки")
    )
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText(/не удалось загрузить/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `cd frontend && npm run test -- src/components/estimate/EstimateList.test.tsx`
Expected: FAIL — модуль `./EstimateList` не найден / нет экспорта `EstimateList`.

- [ ] **Step 3: Реализовать компонент**

Создать `frontend/src/components/estimate/EstimateList.tsx`:

```tsx
import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
import { toast } from "sonner"
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
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiError } from "@/lib/api/client"
import {
  deleteEstimate,
  listEstimates,
  type EstimateListItem,
} from "@/lib/api/estimates"

export interface EstimateListProps {
  onOpen: (item: EstimateListItem) => void
}

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

export const STATUS_META: Record<
  string,
  { label: string; variant: BadgeVariant; clickable: boolean }
> = {
  ready: { label: "Готово", variant: "default", clickable: true },
  partial_error: {
    label: "Готово с ошибками",
    variant: "outline",
    clickable: true,
  },
  pending: { label: "В обработке", variant: "secondary", clickable: true },
  running: { label: "В обработке", variant: "secondary", clickable: true },
  blocked: { label: "Отклонено", variant: "destructive", clickable: false },
}

function metaFor(status: string) {
  return (
    STATUS_META[status] ?? {
      label: status,
      variant: "secondary" as BadgeVariant,
      clickable: false,
    }
  )
}

const dateFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateFmt.format(d)
}

export function EstimateList({ onOpen }: EstimateListProps) {
  const [items, setItems] = useState<EstimateListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setItems(await listEstimates())
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Не удалось загрузить сметы"
      )
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function remove(id: number) {
    try {
      await deleteEstimate(id)
      toast.success("Смета удалена")
      await load()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось удалить смету"
      )
    }
  }

  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {error}
      </p>
    )
  }

  if (items === null) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Пока нет разобранных смет — загрузите файл выше.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Файл</TableHead>
          <TableHead>Статус</TableHead>
          <TableHead className="text-right">Узлов</TableHead>
          <TableHead>Дата</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => {
          const meta = metaFor(item.status)
          return (
            <TableRow key={item.id}>
              <TableCell>
                {meta.clickable ? (
                  <button
                    type="button"
                    className="text-left font-medium hover:underline"
                    onClick={() => onOpen(item)}
                  >
                    {item.filename}
                  </button>
                ) : (
                  <span className="font-medium text-muted-foreground">
                    {item.filename}
                  </span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={meta.variant}>{meta.label}</Badge>
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {item.nodesCount}
              </TableCell>
              <TableCell className="text-muted-foreground">
                {formatDate(item.createdAt)}
              </TableCell>
              <TableCell>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <button
                      type="button"
                      aria-label={`Удалить ${item.filename}`}
                      className="rounded-sm p-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <Trash2 className="size-4 text-destructive" />
                    </button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Удалить смету?</AlertDialogTitle>
                      <AlertDialogDescription>
                        «{item.filename}» будет удалена безвозвратно.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Отмена</AlertDialogCancel>
                      <AlertDialogAction onClick={() => void remove(item.id)}>
                        Удалить
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd frontend && npm run test -- src/components/estimate/EstimateList.test.tsx`
Expected: PASS (все 6 тестов).

- [ ] **Step 5: Проверить типы и линт**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: без ошибок.

- [ ] **Step 6: Коммит**

```bash
git add frontend/src/components/estimate/EstimateList.tsx frontend/src/components/estimate/EstimateList.test.tsx
git commit -m "feat(estimates): компонент EstimateList со статус-бейджами и удалением"
```

---

### Task 3: Подключить список в `StartScreen` и `EstimateFlow`

**Files:**
- Modify: `frontend/src/pages/estimate/StartScreen.tsx`
- Modify: `frontend/src/pages/estimate/EstimateFlow.tsx`
- Test: `frontend/src/pages/estimate/EstimateFlow.test.tsx` (добавить тесты открытия)

**Interfaces:**
- Consumes: `EstimateList` + `EstimateListItem` (Task 2); `getEstimate`, `pollEstimate` (существуют в `estimates.ts`).
- Produces:
  - `StartScreen` получает проп `onOpen: (item: EstimateListItem) => void` и рендерит `<EstimateList onOpen={onOpen} />`.
  - `EstimateFlow` получает приватный `handleOpen(item: EstimateListItem)`.

- [ ] **Step 1: Обновить мок `@/lib/api/estimates` и добавить тесты открытия**

ВАЖНО: текущий `EstimateFlow.test.tsx` мокает `@/lib/api/estimates` целиком (`vi.mock(... () => ({ ... }))`) и НЕ отдаёт `listEstimates`/`deleteEstimate`. Как только `StartScreen` начнёт монтировать `EstimateList` (Task 3 Step 3-4), `listEstimates()` будет `undefined` — тесты упадут. Поэтому мок надо расширить и сделать функции управляемыми из тестов (по образцу `patchRowReview`/`exportEstimate`, которые уже вынесены в `vi.fn()` и вызываются лениво внутри фабрики, чтобы не словить TDZ при хойстинге `vi.mock`).

Заменить верхнюю часть файла (строки 1-58, от импортов до конца `beforeEach`/`afterEach`) на:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { MatchRow } from "@/lib/types"
import type { EstimateListItem } from "@/lib/api/estimates"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { clearReview } from "@/lib/session"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

const patchRowReview = vi.fn()
const exportEstimate = vi.fn((id: number) => {
  void id
  return Promise.resolve(new Blob(["test"]))
})
const listEstimates = vi.fn(async (): Promise<EstimateListItem[]> => [])
const deleteEstimate = vi.fn(async (id: number) => {
  void id
})
const getEstimate = vi.fn(async () => ({
  fileName: "смета.xlsx",
  rows: MOCK_ROWS,
}))
const pollEstimate = vi.fn(async () => ({
  fileName: "смета.xlsx",
  rows: MOCK_ROWS,
}))

// Mock the real estimates API so tests don't hit the network. Функции
// вызываются лениво (через arrow) — иначе хойст vi.mock поймает TDZ const-ов.
vi.mock("@/lib/api/estimates", () => ({
  uploadEstimate: async () => 1,
  pollEstimate: (id: number, onProgress: unknown) => pollEstimate(id, onProgress),
  exportEstimate: (id: number) => exportEstimate(id),
  getEstimate: (id: number) => getEstimate(id),
  listEstimates: () => listEstimates(),
  deleteEstimate: (id: number) => deleteEstimate(id),
  patchRowReview: (
    estimateId: number,
    rowId: number,
    action: string,
    articleId?: number
  ) => patchRowReview(estimateId, rowId, action, articleId),
  rowFromDto: (r: unknown) => r,
}))

beforeEach(() => {
  // jsdom не реализует object URL API — заглушаем для пути экспорта
  URL.createObjectURL = vi.fn(() => "blob:mock")
  URL.revokeObjectURL = vi.fn()
  patchRowReview.mockReset()
  exportEstimate.mockClear()
  listEstimates.mockReset().mockResolvedValue([])
  deleteEstimate.mockReset().mockResolvedValue(undefined)
  getEstimate
    .mockReset()
    .mockResolvedValue({ fileName: "смета.xlsx", rows: MOCK_ROWS })
  pollEstimate
    .mockReset()
    .mockResolvedValue({ fileName: "смета.xlsx", rows: MOCK_ROWS })
  // Default: echo back the row as confirmed/overridden so syncRow has a valid row
  patchRowReview.mockImplementation(
    async (...args: [number, number, string, number?]): Promise<MatchRow> => {
      const [, rowId, action] = args
      const base = MOCK_ROWS.find((r) => r.row_number === rowId)!
      const review_status =
        action === "reject"
          ? "rejected"
          : action === "pick"
            ? "overridden"
            : "confirmed"
      return {
        ...base,
        review_status,
        final_article_id: base.matched_article_id,
        final_code: base.matched_code,
        final_name: base.matched_name,
      }
    }
  )
})

afterEach(() => clearReview())
```

Затем добавить два теста внутри `describe("EstimateFlow", ...)` (рядом с существующими):

```tsx
  it("открывает готовую смету из списка → экран проверки", async () => {
    listEstimates.mockResolvedValue([
      {
        id: 7,
        filename: "old.xlsx",
        status: "ready",
        nodesCount: 3,
        createdAt: "2026-06-24T10:00:00Z",
      },
    ])
    render(<EstimateFlow />)
    await userEvent.click(await screen.findByText("old.xlsx"))
    await waitFor(() =>
      expect(screen.getByText(/проверено/i)).toBeInTheDocument()
    )
    expect(getEstimate).toHaveBeenCalledWith(7)
  })

  it("открывает считающуюся смету через poll, не через getEstimate", async () => {
    listEstimates.mockResolvedValue([
      {
        id: 9,
        filename: "calc.xlsx",
        status: "running",
        nodesCount: 5,
        createdAt: "2026-06-24T10:00:00Z",
      },
    ])
    render(<EstimateFlow />)
    await userEvent.click(await screen.findByText("calc.xlsx"))
    await waitFor(() =>
      expect(pollEstimate).toHaveBeenCalledWith(9, expect.any(Function))
    )
    expect(getEstimate).not.toHaveBeenCalled()
  })
```

- [ ] **Step 2: Запустить тесты — убедиться, что новые падают**

Run: `cd frontend && npm run test -- src/pages/estimate/EstimateFlow.test.tsx`
Expected: FAIL — два новых теста падают: на старте список не рендерит «old.xlsx»/«calc.xlsx» (нет `onOpen`/`EstimateList`). Существующие 4 теста должны остаться зелёными (мок уже расширен).

- [ ] **Step 3: Прокинуть `onOpen` в `StartScreen`**

Заменить `frontend/src/pages/estimate/StartScreen.tsx` целиком:

```tsx
import { Dropzone } from "@/components/Dropzone"
import { EstimateList } from "@/components/estimate/EstimateList"
import type { EstimateListItem } from "@/lib/api/estimates"

interface StartScreenProps {
  onFile: (file: File) => void
  onOpen: (item: EstimateListItem) => void
}

export function StartScreen({ onFile, onOpen }: StartScreenProps) {
  return (
    <div className="space-y-8 p-8">
      <Dropzone
        onFile={onFile}
        accept=".xlsx,.xls"
        id="estimate-file"
        ariaLabel="файл сметы"
        idleText="Перетащите смету или выберите файл"
        hotText="Отпустите файл сметы"
        hint=".xlsx · .xls — обрабатываются строки «Вид раздела = СМР»"
        className="min-h-64"
      />
      <section className="space-y-3">
        <h2 className="text-sm font-medium text-muted-foreground">
          Разобранные сметы
        </h2>
        <EstimateList onOpen={onOpen} />
      </section>
    </div>
  )
}
```

- [ ] **Step 4: Добавить `handleOpen` в `EstimateFlow` и прокинуть в `StartScreen`**

В `frontend/src/pages/estimate/EstimateFlow.tsx`:

1. Дополнить импорт из `@/lib/api/estimates` функцией `getEstimate` (рядом с `exportEstimate`, `patchRowReview`, `pollEstimate`, `uploadEstimate`):

```ts
import {
  exportEstimate,
  getEstimate,
  patchRowReview,
  pollEstimate,
  uploadEstimate,
} from "@/lib/api/estimates"
```

2. Добавить импорт типа элемента списка (отдельной строкой `import type`):

```ts
import type { EstimateListItem } from "@/lib/api/estimates"
```

3. Добавить метод `handleOpen` рядом с `handleFile` (внутри компонента `EstimateFlow`):

```ts
  // Открыть ранее разобранную смету из списка. Готовые (ready/partial_error) —
  // сразу в review; ещё считающиеся (pending/running) — в processing с
  // возобновлением poll. blocked сюда не приходит (некликабелен в списке).
  async function handleOpen(item: EstimateListItem) {
    estimateIdRef.current = item.id
    saveEstimateId(item.id)
    setFileName(item.filename)

    if (item.status === "pending" || item.status === "running") {
      setPhase("processing")
      setProg({ phase: "parsing", done: 0, total: 0, etaSeconds: null })
      try {
        const { fileName: serverFileName, rows } = await pollEstimate(
          item.id,
          (status, done, total) => {
            const mappedPhase: Progress["phase"] =
              status === "running" ? "matching" : "parsing"
            setProg({ phase: mappedPhase, done, total, etaSeconds: null })
          }
        )
        const fresh = initReview(serverFileName || item.filename, rows)
        dispatch({ type: "load", state: fresh })
        saveReview(fresh)
        setPhase("review")
      } catch (err) {
        console.error(err)
        toast.error(
          err instanceof Error ? err.message : "Не удалось обработать смету"
        )
        setPhase("start")
      }
      return
    }

    try {
      const { fileName: serverFileName, rows } = await getEstimate(item.id)
      const fresh = initReview(serverFileName || item.filename, rows)
      dispatch({ type: "load", state: fresh })
      saveReview(fresh)
      setPhase("review")
    } catch (err) {
      console.error(err)
      toast.error(
        err instanceof Error ? err.message : "Не удалось открыть смету"
      )
      setPhase("start")
    }
  }
```

4. Прокинуть `onOpen` в `StartScreen` (строка рендера фазы `start`):

Заменить
```tsx
  if (phase === "start") return <StartScreen onFile={handleFile} />
```
на
```tsx
  if (phase === "start")
    return <StartScreen onFile={handleFile} onOpen={handleOpen} />
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `cd frontend && npm run test -- src/pages/estimate/EstimateFlow.test.tsx`
Expected: PASS (новые тесты A/B + существующие).

- [ ] **Step 6: Прогнать весь фронт-набор, типы и линт**

Run: `cd frontend && npm run test && npm run typecheck && npm run lint`
Expected: всё зелёное.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/pages/estimate/StartScreen.tsx frontend/src/pages/estimate/EstimateFlow.tsx frontend/src/pages/estimate/EstimateFlow.test.tsx
git commit -m "feat(estimates): список смет на StartScreen + открытие по статусу"
```

---

## Заметки по ручной проверке (после Task 3)

- `just dev-back` + `just dev-front`, залогиниться, открыть вкладку «Смета».
- Под дропзоной — список разобранных смет: готовые открываются в проверку,
  «В обработке» уводят в экран обработки (poll), «Отклонено» некликабельна.
- Удаление из списка спрашивает подтверждение и убирает строку.
- Открытая из списка смета поддерживает PATCH-ревью строк и экспорт
  (`estimateIdRef`/`saveEstimateId` выставлены).
