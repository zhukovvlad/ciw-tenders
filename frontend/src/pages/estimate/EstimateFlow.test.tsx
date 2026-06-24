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
const getEstimate = vi.fn(async (_id?: number) => {
  void _id
  return { fileName: "смета.xlsx", rows: MOCK_ROWS }
})
const pollEstimate = vi.fn(async (_id?: number, _onProgress?: unknown) => {
  void _id
  void _onProgress
  return { fileName: "смета.xlsx", rows: MOCK_ROWS }
})

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

async function uploadAndReachReview() {
  const input = screen.getByLabelText(/файл сметы/i)
  await userEvent.upload(input, new File(["x"], "смета.xlsx"))
  await waitFor(
    () => expect(screen.getByText(/проверено/i)).toBeInTheDocument(),
    { timeout: 5000 }
  )
}

describe("EstimateFlow", () => {
  it("проходит путь старт → обработка → проверка", async () => {
    render(<EstimateFlow />)
    await uploadAndReachReview()
  })

  it("восстанавливает ревью из sessionStorage при монтировании", async () => {
    const { unmount } = render(<EstimateFlow />)
    await uploadAndReachReview()
    unmount()
    render(<EstimateFlow />) // новый маунт — должен сразу показать ревью
    expect(screen.getByText(/проверено/i)).toBeInTheDocument()
  })

  it("клик по кандидату коммитит решение на бэк через patchRowReview('pick')", async () => {
    render(<EstimateFlow />)
    await uploadAndReachReview()
    // Первая pending needs_review строка авто-раскрыта → её кандидаты видны.
    // Берём первую needs_review строку из снимка и кликаем её топ-кандидата.
    const firstReview = MOCK_ROWS.find((r) => r.status === "needs_review")!
    const cand = firstReview.candidates[0]
    await userEvent.click(
      screen.getByRole("button", { name: new RegExp(cand.article_code) })
    )
    await waitFor(() =>
      expect(patchRowReview).toHaveBeenCalledWith(
        1,
        firstReview.row_number,
        "pick",
        cand.id ?? undefined
      )
    )
  })

  it("выгрузка вызывает exportEstimate с id сметы", async () => {
    render(<EstimateFlow />)
    await uploadAndReachReview()
    await userEvent.click(screen.getByRole("button", { name: /Выгрузить/ }))
    await waitFor(() => expect(exportEstimate).toHaveBeenCalledWith(1))
  })

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
})
