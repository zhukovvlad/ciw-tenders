import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"
import { ContextStrip } from "@/pages/estimate/ContextStrip"
import { initReview } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

// row(...) — хелпер как в Task 2 Step 1
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

const ROWS: MatchRow[] = [
  row(1, 0, "excluded", { source_name: "Орг-заголовок", breadcrumb: [] }),
  row(2, 1, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(3, 2, "needs_review", { breadcrumb: ["Орг-заголовок"] }),
  row(4, 3, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(5, 4, "confident", {
    source_name: "Другой раздел работа",
    breadcrumb: ["Раздел Б"],
  }),
  row(6, 5, "confident", { breadcrumb: ["Раздел Б"] }),
]

describe("ContextStrip", () => {
  it("окно ±2 вокруг активной по sourceIndex, включая excluded (приглушён)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    // окно: строки 1..5 (source_index 0..4); строки 6 нет
    expect(screen.getByText(/Орг-заголовок/)).toBeInTheDocument()
    expect(screen.queryByText("Строка 6")).not.toBeInTheDocument()
    const org = screen.getByText(/Орг-заголовок/).closest("[data-row]")!
    expect(org.className).toContain("opacity-60")
  })

  it("активная строка помечена", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen.getByText("Строка 3").closest("[data-row]")!
    expect(active).toHaveAttribute("data-active", "true")
  })

  it("разделитель на границе верхнеуровневого раздела", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={4} />)
    // между строкой 4 (раздел «Орг-заголовок») и строкой 5 («Раздел Б»)
    expect(screen.getByTestId("section-boundary")).toBeInTheDocument()
  })

  it("активная строка — маркер «вы здесь», не статус", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen
      .getByText("Строка 3")
      .closest("[data-row]") as HTMLElement
    expect(within(active).getByLabelText("вы здесь")).toBeInTheDocument()
    expect(active.textContent).not.toContain("→")
  })
})
