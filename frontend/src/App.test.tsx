// frontend/src/App.test.tsx
import { afterEach, describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { App } from "@/App"
import { AUTH_KEY } from "@/lib/mock/auth"
import { clearReview } from "@/lib/session"

afterEach(() => {
  localStorage.clear()
  clearReview()
})

describe("App", () => {
  it("после входа показывает поток сметы и переключает на справочник", async () => {
    localStorage.setItem(AUTH_KEY, "mock-token") // считаем, что уже вошли
    render(<App />)
    // поток сметы стартует с dropzone
    expect(screen.getByLabelText(/файл сметы/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Справочник/ }))
    expect(screen.getByText(/Новая статья справочника/i)).toBeInTheDocument()
  })
})
