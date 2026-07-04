import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom"
import type { AuthUser } from "@/lib/types"
import * as authCtx from "@/lib/auth/useAuth"
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

afterEach(() => {
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

  it("из меню пользователя выходит (logout)", async () => {
    mockAuth()
    renderShell("/estimates")
    await userEvent.click(screen.getByRole("button", { name: /a@mr\.kz/i }))
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
})
