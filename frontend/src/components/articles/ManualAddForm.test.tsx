import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { ManualAddForm } from "./ManualAddForm"

afterEach(() => vi.restoreAllMocks())

describe("ManualAddForm", () => {
  it("создаёт статью и зовёт onCreated", async () => {
    const onCreated = vi.fn()
    const spy = vi
      .spyOn(articlesApi, "createArticle")
      .mockResolvedValue({ id: 1, article_code: "1", name: "Раздел", parent_id: null })
    render(<ManualAddForm onCreated={onCreated} />)
    // /^Код$/ — иначе матчит и «Код родителя» (multiple elements)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Раздел")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(spy).toHaveBeenCalledWith({ article_code: "1", name: "Раздел", parent_code: null })
    expect(onCreated).toHaveBeenCalledOnce()
  })

  it("показывает ошибку бэкенда (409 дубликат)", async () => {
    vi.spyOn(articlesApi, "createArticle").mockRejectedValue(new ApiError(409, "уже существует"))
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Дубль")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(await screen.findByText(/уже существует/i)).toBeInTheDocument()
  })
})
