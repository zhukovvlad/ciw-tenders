import { describe, expect, it, vi } from "vitest"
import { matchEstimate, searchArticles, exportEstimateCsv } from "@/lib/mock/api"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

describe("mock api", () => {
  it("matchEstimate возвращает строки и сообщает прогресс, ETA только на matching", async () => {
    const phases: string[] = []
    const etaByPhase: Record<string, number | null> = {}
    const rows = await matchEstimate(new File([""], "смета.xlsx"), (p) => {
      phases.push(p.phase)
      etaByPhase[p.phase] = p.etaSeconds
    })
    expect(rows.length).toBe(15)
    expect(phases).toContain("embedding")
    expect(phases).toContain("matching")
    expect(etaByPhase["embedding"]).toBeNull()
    expect(typeof etaByPhase["matching"]).toBe("number")
  })

  it("searchArticles фильтрует справочник по подстроке без регистра", async () => {
    const res = await searchArticles("кровл")
    expect(res.some((c) => c.name.toLowerCase().includes("кровл"))).toBe(true)
  })

  it("exportEstimateCsv: ручной выбор → пустой Score, статус «Ручной выбор»", () => {
    const state = initReview("смета.xlsx", MOCK_ROWS)
    state.decisions[3] = { kind: "confirmed", code: "СМР-99-999", name: "Ручная статья", manual: true }
    const csv = exportEstimateCsv(state)
    const line = csv.split("\n").find((l) => l.startsWith("3;"))!
    const cells = line.split(";")
    // колонки: row;source;code;name;score;status;alt2;alt3
    expect(cells[2]).toBe("СМР-99-999")
    expect(cells[4]).toBe("") // score пустой
    expect(cells[5]).toContain("Ручной выбор")
  })
})
