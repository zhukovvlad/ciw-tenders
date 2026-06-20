import { describe, expect, it } from "vitest"
import {
  initReview,
  reviewReducer,
  decisionFor,
  progress,
  filteredRows,
  statusLabel,
} from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

const base = () => initReview("смета.xlsx", MOCK_ROWS)
const rowNum = (status: string) =>
  MOCK_ROWS.find((r) => r.status === status)!.row_number

describe("reviewState", () => {
  it("confident инициализируются как confirmed, спорные — pending", () => {
    const s = base()
    expect(
      decisionFor(s, MOCK_ROWS.find((r) => r.status === "confident")!).kind
    ).toBe("confirmed")
    expect(
      decisionFor(s, MOCK_ROWS.find((r) => r.status === "needs_review")!).kind
    ).toBe("pending")
  })

  it("progress: total = спорные + без пары, изначально reviewed считает только confident? нет — только требующие", () => {
    const s = base()
    const review = MOCK_ROWS.filter((r) => r.status !== "confident").length
    expect(progress(s).total).toBe(review)
    expect(progress(s).reviewed).toBe(0)
  })

  it("confirmArbiter закрывает спорную строку и двигает прогресс", () => {
    const r = rowNum("needs_review")
    const s = reviewReducer(base(), { type: "confirmArbiter", row: r })
    const d = decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!)
    expect(d.kind).toBe("confirmed")
    expect(progress(s).reviewed).toBe(1)
  })

  it("confirmNoMatch закрывает строку «без пары» (входит в счётчик)", () => {
    const r = rowNum("no_match")
    const s = reviewReducer(base(), { type: "confirmNoMatch", row: r })
    expect(
      decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!).kind
    ).toBe("no_match")
    expect(progress(s).reviewed).toBe(1)
  })

  it("manualPick помечает manual:true", () => {
    const r = rowNum("needs_review")
    const s = reviewReducer(base(), {
      type: "manualPick",
      row: r,
      candidate: {
        article_code: "СМР-99-999",
        name: "Ручная",
        section_name: "X",
        score: 0,
      },
    })
    const d = decisionFor(s, MOCK_ROWS.find((x) => x.row_number === r)!)
    expect(d).toMatchObject({
      kind: "confirmed",
      manual: true,
      code: "СМР-99-999",
    })
  })

  it("filter=review показывает только needs_review", () => {
    const s = reviewReducer(base(), { type: "setFilter", filter: "review" })
    expect(filteredRows(s).every((r) => r.status === "needs_review")).toBe(true)
  })

  it("statusLabel различает арбитра, ручной выбор и без пары", () => {
    expect(
      statusLabel(MOCK_ROWS[0], {
        kind: "confirmed",
        code: "x",
        name: "y",
        manual: false,
      })
    ).toBe("Подтверждено оператором")
    expect(
      statusLabel(MOCK_ROWS[0], {
        kind: "confirmed",
        code: "x",
        name: "y",
        manual: true,
      })
    ).toBe("Ручной выбор")
    expect(statusLabel(MOCK_ROWS[0], { kind: "no_match" })).toBe(
      "Нет совпадения"
    )
  })
})
