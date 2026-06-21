import { describe, expect, it } from "vitest"
import { MOCK_ROWS, MOCK_ARTICLES } from "@/lib/mock/fixtures"

describe("MOCK_ROWS", () => {
  it("содержит 15 строк СМР", () => {
    expect(MOCK_ROWS).toHaveLength(15)
  })
  it("у каждой needs_review есть ровно 3 кандидата и rationale", () => {
    const review = MOCK_ROWS.filter((r) => r.status === "needs_review")
    expect(review.length).toBeGreaterThan(0)
    for (const r of review) {
      expect(r.candidates).toHaveLength(3)
      expect(r.rationale).toBeTruthy()
      expect(r.matched_code).toBeTruthy()
    }
  })
  it("confident-строки имеют matched_code и не имеют rationale", () => {
    const conf = MOCK_ROWS.filter((r) => r.status === "confident")
    expect(conf.length).toBeGreaterThan(0)
    for (const r of conf) {
      expect(r.matched_code).toBeTruthy()
      expect(r.rationale).toBeNull()
    }
  })
  it("no_match-строки без matched_code", () => {
    const nm = MOCK_ROWS.filter((r) => r.status === "no_match")
    expect(nm.length).toBeGreaterThan(0)
    for (const r of nm) expect(r.matched_code).toBeNull()
  })
  it("справочник для ручного поиска непустой", () => {
    expect(MOCK_ARTICLES.length).toBeGreaterThan(10)
  })
})
