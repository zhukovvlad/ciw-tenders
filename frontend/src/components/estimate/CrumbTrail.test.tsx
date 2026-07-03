import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import { CrumbTrail } from "@/components/estimate/CrumbTrail"

describe("CrumbTrail", () => {
  it("короткая цепочка — все уровни", () => {
    render(
      <CrumbTrail levels={["Раздел 1", "Конструктив", "Подземная часть"]} />
    )
    const el = screen.getByText(/Раздел 1/)
    expect(el.textContent).toBe("Раздел 1 › Конструктив › Подземная часть")
  })

  it("длинная цепочка — средний эллипсис: первый + два последних", () => {
    render(
      <CrumbTrail
        levels={[
          "Раздел 1",
          "ООО Длинное Юридическое",
          "Этап 2",
          "Конструктив",
          "2.4 Подземная часть",
        ]}
      />
    )
    const el = screen.getByText(/Раздел 1/)
    expect(el.textContent).toBe(
      "Раздел 1 › … › Конструктив › 2.4 Подземная часть"
    )
    // полная цепочка доступна ховером
    expect(el).toHaveAttribute(
      "title",
      "Раздел 1 › ООО Длинное Юридическое › Этап 2 › Конструктив › 2.4 Подземная часть"
    )
  })

  it("пустая цепочка — ничего не рендерит", () => {
    const { container } = render(<CrumbTrail levels={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
