// frontend/src/pages/estimate/ReviewScreen.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReducer } from "react"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { initReview, reviewReducer } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

function Wrap({ onExport = vi.fn() }: { onExport?: () => void }) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("смета.xlsx", MOCK_ROWS)
  )
  return (
    <ReviewScreen
      state={state}
      dispatch={dispatch}
      onExport={onExport}
      onNewEstimate={vi.fn()}
    />
  )
}

describe("клавиатура не затрагивает строку, скрытую фильтром", () => {
  it("keyboard не атакует needs_review строку, скрытую фильтром «Без пары»", async () => {
    render(<Wrap />)
    // На фильтре «Все» в auto-режиме activeRow = row_number первой pending-строки (строка 3).
    // Кликаем по ВТОРОЙ строке «Требует проверки» (строка 4), чтобы явно выставить
    // activeRowOverride = 4, а не "auto". Теперь при смене фильтра override сохранится.
    const needsReviewStatuses = screen.getAllByText("Требует проверки")
    // Нас интересует вторая строка (индекс 1 — строка 4 «Устройство гидроизоляции»)
    await userEvent.click(needsReviewStatuses[1])
    // Убеждаемся, что строка раскрылась (кандидаты видны)
    // Переключаемся на фильтр «Без пары» — очередь становится только [no_match].
    // Баг (state.rows.find): activeRow=4 всё ещё находит needs_review строку → Enter её подтверждает.
    // Исправление (queue.find): 4 не входит в queue → active=undefined → клавиатура отключена.
    await userEvent.click(screen.getByRole("button", { name: /Без пары/ }))
    // Нажимаем Enter — НЕ должен подтвердить скрытую needs_review строку
    await userEvent.keyboard("{Enter}")
    // Возвращаемся на «Все», чтобы проверить состояние needs_review строк
    await userEvent.click(screen.getByRole("button", { name: /Все/ }))
    // При исправлении: все 7 строк «Требует проверки» (4 needs_review + 3 no_match) нетронуты
    // При баге: строка 4 была подтверждена Enter → осталось 6 «Требует проверки»
    expect(screen.getAllByText("Требует проверки").length).toBe(7)
  })
})

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
