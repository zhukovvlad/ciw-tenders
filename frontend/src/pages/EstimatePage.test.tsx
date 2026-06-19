import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { EstimatePage } from "@/pages/EstimatePage"

describe("EstimatePage", () => {
  it("отображает форму загрузки сметы", () => {
    render(<EstimatePage />)

    expect(screen.getByText("Загрузка сметы")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Сопоставить/ })).toBeDisabled()
  })
})
