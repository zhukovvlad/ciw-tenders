import { describe, expect, it } from "vitest"
import { rowFromDto } from "@/lib/api/estimates"

describe("rowFromDto", () => {
  it("maps DTO to MatchRow (id→row_number, code→article_code)", () => {
    const row = rowFromDto({
      id: 42,
      name: "Кладка",
      status: "needs_review",
      score: 0.7,
      matched_code: "2.1",
      matched_name: "Статья",
      matched_article_id: 7,
      candidates: [{ id: 7, code: "2.1", name: "Статья", score: 0.7 }],
      review_status: "unreviewed",
      final_article_id: null,
      final_code: null,
      final_name: null,
    })
    expect(row.row_number).toBe(42)
    expect(row.source_name).toBe("Кладка")
    expect(row.candidates[0].article_code).toBe("2.1")
    expect(row.review_status).toBe("unreviewed")
  })
})
