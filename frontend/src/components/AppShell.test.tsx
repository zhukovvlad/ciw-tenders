import { afterEach, describe, expect, it, vi } from "vitest"
import { act, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom"
import type { AuthUser } from "@/lib/types"
import * as authCtx from "@/lib/auth/useAuth"
import i18n from "@/lib/i18n"
import { AppShell } from "./AppShell"

const USER: AuthUser = {
  id: 1,
  email: "a@mr.kz",
  role: "admin",
  is_active: true,
}
const logout = vi.fn()

function mockAuth() {
  vi.spyOn(authCtx, "useAuth").mockReturnValue({
    user: USER,
    role: USER.role,
    loading: false,
    error: null,
    login: vi.fn(),
    logout,
  })
}

function renderShell(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          element={
            <AppShell>
              <Outlet />
            </AppShell>
          }
        >
          <Route path="/estimates" element={<div>estimates-page</div>} />
          <Route path="/articles" element={<div>articles-page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

afterEach(async () => {
  // Порядок важен: afterEach выполняются в обратном порядке регистрации,
  // так что этот блок отрабатывает ДО глобального cleanup() из test/setup.ts —
  // AppShell на этот момент ещё смонтирован. changeLanguage триггерит
  // languageChanged → ре-рендер AppShell; если мок useAuth уже снят,
  // ре-рендер зовёт реальный useAuth() без AuthProvider и падает. Поэтому
  // сначала возвращаем язык (мок ещё активен), потом снимаем моки.
  await act(() => i18n.changeLanguage("ru"))
  vi.restoreAllMocks()
  logout.mockClear()
})

describe("AppShell", () => {
  it("таб «Справочник» ведёт на /articles", async () => {
    mockAuth()
    renderShell("/estimates")
    await userEvent.click(screen.getByRole("tab", { name: /Справочник/ }))
    expect(screen.getByText("articles-page")).toBeInTheDocument()
  })

  it("бренд — ссылка на /estimates", async () => {
    mockAuth()
    renderShell("/articles")
    await userEvent.click(screen.getByText(/MR/))
    expect(screen.getByText("estimates-page")).toBeInTheDocument()
  })

  it("из меню пользователя выходит (logout); переключателя языка в меню нет", async () => {
    mockAuth()
    renderShell("/estimates")
    await userEvent.click(screen.getByRole("button", { name: /a@mr\.kz/i }))
    // Переключатель языка переехал на нав-панель — в меню его больше нет.
    expect(screen.queryByRole("menuitemradio")).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole("menuitem", { name: /выйти/i }))
    expect(logout).toHaveBeenCalledOnce()
  })

  it("компактный режим: email скрыт ниже md, иконка-заглушка присутствует", () => {
    mockAuth()
    renderShell("/estimates")
    const email = screen.getByText("a@mr.kz")
    expect(email.className).toContain("hidden")
    expect(email.className).toContain("md:inline")
  })

  it("триггер меню пользователя имеет aria-label с email (accessible name ниже md)", () => {
    mockAuth()
    renderShell("/estimates")
    const trigger = screen.getByRole("button", { name: /a@mr\.kz/i })
    expect(trigger).toHaveAttribute("aria-label", "a@mr.kz")
  })

  it("сегмент на нав-панели переключает интерфейс на турецкий и персистит выбор", async () => {
    mockAuth()
    renderShell("/estimates")
    // Сегмент RU/TR прямо в шапке — без открытия меню аккаунта.
    await userEvent.click(screen.getByRole("radio", { name: "Türkçe" }))
    // Nav-текст сменился на турецкий (таб «Справочник» → «Sözlük»)
    expect(screen.getByRole("tab", { name: /Sözlük/ })).toBeInTheDocument()
    expect(localStorage.getItem("ciw.ui.lang")).toBe("tr")
    expect(document.documentElement.lang).toBe("tr")
  })
})
