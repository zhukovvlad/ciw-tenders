import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import type { AuthUser } from "@/lib/types"
import * as articlesApi from "@/lib/api/articles"
import * as authCtx from "@/lib/auth/AuthContext"
import { ArticlesPage } from "./ArticlesPage"

const USER: AuthUser = { id: 2, email: "u@mr.kz", role: "user", is_active: true }
const ADMIN: AuthUser = { id: 1, email: "a@mr.kz", role: "admin", is_active: true }

function mockAuth(user: AuthUser) {
  vi.spyOn(authCtx, "useAuth").mockReturnValue({
    user,
    role: user.role,
    loading: false,
    error: null,
    login: vi.fn(),
    logout: vi.fn(),
  })
}

afterEach(() => vi.restoreAllMocks())

describe("ArticlesPage", () => {
  it("показывает список после загрузки", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([
      { id: 1, article_code: "1", name: "Подготовка", parent_id: null },
    ])
    render(<ArticlesPage />)
    expect(await screen.findByText("Подготовка")).toBeInTheDocument()
  })

  it("пустой справочник — подсказка", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    expect(await screen.findByText(/справочник пуст/i)).toBeInTheDocument()
  })

  it("ошибка загрузки — сообщение + повтор", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockRejectedValue(new Error("fail"))
    render(<ArticlesPage />)
    expect(await screen.findByText(/не удалось загрузить/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /повторить/i })).toBeInTheDocument()
  })

  it("не-админ не видит admin-секций (загрузка шаблона)", async () => {
    mockAuth(USER)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    await screen.findByText(/справочник пуст/i)
    expect(screen.queryByText(/загрузить шаблон/i)).not.toBeInTheDocument()
  })

  it("админ видит секцию загрузки шаблона", async () => {
    mockAuth(ADMIN)
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(<ArticlesPage />)
    expect(await screen.findByText(/загрузить шаблон/i)).toBeInTheDocument()
  })
})
