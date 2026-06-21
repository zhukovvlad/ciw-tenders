import { afterEach, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ApiError } from "@/lib/api/client"
import { AuthProvider } from "@/lib/auth/AuthContext"
import * as authApi from "@/lib/api/auth"
import { LoginScreen } from "./LoginScreen"

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

it("на 401 показывает «неверный логин или пароль»", async () => {
  vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "bad"))
  render(
    <AuthProvider>
      <LoginScreen />
    </AuthProvider>
  )
  await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
  await userEvent.type(screen.getByLabelText(/пароль/i), "x")
  await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
  expect(
    await screen.findByText(/неверный логин или пароль/i)
  ).toBeInTheDocument()
})
