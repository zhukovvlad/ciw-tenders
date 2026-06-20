import { afterEach, describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { AuthGate } from "@/components/auth/AuthGate"
import { logout } from "@/lib/mock/auth"

afterEach(() => logout())

describe("AuthGate", () => {
  it("показывает вход, затем контент после логина", async () => {
    render(<AuthGate><div>Секретный контент</div></AuthGate>)
    expect(screen.queryByText("Секретный контент")).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText(/логин/i), "operator")
    await userEvent.type(screen.getByLabelText(/пароль/i), "secret")
    await userEvent.click(screen.getByRole("button", { name: /Войти/ }))
    expect(await screen.findByText("Секретный контент")).toBeInTheDocument()
  })
})
