import { afterEach, describe, expect, it, vi } from "vitest"
import * as client from "@/lib/api/client"
import {
  deleteEstimate,
  listEstimates,
  rowFromDto,
} from "@/lib/api/estimates"

afterEach(() => vi.restoreAllMocks())

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

describe("estimates api list/delete", () => {
  it("listEstimates маппит snake_case DTO в camelCase", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      {
        id: 1,
        filename: "a.xlsx",
        status: "ready",
        nodes_count: 12,
        created_at: "2026-06-24T10:00:00Z",
      },
    ])
    const items = await listEstimates()
    expect(items).toEqual([
      {
        id: 1,
        filename: "a.xlsx",
        status: "ready",
        nodesCount: 12,
        createdAt: "2026-06-24T10:00:00Z",
      },
    ])
  })

  it("listEstimates ходит на GET /estimates", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue([])
    await listEstimates()
    expect(spy).toHaveBeenCalledWith("/estimates")
  })

  it("deleteEstimate шлёт DELETE по id", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await deleteEstimate(7)
    expect(spy).toHaveBeenCalledWith("DELETE", "/estimates/7")
  })
})
