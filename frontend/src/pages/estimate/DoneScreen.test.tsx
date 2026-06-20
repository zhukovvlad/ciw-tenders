import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DoneScreen } from "@/pages/estimate/DoneScreen"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

describe("DoneScreen", () => {
  it("кнопки выгрузки и новой сметы работают", async () => {
    const onExport = vi.fn(), onNew = vi.fn()
    render(<DoneScreen state={initReview("смета.xlsx", MOCK_ROWS)} onExport={onExport} onNewEstimate={onNew} />)
    await userEvent.click(screen.getByRole("button", { name: /Скачать/ }))
    expect(onExport).toHaveBeenCalled()
    await userEvent.click(screen.getByRole("button", { name: /следующую смету/ }))
    expect(onNew).toHaveBeenCalled()
  })
})
