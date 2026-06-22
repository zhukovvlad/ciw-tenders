import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import * as articlesApi from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { WipeCatalog } from "./WipeCatalog"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => vi.restoreAllMocks())

async function openDialog() {
  await userEvent.click(
    screen.getByRole("button", { name: /очистить справочник/i })
  )
  return screen.findByRole("alertdialog")
}

describe("WipeCatalog", () => {
  it("кнопка подтверждения активна только после ввода слова", async () => {
    render(<WipeCatalog onWiped={vi.fn()} />)
    const dialog = await openDialog()
    const confirm = within(dialog).getByRole("button", {
      name: /очистить справочник/i,
    })
    expect(confirm).toBeDisabled()
    await userEvent.type(within(dialog).getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    expect(confirm).toBeEnabled()
  })

  it("очищает и шлёт тост «Удалено N»", async () => {
    const onWiped = vi.fn()
    vi.spyOn(articlesApi, "deleteAllArticles").mockResolvedValue(362)
    render(<WipeCatalog onWiped={onWiped} />)
    const dialog = await openDialog()
    await userEvent.type(within(dialog).getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /очистить справочник/i })
    )
    await vi.waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/удалено 362/i)
      )
    )
    expect(onWiped).toHaveBeenCalledOnce()
  })

  it("на ошибке ApiError шлёт тост и сбрасывает слово", async () => {
    vi.spyOn(articlesApi, "deleteAllArticles").mockRejectedValue(
      new ApiError(500, "сбой очистки")
    )
    render(<WipeCatalog onWiped={vi.fn()} />)
    const dialog = await openDialog()
    const input = within(dialog).getByLabelText(/подтверждени/i)
    await userEvent.type(input, "УДАЛИТЬ")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /очистить справочник/i })
    )
    await vi.waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/сбой очистки/i)
      )
    )
    expect(input).toHaveValue("")
  })
})
