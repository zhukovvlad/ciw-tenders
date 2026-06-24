import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as estimatesApi from "@/lib/api/estimates"
import { ApiError } from "@/lib/api/client"
import { EstimateList } from "./EstimateList"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(() => vi.restoreAllMocks())

const ITEMS: estimatesApi.EstimateListItem[] = [
  {
    id: 1,
    filename: "ready.xlsx",
    status: "ready",
    nodesCount: 10,
    createdAt: "2026-06-24T10:00:00Z",
  },
  {
    id: 2,
    filename: "blocked.xlsx",
    status: "blocked",
    nodesCount: 0,
    createdAt: "2026-06-24T11:00:00Z",
  },
]

describe("EstimateList", () => {
  it("показывает пустое состояние, когда смет нет", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue([])
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText(/пока нет разобранных смет/i)).toBeInTheDocument()
  })

  it("рисует строки и бейджи статусов", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText("ready.xlsx")).toBeInTheDocument()
    expect(screen.getByText("Готово")).toBeInTheDocument()
    expect(screen.getByText("Отклонено")).toBeInTheDocument()
  })

  it("клик по готовой смете зовёт onOpen с item", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    const onOpen = vi.fn()
    render(<EstimateList onOpen={onOpen} />)
    await userEvent.click(await screen.findByText("ready.xlsx"))
    expect(onOpen).toHaveBeenCalledWith(ITEMS[0])
  })

  it("blocked-смета не кликабельна (onOpen не зовётся)", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockResolvedValue(ITEMS)
    const onOpen = vi.fn()
    render(<EstimateList onOpen={onOpen} />)
    await userEvent.click(await screen.findByText("blocked.xlsx"))
    expect(onOpen).not.toHaveBeenCalled()
  })

  it("удаление через диалог зовёт deleteEstimate и рефетчит список", async () => {
    const listSpy = vi
      .spyOn(estimatesApi, "listEstimates")
      .mockResolvedValueOnce(ITEMS)
      .mockResolvedValueOnce([ITEMS[1]])
    const delSpy = vi
      .spyOn(estimatesApi, "deleteEstimate")
      .mockResolvedValue(undefined)
    render(<EstimateList onOpen={vi.fn()} />)
    await screen.findByText("ready.xlsx")
    // у строки с id=1 жмём кнопку удаления (aria-label содержит имя файла)
    await userEvent.click(
      screen.getByRole("button", { name: /удалить ready\.xlsx/i })
    )
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /^удалить$/i })
    )
    await vi.waitFor(() => expect(delSpy).toHaveBeenCalledWith(1))
    expect(listSpy).toHaveBeenCalledTimes(2)
  })

  it("на ошибке загрузки показывает сообщение", async () => {
    vi.spyOn(estimatesApi, "listEstimates").mockRejectedValue(
      new ApiError(500, "Не удалось загрузить сметы")
    )
    render(<EstimateList onOpen={vi.fn()} />)
    expect(await screen.findByText(/не удалось загрузить/i)).toBeInTheDocument()
  })
})
