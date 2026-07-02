// frontend/src/pages/estimate/EstimatePage.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { EstimatePage } from "@/pages/estimate/EstimatePage"
import { getEstimate, pollEstimate, setCompletion } from "@/lib/api/estimates"
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

const ROW_NEEDS_REVIEW = MOCK_ROWS.find((r) => r.status === "needs_review")!

function renderAt(id: number) {
  return render(
    <MemoryRouter initialEntries={[`/estimates/${id}`]}>
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
})
