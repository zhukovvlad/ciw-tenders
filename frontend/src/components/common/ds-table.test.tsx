import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "./ds-table"

function renderRows() {
  return render(
    <DsTable>
      <DsTableHeader>
        <DsTableRow>
          <DsTableHead>Колонка</DsTableHead>
        </DsTableRow>
      </DsTableHeader>
      <DsTableBody>
        <DsTableRow data-testid="plain">
          <DsTableCell>обычная</DsTableCell>
        </DsTableRow>
        <DsTableRow data-testid="clickable" interactive>
          <DsTableCell>кликабельная</DsTableCell>
        </DsTableRow>
      </DsTableBody>
    </DsTable>
  )
}

describe("ds-table", () => {
  it("неинтерактивная строка активно гасит вендорный hover", () => {
    renderRows()
    const row = screen.getByTestId("plain")
    expect(row.className).toContain("hover:bg-transparent")
    expect(row.className).not.toContain("hover:bg-muted/50")
    expect(row.className).not.toContain("cursor-pointer")
  })

  it("интерактивная строка сохраняет hover и получает cursor-pointer", () => {
    renderRows()
    const row = screen.getByTestId("clickable")
    expect(row.className).toContain("hover:bg-muted/50")
    expect(row.className).toContain("cursor-pointer")
  })

  it("ячейка шапки несёт DS-канон: uppercase text-xs, вендорный h-10 погашен", () => {
    renderRows()
    const head = screen.getByRole("columnheader", { name: "Колонка" })
    expect(head.className).toContain("uppercase")
    expect(head.className).toContain("h-auto")
    expect(head.className).not.toContain("font-medium")
  })
})
