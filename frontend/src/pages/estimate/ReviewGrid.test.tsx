import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { createRef } from "react"
import { ReviewGrid } from "@/pages/estimate/ReviewGrid"
import { initReview } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

function row(
  n: number,
  si: number,
  status: MatchStatus = "needs_review",
  over: Partial<MatchRow> = {}
): MatchRow {
  return {
    row_number: n,
    section_code: `1.${n}`,
    source_name: `Строка ${n}`,
    sourceIndex: si,
    breadcrumb: [],
    matchError: null,
    status,
    score: 0.8,
    matched_code: "01.01",
    matched_name: "Статья",
    matched_article_id: 7,
    matchedBreadcrumb: [],
    candidates: [],
    review_status: "unreviewed",
    final_article_id: null,
    finalBreadcrumb: [],
    final_code: null,
    final_name: null,
    ...over,
  }
}

const RECT = { width: 1024, height: 600 }

function manyRows(n: number): MatchRow[] {
  return Array.from({ length: n }, (_, i) =>
    row(i + 1, i, i % 10 === 0 ? "needs_review" : "confident")
  )
}

function renderGrid(rows: MatchRow[], over: Record<string, unknown> = {}) {
  const scrollOffsetRef = createRef<number | null>() as React.MutableRefObject<
    number | null
  >
  scrollOffsetRef.current = null
  const onOpenRow = vi.fn()
  render(
    <ReviewGrid
      state={initReview("смета.xlsx", rows)}
      dispatch={vi.fn()}
      onOpenRow={onOpenRow}
      scrollOffsetRef={scrollOffsetRef}
      initialRect={RECT}
      {...over}
    />
  )
  return { onOpenRow, scrollOffsetRef }
}

describe("ReviewGrid: виртуализация", () => {
  it("рендерит окно, а не все 500 строк", () => {
    renderGrid(manyRows(500))
    const rendered = screen.getAllByRole("row") // включая шапку
    expect(rendered.length).toBeGreaterThan(5)
    expect(rendered.length).toBeLessThan(60) // 600px / 64px + overscan ≪ 500
  })
})

describe("ReviewGrid: клики", () => {
  it("клик по строке (включая confident) зовёт onOpenRow", async () => {
    const { onOpenRow } = renderGrid([
      row(1, 0, "confident"),
      row(2, 1, "needs_review"),
    ])
    await userEvent.click(screen.getByText("Строка 1"))
    expect(onOpenRow).toHaveBeenCalledWith(1)
  })

  it("excluded некликабелен; без onOpenRow (read-only) не кликабельно ничего", async () => {
    const { onOpenRow } = renderGrid([
      row(1, 0, "excluded", { source_name: "Орг" }),
      row(2, 1, "needs_review"),
    ])
    await userEvent.click(screen.getByText("Орг"))
    expect(onOpenRow).not.toHaveBeenCalled()
  })
})

describe("hover по кликабельности (этап 3)", () => {
  it("с onOpenRow: hover и cursor у решаемой строки, у excluded — нет", () => {
    renderGrid([
      row(1, 0, "needs_review", { source_name: "Кликабельная работа" }),
      row(2, 1, "excluded", { source_name: "Орг-заголовок" }),
    ])
    const clickable = screen
      .getByText("Кликабельная работа")
      .closest('[role="row"]')!
    const excluded = screen.getByText("Орг-заголовок").closest('[role="row"]')!
    expect(clickable.className).toContain("hover:bg-muted/50")
    expect(clickable.className).toContain("cursor-pointer")
    expect(excluded.className).not.toContain("hover:bg-muted/50")
    expect(excluded.className).not.toContain("cursor-pointer")
  })

  it("read-only (без onOpenRow): hover нет ни у кого", () => {
    renderGrid(
      [row(1, 0, "needs_review", { source_name: "Кликабельная работа" })],
      { onOpenRow: undefined }
    )
    const readOnlyRow = screen
      .getByText("Кликабельная работа")
      .closest('[role="row"]')!
    expect(readOnlyRow.className).not.toContain("hover:bg-muted/50")
    expect(readOnlyRow.className).not.toContain("cursor-pointer")
  })
})
