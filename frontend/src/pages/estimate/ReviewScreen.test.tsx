// frontend/src/pages/estimate/ReviewScreen.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReducer } from "react"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { initReview, reviewReducer } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

function Wrap({ onExport = vi.fn() }: { onExport?: () => void }) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () => initReview("смета.xlsx", MOCK_ROWS))
  return <ReviewScreen state={state} dispatch={dispatch} onExport={onExport} onNewEstimate={vi.fn()} />
}

describe("ReviewScreen", () => {
  it("показывает имя файла и счётчики", () => {
    render(<Wrap />)
    expect(screen.getByText(/смета\.xlsx/)).toBeInTheDocument()
    expect(screen.getByText(/проверено/i)).toBeInTheDocument()
  })

  it("фильтр «Проверить» оставляет только спорные строки", async () => {
    render(<Wrap />)
    await userEvent.click(screen.getByRole("button", { name: /Проверить/ }))
    // confident-строка «Устройство кровли» исчезает
    expect(screen.queryByText("Устройство кровли")).not.toBeInTheDocument()
  })

  it("кнопка выгрузки вызывает onExport", async () => {
    const onExport = vi.fn()
    render(<Wrap onExport={onExport} />)
    await userEvent.click(screen.getByRole("button", { name: /Выгрузить/ }))
    expect(onExport).toHaveBeenCalled()
  })

  it("Enter подтверждает строку no_match без совпадения (confirmNoMatch)", async () => {
    render(<Wrap />)
    // Переключиться на фильтр «Без пары» — первой активной строкой станет no_match строка
    await userEvent.click(screen.getByRole("button", { name: /Без пары/ }))
    // Нажать Enter — onConfirm должен отправить confirmNoMatch, а не confirmArbiter (no-op)
    await userEvent.keyboard("{Enter}")
    // После confirmNoMatch строка переходит в статус "Нет совпадения" (decision.kind === "no_match")
    expect(screen.getAllByText("Нет совпадения").length).toBeGreaterThan(0)
  })
})
