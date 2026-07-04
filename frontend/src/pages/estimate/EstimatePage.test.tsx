// frontend/src/pages/estimate/EstimatePage.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { EstimatePage } from "@/pages/estimate/EstimatePage"
import {
  getEstimate,
  patchRowReview,
  pollEstimate,
  setCompletion,
} from "@/lib/api/estimates"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

vi.mock("@/lib/api/estimates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/estimates")>(
    "@/lib/api/estimates"
  )
  return {
    ...actual,
    getEstimate: vi.fn(),
    pollEstimate: vi.fn(),
    setCompletion: vi.fn(),
    patchRowReview: vi.fn(),
    exportEstimate: vi.fn(),
  }
})

vi.mock("@/lib/api/articles", () => ({
  searchArticles: vi.fn().mockResolvedValue([]),
}))

vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn() } }))
import { toast } from "sonner"

const ROW_NEEDS_REVIEW = MOCK_ROWS.find((r) => r.status === "needs_review")!

function renderAt(id: number) {
  return renderAtUrl(`/estimates/${id}`)
}

function renderAtUrl(url: string) {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/estimates/:id" element={<EstimatePage />} />
        <Route path="/estimates" element={<div>list-page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

const READY = {
  id: 5,
  fileName: "a.xlsx",
  status: "ready",
  statusDetail: null,
  completedAt: null,
  isReference: false,
  rows: [ROW_NEEDS_REVIEW],
  anomalies: [],
  outlineOverrides: 0,
}

const DUP_ANOMALY = {
  kind: "duplicate_code",
  sourceIndex: 2,
  code: "1.1",
  name: "B",
  detail: "код встречается 2 раза",
}

describe("EstimatePage", () => {
  it("ready без completedAt → экран ревью", async () => {
    vi.mocked(getEstimate).mockResolvedValue(READY)
    renderAt(5)
    expect(await screen.findByText(/Выгрузить Excel/)).toBeInTheDocument()
  })

  it("ready с completedAt → итоговый экран", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      completedAt: "2026-07-02T12:00:00Z",
    })
    renderAt(5)
    expect(await screen.findByText(/Возобновить проверку/)).toBeInTheDocument()
  })

  it("blocked → сообщение об отказе и ссылка к списку", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      status: "blocked",
      statusDetail: "нет строк СМР",
      rows: [],
    })
    renderAt(5)
    expect(await screen.findByRole("alert")).toHaveTextContent("нет строк СМР")
  })

  it("«Завершить» дергает setCompletion и показывает итог", async () => {
    vi.mocked(getEstimate).mockResolvedValue(READY)
    vi.mocked(setCompletion).mockResolvedValue({
      completedAt: "2026-07-02T12:00:00Z",
    })
    renderAt(5)
    // имя точное, не regex: после открытия диалога /Завершить/ матчил бы две кнопки
    await userEvent.click(
      await screen.findByRole("button", { name: "Завершить" })
    )
    // строка нерешённая → AlertDialog «осталось N спорных»
    await userEvent.click(
      screen.getByRole("button", { name: "Завершить всё равно" })
    )
    expect(await screen.findByText(/Возобновить проверку/)).toBeInTheDocument()
    expect(setCompletion).toHaveBeenCalledWith(5, true)
  })

  it("blocked во время поллинга → алерт с деталью, а не generic-ошибка", async () => {
    vi.mocked(getEstimate)
      .mockResolvedValueOnce({ ...READY, status: "pending", rows: [] })
      .mockResolvedValueOnce({
        ...READY,
        status: "blocked",
        statusDetail: "нет строк СМР",
        rows: [],
      })
    vi.mocked(pollEstimate).mockRejectedValue(
      new Error("Обработка сметы заблокирована")
    )
    renderAt(5)
    expect(await screen.findByRole("alert")).toHaveTextContent("нет строк СМР")
  })

  it("размонтирование во время поллинга отменяет AbortSignal, переданный в pollEstimate", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      status: "pending",
      rows: [],
    })
    let capturedSignal: AbortSignal | undefined
    vi.mocked(pollEstimate).mockImplementation(
      (_id, _onProgress, _intervalMs, opts) => {
        capturedSignal = opts?.signal
        return new Promise(() => {}) // никогда не резолвится — как незавершённый поллинг
      }
    )
    const { unmount } = renderAt(5)
    await waitFor(() => expect(pollEstimate).toHaveBeenCalled())
    expect(capturedSignal?.aborted).toBe(false)
    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })

  it("completed + ?view=grid → read-only грид; без view — DoneScreen", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      completedAt: "2026-07-02T12:00:00Z",
      rows: MOCK_ROWS,
    })
    const gridRender = renderAtUrl("/estimates/5?view=grid")
    expect(await screen.findByRole("table")).toBeInTheDocument()
    gridRender.unmount()

    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      completedAt: "2026-07-02T12:00:00Z",
      rows: MOCK_ROWS,
    })
    renderAtUrl("/estimates/5")
    expect(await screen.findByText(/Скачать обогащённый/)).toBeInTheDocument()
    const link = screen.getByRole("link", { name: /Просмотреть строки/ })
    expect(link).toHaveAttribute("href", expect.stringContaining("view=grid"))
  })

  it("processing + ?view=grid молча игнорируется (ProcessingScreen)", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      status: "pending",
      rows: [],
    })
    vi.mocked(pollEstimate).mockImplementation(() => new Promise(() => {}))
    renderAtUrl("/estimates/5?view=grid")
    expect(await screen.findByText(/Отбор строк СМР/)).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("ошибка PATCH: toast с именем строки и reopen", async () => {
    vi.mocked(getEstimate).mockResolvedValue(READY)
    vi.mocked(patchRowReview).mockRejectedValue(new Error("boom"))
    renderAt(5)
    await screen.findByText(/Выгрузить Excel/)
    // строка «needs_review» с рекомендацией активна автоматически (очередь) —
    // Enter коммитит confirmArbiter, PATCH падает
    await userEvent.keyboard("{Enter}")
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining(ROW_NEEDS_REVIEW.source_name)
      )
    )
    // reopen вернул решение в pending — карточка той же строки осталась
    // активной (единственная спорная строка), а не терминальный экран.
    // Полоса контекста (Task 1, спека 3.5) смонтирована внутри карточки и
    // дублирует source_name активной строки — строки полосы несут data-row
    // (см. ContextStrip.tsx), по нему отличаем текст работы карточки.
    const workText = within(screen.getByTestId("review-card"))
      .getAllByText(ROW_NEEDS_REVIEW.source_name)
      .find((el) => !el.closest("[data-row]"))
    expect(workText).toBeInTheDocument()
  })

  it("аномалии из GET показываются на экране ревью (прямой заход/F5)", async () => {
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      anomalies: [DUP_ANOMALY],
    })
    renderAt(5)
    expect(
      await screen.findByText(/структура сметы.*1 замечание/i)
    ).toBeInTheDocument()
  })

  it("upload → processing → ready: notice виден после полла (спека §7)", async () => {
    // парсинг синхронен в POST — аномалии уже в первичном GET при status=pending
    vi.mocked(getEstimate).mockResolvedValue({
      ...READY,
      status: "pending",
      rows: [],
      anomalies: [DUP_ANOMALY],
    })
    vi.mocked(pollEstimate).mockResolvedValue({
      fileName: "a.xlsx",
      rows: [ROW_NEEDS_REVIEW],
    })
    renderAt(5)
    expect(
      await screen.findByText(/структура сметы.*1 замечание/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/Выгрузить Excel/)).toBeInTheDocument()
  })
})
