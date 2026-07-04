import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import { ApiError } from "@/lib/api/client"
import { AuthProvider } from "@/lib/auth/AuthContext"
import * as authApi from "@/lib/api/auth"
import { LoginScreen } from "./LoginScreen"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

beforeEach(() => {
  vi.clearAllMocks()
})

function renderLogin() {
  return render(
    <AuthProvider>
      <LoginScreen />
    </AuthProvider>
  )
}

describe("LoginScreen", () => {
  it("рендерит поля Логин и Пароль через FormLabel", () => {
    renderLogin()
    expect(screen.getByLabelText(/логин/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/пароль/i)).toBeInTheDocument()
  })

  it("на 401 показывает инлайн-ошибку «Неверный логин или пароль», toast НЕ вызывается", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(new ApiError(401, "bad"))
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверный логин или пароль"
    )
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("на другую ошибку — инлайн «Не удалось войти», toast НЕ вызывается", async () => {
    vi.spyOn(authApi, "login").mockRejectedValue(
      new ApiError(500, "server error")
    )
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Не удалось войти/
    )
    expect(toast.error).not.toHaveBeenCalled()
  })

  it("повторный сабмит с верными данными убирает старую root-ошибку", async () => {
    vi.spyOn(authApi, "login")
      .mockRejectedValueOnce(new ApiError(401, "bad"))
      .mockResolvedValueOnce("tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "user",
      is_active: true,
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "x")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await screen.findByRole("alert")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    )
  })

  it("zod: пустой email показывает ошибку валидации без запроса к серверу", async () => {
    const spy = vi.spyOn(authApi, "login")
    renderLogin()
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await waitFor(() => expect(spy).not.toHaveBeenCalled())
    expect(await screen.findByText(/введите логин/i)).toBeInTheDocument()
    expect(await screen.findByText(/введите пароль/i)).toBeInTheDocument()
  })

  it("кнопка деактивирована во время запроса", async () => {
    vi.spyOn(authApi, "login").mockReturnValue(new Promise(() => {}))
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "pass")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(screen.getByRole("button", { name: /Войти/ })).toBeDisabled()
  })

  it("успешный вход не показывает toast.error", async () => {
    vi.spyOn(authApi, "login").mockResolvedValue("tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "user",
      is_active: true,
    })
    renderLogin()
    await userEvent.type(screen.getByLabelText(/логин/i), "a@mr.kz")
    await userEvent.type(screen.getByLabelText(/пароль/i), "pass")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    await waitFor(() => expect(toast.error).not.toHaveBeenCalled())
  })
})
