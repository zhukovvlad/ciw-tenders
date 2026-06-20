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
