import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError, AUTH_TOKEN_KEY } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import { AuthProvider, useAuth } from "./AuthContext"

const ADMIN = { id: 1, email: "a@mr.kz", role: "admin" as const, is_active: true }

function Probe() {
  const { user, role, loading, error, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="state">
        {loading ? "loading" : user ? `${user.email}:${role}` : error ? `err:${error}` : "anon"}
      </span>
      <button onClick={() => login("a@mr.kz", "pw")}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe("AuthContext", () => {
  it("без токена — anon, не loading", async () => {
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
  })

  it("login кладёт токен и заполняет user", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue("tok")
    vi.spyOn(authApi, "me").mockResolvedValue(ADMIN)
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    await userEvent.click(screen.getByText("login"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("a@mr.kz:admin"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("tok")
  })

  it("стартовый 401 на me() → logout (токен очищен)", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "stale")
    vi.spyOn(authApi, "me").mockRejectedValue(new ApiError(401, "no"))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })

  it("стартовая сеть/5xx на me() → токен СОХРАНЁН, показана ошибка", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "good")
    vi.spyOn(authApi, "me").mockRejectedValue(new ApiError(503, "down"))
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("err:"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBe("good")
  })

  it("logout чистит токен и user", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue("tok")
    vi.spyOn(authApi, "me").mockResolvedValue(ADMIN)
    render(<AuthProvider><Probe /></AuthProvider>)
    await userEvent.click(screen.getByText("login"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("a@mr.kz:admin"))
    await userEvent.click(screen.getByText("logout"))
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("anon"))
    expect(sessionStorage.getItem(AUTH_TOKEN_KEY)).toBeNull()
  })
})
