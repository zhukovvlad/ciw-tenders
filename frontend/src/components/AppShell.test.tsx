import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { AuthUser } from "@/lib/types"
import * as authCtx from "@/lib/auth/useAuth"
import * as session from "@/lib/session"
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

afterEach(() => {
  vi.restoreAllMocks()
  logout.mockClear()
})

describe("AppShell", () => {
  it("клик по вкладке зовёт onTab", async () => {
    mockAuth()
    const onTab = vi.fn()
    render(
      <AppShell tab="estimate" onTab={onTab}>
        контент
      </AppShell>
    )
    await userEvent.click(screen.getByRole("tab", { name: /справочник/i }))
    expect(onTab).toHaveBeenCalledWith("articles")
  })

  it("из меню пользователя выходит (clearReview + logout)", async () => {
    mockAuth()
    const clearReview = vi
      .spyOn(session, "clearReview")
      .mockImplementation(() => {})
    render(
      <AppShell tab="estimate" onTab={vi.fn()}>
        контент
      </AppShell>
    )
    await userEvent.click(screen.getByRole("button", { name: /a@mr\.kz/i }))
    await userEvent.click(screen.getByRole("menuitem", { name: /выйти/i }))
    expect(clearReview).toHaveBeenCalledOnce()
    expect(logout).toHaveBeenCalledOnce()
  })
})
