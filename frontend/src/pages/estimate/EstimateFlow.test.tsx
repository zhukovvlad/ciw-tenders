import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { clearReview } from "@/lib/session"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

// Mock the real estimates API so tests don't hit the network
vi.mock("@/lib/api/estimates", () => ({
  uploadEstimate: async () => 1,
  pollEstimate: async () => ({ fileName: "смета.xlsx", rows: MOCK_ROWS }),
  exportEstimate: async () => new Blob(["test"]),
  getEstimate: async () => ({ fileName: "смета.xlsx", rows: MOCK_ROWS }),
  patchRowReview: async () => MOCK_ROWS[0],
  rowFromDto: (r: unknown) => r,
}))

afterEach(() => clearReview())

describe("EstimateFlow", () => {
  it("проходит путь старт → обработка → проверка", async () => {
    render(<EstimateFlow />)
    const input = screen.getByLabelText(/файл сметы/i)
    await userEvent.upload(input, new File(["x"], "смета.xlsx"))
    // после обработки появляется главный экран проверки
    await waitFor(
      () => expect(screen.getByText(/проверено/i)).toBeInTheDocument(),
      { timeout: 5000 }
    )
  })

  it("восстанавливает ревью из sessionStorage при монтировании", async () => {
    const { unmount } = render(<EstimateFlow />)
    await userEvent.upload(
      screen.getByLabelText(/файл сметы/i),
      new File(["x"], "смета.xlsx")
    )
    await waitFor(
      () => expect(screen.getByText(/проверено/i)).toBeInTheDocument(),
      { timeout: 5000 }
    )
    unmount()
    render(<EstimateFlow />) // новый маунт — должен сразу показать ревью
    expect(screen.getByText(/проверено/i)).toBeInTheDocument()
  })
})
