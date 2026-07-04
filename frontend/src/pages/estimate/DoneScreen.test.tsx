import { describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { DoneScreen } from "@/pages/estimate/DoneScreen"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"
import { setReference } from "@/lib/api/estimates"

vi.mock("@/lib/api/estimates", () => ({
  setReference: vi.fn().mockResolvedValue({ is_reference: true, promoted: 1 }),
}))
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn() } }))
import { toast } from "sonner"

// хотя бы одна строка с решением оператора — иначе тумблер фонда disabled
// (promotableCount === 0) и тесты кликов по нему бессмысленны
const ROWS_WITH_DECISION = MOCK_ROWS.map((r, i) =>
  i === 0
    ? {
        ...r,
        status: "needs_review" as const,
        review_status: "confirmed" as const,
      }
    : r
)

function renderDone(props: Partial<React.ComponentProps<typeof DoneScreen>>) {
  return render(
    <MemoryRouter>
      <DoneScreen
        state={initReview("смета.xlsx", ROWS_WITH_DECISION)}
        onExport={vi.fn()}
        onResume={vi.fn()}
        estimateId={1}
        isReference={false}
        {...props}
      />
    </MemoryRouter>
  )
}

describe("DoneScreen", () => {
  it("кнопки выгрузки и возобновления работают", async () => {
    const onExport = vi.fn(),
      onResume = vi.fn()
    renderDone({ onExport, onResume })
    await userEvent.click(screen.getByRole("button", { name: /Скачать/ }))
    expect(onExport).toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole("button", { name: /Возобновить проверку/ })
    )
    expect(onResume).toHaveBeenCalled()
  })

  it("кнопка «Просмотреть строки» ведёт в read-only грид (?view=grid)", () => {
    renderDone({})
    const link = screen.getByRole("link", { name: /Просмотреть строки/ })
    expect(link).toHaveAttribute("href", expect.stringContaining("view=grid"))
  })

  it("тумблер «в фонд» вызывает setReference(id, true)", async () => {
    renderDone({})
    await userEvent.click(screen.getByRole("switch"))
    expect(setReference).toHaveBeenCalledWith(1, true)
  })

  it("тумблер имеет aria-label для доступности", () => {
    renderDone({})
    expect(
      screen.getByRole("switch", {
        name: "Эталонная смета — добавить в фонд решений",
      })
    ).toBeInTheDocument()
  })

  it("синкает тумблер по ответу сервера: is_reference:false после toggle-ON приходит в OFF", async () => {
    vi.mocked(setReference).mockResolvedValueOnce({
      is_reference: false,
      promoted: 0,
    })
    renderDone({})
    const toggle = screen.getByRole("switch")
    await userEvent.click(toggle)
    expect(setReference).toHaveBeenCalledWith(1, true)
    await vi.waitFor(() => {
      expect(toggle).toHaveAttribute("aria-checked", "false")
    })
  })

  it("тумблер инициализируется из пропа isReference", () => {
    renderDone({ isReference: true })
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true")
  })

  it("успешный тумблер зовёт onReferenceChange с ответом бэка", async () => {
    vi.mocked(setReference).mockResolvedValueOnce({
      is_reference: true,
      promoted: 2,
    })
    const onReferenceChange = vi.fn()
    renderDone({ onReferenceChange })
    await userEvent.click(screen.getByRole("switch"))
    await vi.waitFor(() => {
      expect(onReferenceChange).toHaveBeenCalledWith(true)
    })
  })

  it("promoted=0 при включении → подсказка, почему тумблер отщёлкнулся", async () => {
    vi.mocked(setReference).mockResolvedValueOnce({
      is_reference: false,
      promoted: 0,
    })
    renderDone({})
    await userEvent.click(screen.getByRole("switch"))
    await vi.waitFor(() => {
      expect(toast.info).toHaveBeenCalled()
    })
  })

  it("гонка двойного клика: побеждает ответ на последний запрос (latest-wins)", async () => {
    let resolveFirst: (v: { is_reference: boolean; promoted: number }) => void
    const first = new Promise<{ is_reference: boolean; promoted: number }>(
      (resolve) => {
        resolveFirst = resolve
      }
    )
    vi.mocked(setReference)
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ is_reference: false, promoted: 0 })
    renderDone({})
    const toggle = screen.getByRole("switch")
    // первый клик (ON) — ответ придёт позже
    await userEvent.click(toggle)
    // второй клик (OFF) — ответ приходит раньше и должен победить
    await userEvent.click(toggle)
    await vi.waitFor(() => {
      expect(toggle).toHaveAttribute("aria-checked", "false")
    })
    // устаревший ответ первого (ON) запроса приходит последним, с ДРУГИМ is_reference —
    // не должен перезаписать актуальное состояние (OFF)
    await act(async () => {
      resolveFirst!({ is_reference: true, promoted: 1 })
      await first
    })
    expect(toggle).toHaveAttribute("aria-checked", "false")
  })

  it("тумблер disabled с пояснением, когда нет решений оператора", () => {
    renderDone({ state: initReview("смета.xlsx", MOCK_ROWS) }) // все unreviewed
    expect(screen.getByRole("switch")).toBeDisabled()
    expect(
      screen.getByText(/Фонд пополняют решения, принятые оператором/)
    ).toBeInTheDocument()
  })

  it("подтверждённые фонд-хиты не активируют тумблер (анти-накрутка)", () => {
    const rows = MOCK_ROWS.map((r, i) =>
      i === 0
        ? {
            ...r,
            status: "matched_fund" as const,
            review_status: "confirmed" as const,
          }
        : r
    )
    renderDone({ state: initReview("смета.xlsx", rows) })
    expect(screen.getByRole("switch")).toBeDisabled()
  })

  it("при наличии решения оператора тумблер активен и пояснение скрыто", () => {
    renderDone({})
    expect(screen.getByRole("switch")).toBeEnabled()
    expect(screen.queryByText(/Фонд пополняют решения/)).not.toBeInTheDocument()
  })

  it("эталонная смета с 0 промоутабельных: тумблер активен для выключения", () => {
    // оператор возобновил проверку и переиграл всё в rejected — promotable=0,
    // но смета УЖЕ в фонде (isReference=true): unreference обязана остаться
    // доступной, disabled блокирует только ВКЛЮЧЕНИЕ, не выключение
    renderDone({
      state: initReview("смета.xlsx", MOCK_ROWS), // все unreviewed → promotable=0
      isReference: true,
    })
    expect(screen.getByRole("switch")).toBeEnabled()
    expect(screen.queryByText(/Фонд пополняют решения/)).not.toBeInTheDocument()
  })
})
