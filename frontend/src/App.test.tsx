// frontend/src/App.test.tsx
import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { App } from "@/App"
import { ThemeProvider } from "@/components/theme-provider"
import { AUTH_TOKEN_KEY } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import * as articlesApi from "@/lib/api/articles"
import { clearReview } from "@/lib/session"

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
  clearReview()
})

describe("App", () => {
  it("после входа показывает поток сметы и переключает на справочник", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: 1,
      email: "a@mr.kz",
      role: "admin",
      is_active: true,
    })
    vi.spyOn(articlesApi, "listArticles").mockResolvedValue([])
    render(
      <ThemeProvider defaultTheme="system">
        <App />
      </ThemeProvider>
    )
    // поток сметы стартует с dropzone
    expect(await screen.findByLabelText(/файл сметы/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Справочник/ }))
    expect(await screen.findByText(/Справочник СМР/i)).toBeInTheDocument()
  })
})
