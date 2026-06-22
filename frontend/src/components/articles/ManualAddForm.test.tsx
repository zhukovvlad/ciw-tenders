import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { ManualAddForm } from "./ManualAddForm"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => vi.restoreAllMocks())

beforeEach(() => {
  vi.clearAllMocks()
})

describe("ManualAddForm", () => {
  it("рендерит поля Код, Наименование, Код родителя через FormLabel", () => {
    render(<ManualAddForm onCreated={vi.fn()} />)
    expect(screen.getByLabelText(/^Код$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/наименование/i)).toBeInTheDocument()
  })

  it("создаёт статью, зовёт onCreated и шлёт toast.success", async () => {
    const onCreated = vi.fn()
    const spy = vi.spyOn(articlesApi, "createArticle").mockResolvedValue({
      id: 1,
      article_code: "1",
      name: "Раздел",
      parent_id: null,
    })
    render(<ManualAddForm onCreated={onCreated} />)
    // /^Код$/ — иначе матчит и «Код родителя» (multiple elements)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Раздел")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    expect(spy).toHaveBeenCalledWith({
      article_code: "1",
      name: "Раздел",
      parent_code: null,
    })
    expect(onCreated).toHaveBeenCalledOnce()
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/добавлена/i)
      )
    )
  })

  it("после успеха форма сбрасывается (поля пустые)", async () => {
    vi.spyOn(articlesApi, "createArticle").mockResolvedValue({
      id: 1,
      article_code: "1",
      name: "Раздел",
      parent_id: null,
    })
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Раздел")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() => expect(toast.success).toHaveBeenCalled())
    expect(screen.getByLabelText(/^Код$/i)).toHaveValue("")
    expect(screen.getByLabelText(/наименование/i)).toHaveValue("")
  })

  it("показывает ошибку бэкенда (409 дубликат) через toast.error", async () => {
    vi.spyOn(articlesApi, "createArticle").mockRejectedValue(
      new ApiError(409, "уже существует")
    )
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "1")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Дубль")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/уже существует/i)
      )
    )
  })

  it("zod: пустые обязательные поля не вызывают API", async () => {
    const spy = vi.spyOn(articlesApi, "createArticle")
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() => expect(spy).not.toHaveBeenCalled())
  })

  it("parent_code пустой → передаётся как null", async () => {
    const spy = vi.spyOn(articlesApi, "createArticle").mockResolvedValue({
      id: 2,
      article_code: "2",
      name: "Sub",
      parent_id: null,
    })
    render(<ManualAddForm onCreated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText(/^Код$/i), "2")
    await userEvent.type(screen.getByLabelText(/наименование/i), "Sub")
    await userEvent.click(screen.getByRole("button", { name: /добавить/i }))
    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith(
        expect.objectContaining({ parent_code: null })
      )
    )
  })
})
