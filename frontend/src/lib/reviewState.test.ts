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
  promotableCount,
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
        breadcrumb: [],
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

  it("statusLabel: нетронутый фонд-хит → «Из фонда», override → «Ручной выбор», reject → «Нет совпадения»", () => {
    const row = fundRow()
    expect(
      statusLabel(row, {
        kind: "confirmed",
        code: "a",
        name: "b",
        manual: false,
      })
    ).toBe("Из фонда")
    expect(
      statusLabel(row, {
        kind: "confirmed",
        code: "a",
        name: "b",
        manual: true,
      })
    ).toBe("Ручной выбор")
    expect(statusLabel(row, { kind: "no_match" })).toBe("Нет совпадения")
  })

  it("requiresDecision: matched_fund не требует ревью (как confident)", () => {
    expect(requiresDecision(fundRow())).toBe(false)
  })

  // Пин-тест на дефект финального ревью: requiresDecision был инверсией
  // (не confident/matched_fund), из-за чего excluded (орг-заголовки) и pending
  // ошибочно попадали в «требует решения» и в знаменатель progress().total.
  it("requiresDecision: excluded и pending — вне ревью, не входят в progress().total", () => {
    const excludedRow: MatchRow = {
      ...fundRow(),
      row_number: 9201,
      status: "excluded",
    }
    const pendingStatusRow: MatchRow = {
      ...fundRow(),
      row_number: 9202,
      status: "pending",
    }
    expect(requiresDecision(excludedRow)).toBe(false)
    expect(requiresDecision(pendingStatusRow)).toBe(false)

    const totalBefore = progress(base()).total
    const s = initReview("смета.xlsx", [
      ...MOCK_ROWS,
      excludedRow,
      pendingStatusRow,
    ])
    // добавление excluded/pending-строк не должно раздувать знаменатель прогресса
    expect(progress(s).total).toBe(totalBefore)
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

  it("initReview гидратирует решения из review_status бэка (повторное открытие сметы)", () => {
    const base = MOCK_ROWS.find((r) => r.status === "needs_review")!
    const confirmed = {
      ...base,
      row_number: 9101,
      review_status: "confirmed" as const,
      final_code: "СМР-1",
      final_name: "Подтверждённая",
    }
    const overridden = {
      ...base,
      row_number: 9102,
      review_status: "overridden" as const,
      final_code: "СМР-2",
      final_name: "Ручная",
    }
    const rejected = {
      ...base,
      row_number: 9103,
      review_status: "rejected" as const,
    }
    const untouched = { ...base, row_number: 9104 }
    const s = initReview("смета.xlsx", [
      confirmed,
      overridden,
      rejected,
      untouched,
    ])
    expect(decisionFor(s, confirmed)).toMatchObject({
      kind: "confirmed",
      manual: false,
      code: "СМР-1",
    })
    expect(decisionFor(s, overridden)).toMatchObject({
      kind: "confirmed",
      manual: true,
      code: "СМР-2",
    })
    expect(decisionFor(s, rejected)).toEqual({ kind: "no_match" })
    expect(decisionFor(s, untouched)).toEqual({ kind: "pending" })
    // прогресс сразу учитывает уже решённые строки
    expect(progress(s).reviewed).toBe(3)
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

  it("statusLabel: excluded → «Контекст», pending → «В обработке»", () => {
    const ex = { ...MOCK_ROWS[0], status: "excluded" as const }
    const pd = { ...MOCK_ROWS[0], status: "pending" as const }
    expect(statusLabel(ex, { kind: "pending" })).toBe("Контекст")
    expect(statusLabel(pd, { kind: "pending" })).toBe("В обработке")
  })

  it("pick/reject на confident-строке не двигает progress() (спека editable-confident-rows §4)", () => {
    const r = rowNum("confident")
    const total0 = progress(base()).total
    const picked = reviewReducer(base(), {
      type: "manualPick",
      row: r,
      candidate: {
        id: null,
        article_code: "СМР-99-999",
        name: "Ручная",
        score: 0,
        breadcrumb: [],
      },
    })
    expect(progress(picked)).toEqual({ reviewed: 0, total: total0 })
    const rejected = reviewReducer(base(), {
      type: "confirmNoMatch",
      row: r,
    })
    expect(progress(rejected)).toEqual({ reviewed: 0, total: total0 })
  })
})

const BASE: MatchRow = {
  row_number: 1,
  section_code: "1",
  source_name: "Работа",
  sourceIndex: 0,
  breadcrumb: [],
  matchError: null,
  status: "confident",
  score: 0.95,
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
}

describe("promotableCount — зеркало серверного предиката фонда", () => {
  it("unreviewed confident НЕ промоутабелен (авто-уверенность ≠ решение оператора)", () => {
    expect(promotableCount([BASE])).toBe(0)
  })
  it("confirmed промоутабелен", () => {
    expect(
      promotableCount([
        { ...BASE, status: "needs_review", review_status: "confirmed" },
      ])
    ).toBe(1)
  })
  it("overridden промоутабелен", () => {
    expect(
      promotableCount([
        { ...BASE, status: "needs_review", review_status: "overridden" },
      ])
    ).toBe(1)
  })
  it("подтверждённый фонд-хит НЕ промоутабелен (анти-накрутка)", () => {
    expect(
      promotableCount([
        { ...BASE, status: "matched_fund", review_status: "confirmed" },
      ])
    ).toBe(0)
  })
  it("overridden фонд-хит промоутабелен (механика конфликтов фонда)", () => {
    expect(
      promotableCount([
        { ...BASE, status: "matched_fund", review_status: "overridden" },
      ])
    ).toBe(1)
  })
})
