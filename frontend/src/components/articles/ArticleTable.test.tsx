import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { Article } from "@/lib/types"
import { ArticleTable } from "./ArticleTable"

const ARTS: Article[] = [
  { id: 1, article_code: "1", name: "Подготовка", parent_id: null },
  { id: 2, article_code: "1.1", name: "Котлован", parent_id: 1 },
  { id: 3, article_code: "2", name: "Фасады", parent_id: null },
]

describe("ArticleTable", () => {
  it("рендерит все строки", () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    expect(screen.getByText("Подготовка")).toBeInTheDocument()
    expect(screen.getByText("Котлован")).toBeInTheDocument()
    expect(screen.getByText("Фасады")).toBeInTheDocument()
  })

  it("фильтрует по коду или имени", async () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    await userEvent.type(screen.getByPlaceholderText(/поиск/i), "фасад")
    expect(screen.getByText("Фасады")).toBeInTheDocument()
    expect(screen.queryByText("Подготовка")).not.toBeInTheDocument()
  })

  it("у не-админа нет кнопок удаления", () => {
    render(<ArticleTable articles={ARTS} isAdmin={false} />)
    expect(screen.queryByLabelText(/удалить/i)).not.toBeInTheDocument()
  })

  it("у админа подтверждение в диалоге зовёт onDelete с id", async () => {
    const onDelete = vi.fn()
    render(<ArticleTable articles={ARTS} isAdmin onDelete={onDelete} />)
    await userEvent.click(screen.getAllByLabelText(/удалить/i)[0])
    const dialog = await screen.findByRole("alertdialog")
    await userEvent.click(
      within(dialog).getByRole("button", { name: /удалить/i })
    )
    expect(onDelete).toHaveBeenCalledWith(1)
  })
})
