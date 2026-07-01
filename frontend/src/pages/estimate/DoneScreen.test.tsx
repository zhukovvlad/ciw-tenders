import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DoneScreen } from "@/pages/estimate/DoneScreen"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"
import { setReference } from "@/lib/api/estimates"

vi.mock("@/lib/api/estimates", () => ({
  setReference: vi.fn().mockResolvedValue(undefined),
}))

describe("DoneScreen", () => {
  it("кнопки выгрузки и новой сметы работают", async () => {
    const onExport = vi.fn(),
      onNew = vi.fn()
    render(
      <DoneScreen
        state={initReview("смета.xlsx", MOCK_ROWS)}
        onExport={onExport}
        onNewEstimate={onNew}
        estimateId={1}
      />
    )
    await userEvent.click(screen.getByRole("button", { name: /Скачать/ }))
    expect(onExport).toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole("button", { name: /следующую смету/ })
    )
    expect(onNew).toHaveBeenCalled()
  })

  it("тумблер «в фонд» вызывает setReference(id, true)", async () => {
    render(
      <DoneScreen
        state={initReview("смета.xlsx", MOCK_ROWS)}
        onExport={vi.fn()}
        onNewEstimate={vi.fn()}
        estimateId={1}
      />
    )
    await userEvent.click(screen.getByRole("switch"))
    expect(setReference).toHaveBeenCalledWith(1, true)
  })
})
