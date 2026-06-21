import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import * as articlesApi from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { WipeCatalog } from "./WipeCatalog"

afterEach(() => vi.restoreAllMocks())

describe("WipeCatalog", () => {
  it("кнопка активна только после ввода слова-подтверждения", async () => {
    render(<WipeCatalog onWiped={vi.fn()} />)
    const btn = screen.getByRole("button", { name: /очистить справочник/i })
    expect(btn).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    expect(btn).toBeEnabled()
  })

  it("очищает и показывает «Удалено N»", async () => {
    const onWiped = vi.fn()
    vi.spyOn(articlesApi, "deleteAllArticles").mockResolvedValue(362)
    render(<WipeCatalog onWiped={onWiped} />)
    await userEvent.type(screen.getByLabelText(/подтверждени/i), "УДАЛИТЬ")
    await userEvent.click(screen.getByRole("button", { name: /очистить справочник/i }))
    expect(await screen.findByText(/удалено 362/i)).toBeInTheDocument()
    expect(onWiped).toHaveBeenCalledOnce()
  })

  it("показывает ошибку ApiError и сбрасывает слово-подтверждение", async () => {
    vi.spyOn(articlesApi, "deleteAllArticles").mockRejectedValue(new ApiError(500, "сбой очистки"))
    render(<WipeCatalog onWiped={vi.fn()} />)
    const input = screen.getByLabelText(/подтверждени/i)
    await userEvent.type(input, "УДАЛИТЬ")
    await userEvent.click(screen.getByRole("button", { name: /очистить справочник/i }))
    expect(await screen.findByText(/сбой очистки/i)).toBeInTheDocument()
    expect(input).toHaveValue("")
    expect(screen.getByRole("button", { name: /очистить справочник/i })).toBeDisabled()
  })
})
