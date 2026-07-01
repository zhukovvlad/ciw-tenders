import { describe, expect, it } from "vitest"
import {
  initReview,
  reviewReducer,
  decisionFor,
  decisionFromRow,
  progress,
  filteredRows,
  requiresDecision,
  statusLabel,
} from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"
import type { MatchRow } from "@/lib/types"

const fundRow = (): MatchRow => ({
  ...MOCK_ROWS.find((r) => r.status === "confident")!,
  row_number: 9001,
  status: "matched_fund",
  matched_code: "СМР-01-001",
  matched_name: "Подготовительные работы и содержание площадки",
})

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
        id: null,
        article_code: "СМР-99-999",
        name: "Ручная",
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

  it("requiresDecision: matched_fund не требует ревью (как confident)", () => {
    expect(requiresDecision(fundRow())).toBe(false)
  })

  it("initReview авто-подтверждает matched_fund строку (не остаётся pending)", () => {
    const row = fundRow()
    const s = initReview("смета.xlsx", [row])
    expect(decisionFor(s, row)).toEqual({
      kind: "confirmed",
      code: "СМР-01-001",
      name: "Подготовительные работы и содержание площадки",
      manual: false,
    })
  })

  it("decisionFromRow выводит решение из review_status бэка", () => {
    const row = MOCK_ROWS.find((r) => r.status === "needs_review")!
    expect(decisionFromRow({ ...row, review_status: "unreviewed" })).toEqual({
      kind: "pending",
    })
    expect(decisionFromRow({ ...row, review_status: "rejected" })).toEqual({
      kind: "no_match",
    })
    expect(
      decisionFromRow({
        ...row,
        review_status: "overridden",
        final_code: "СМР-X",
        final_name: "Ручная",
      })
    ).toMatchObject({ kind: "confirmed", manual: true, code: "СМР-X" })
  })

  it("syncRow заменяет строку и выставляет решение из ответа бэка", () => {
    const r = MOCK_ROWS.find((x) => x.status === "needs_review")!
    const authoritative = {
      ...r,
      review_status: "overridden" as const,
      final_article_id: 999,
      final_code: "СМР-99-999",
      final_name: "Подтверждённая бэком",
    }
    const s = reviewReducer(base(), { type: "syncRow", row: authoritative })
    // строка в снимке заменена авторитетной
    expect(s.rows.find((x) => x.row_number === r.row_number)!.final_code).toBe(
      "СМР-99-999"
    )
    // решение выведено из review_status
    expect(decisionFor(s, r)).toMatchObject({
      kind: "confirmed",
      manual: true,
      code: "СМР-99-999",
    })
    expect(progress(s).reviewed).toBe(1)
  })
})
