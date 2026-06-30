import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { StructuralAnomaly } from "@/lib/types"
import { StructureNotice } from "./StructureNotice"

const ONE_ANOMALY: StructuralAnomaly[] = [
  {
    kind: "duplicate_code",
    sourceIndex: 2,
    code: "1.1",
    name: "B",
    detail: "код встречается 2 раз",
  },
]

describe("StructureNotice", () => {
  it("рендерит заголовок «1 замечание» и detail аномалии", async () => {
    render(
      <StructureNotice anomalies={ONE_ANOMALY} outlineOverrides={115} />
    )
    // Заголовок содержит «1 замечание»
    expect(
      screen.getByText(/структура сметы.*1 замечание/i)
    ).toBeInTheDocument()

    // Раскрываем блок
    await userEvent.click(
      screen.getByRole("button", { name: /структура сметы/i })
    )
    // Виден detail аномалии
    expect(screen.getByText(/код встречается 2 раз/i)).toBeInTheDocument()
    // Видна агрегатная строка про outline, содержащая 115
    const aggregate = screen.getByText(/вложенность взята из группировки/i)
    expect(aggregate).toBeInTheDocument()
    expect(aggregate).toHaveTextContent("115")
  })

  it("рендерит правильную плюрализацию: 2 замечания, 5 замечаний", () => {
    const two: StructuralAnomaly[] = [
      { ...ONE_ANOMALY[0] },
      { ...ONE_ANOMALY[0], sourceIndex: 3, code: "1.2" },
    ]
    const { rerender } = render(
      <StructureNotice anomalies={two} outlineOverrides={0} />
    )
    expect(screen.getByText(/2 замечания/i)).toBeInTheDocument()

    const five: StructuralAnomaly[] = Array.from({ length: 5 }, (_, i) => ({
      ...ONE_ANOMALY[0],
      sourceIndex: i,
      code: String(i),
    }))
    rerender(<StructureNotice anomalies={five} outlineOverrides={0} />)
    expect(screen.getByText(/5 замечаний/i)).toBeInTheDocument()
  })

  it("не рендерит агрегатную строку, если outlineOverrides === 0", async () => {
    render(<StructureNotice anomalies={ONE_ANOMALY} outlineOverrides={0} />)
    await userEvent.click(
      screen.getByRole("button", { name: /структура сметы/i })
    )
    expect(
      screen.queryByText(/вложенность взята из группировки/i)
    ).not.toBeInTheDocument()
  })

  it("не рендерит ничего, если anomalies пуст и outlineOverrides === 0", () => {
    const { container } = render(
      <StructureNotice anomalies={[]} outlineOverrides={0} />
    )
    expect(container.firstChild).toBeNull()
  })
})
