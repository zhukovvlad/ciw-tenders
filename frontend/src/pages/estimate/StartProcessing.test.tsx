import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"

describe("StartScreen", () => {
  it("выбор файла вызывает onFile", async () => {
    const onFile = vi.fn()
    render(<StartScreen onFile={onFile} />)
    const input = screen.getByLabelText(/файл сметы/i) as HTMLInputElement
    await userEvent.upload(input, new File(["x"], "смета.xlsx"))
    expect(onFile).toHaveBeenCalled()
  })
})

describe("ProcessingScreen", () => {
  it("на фазе embedding ETA-число не показывается", () => {
    render(
      <ProcessingScreen
        fileName="смета.xlsx"
        progress={{ phase: "embedding", done: 10, total: 15, etaSeconds: null }}
      />
    )
    expect(screen.queryByText(/сек/i)).not.toBeInTheDocument()
  })
  it("на фазе matching показывается ETA-число", () => {
    render(
      <ProcessingScreen
        fileName="смета.xlsx"
        progress={{ phase: "matching", done: 5, total: 15, etaSeconds: 8 }}
      />
    )
    expect(screen.getByText(/сек/i)).toBeInTheDocument()
  })
})
