import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import { AUTH_TOKEN_KEY } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { AuthGate } from "./AuthGate"

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe("AuthGate", () => {
  it("без токена показывает форму входа, не контент", async () => {
    render(
      <AuthProvider>
        <AuthGate>
          <div>Секрет</div>
        </AuthGate>
      </AuthProvider>,
    )
    expect(await screen.findByRole("button", { name: /Войти/ })).toBeInTheDocument()
    expect(screen.queryByText("Секрет")).not.toBeInTheDocument()
  })

  it("с валидным токеном показывает контент", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "admin",
      is_active: true,
    })
    render(
      <AuthProvider>
        <AuthGate>
          <div>Секрет</div>
        </AuthGate>
      </AuthProvider>,
    )
    expect(await screen.findByText("Секрет")).toBeInTheDocument()
  })
})
