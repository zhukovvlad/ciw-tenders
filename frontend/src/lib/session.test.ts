import { afterEach, describe, expect, it } from "vitest"
import { saveReview, loadReview, clearReview } from "@/lib/session"
import { initReview } from "@/lib/reviewState"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

afterEach(() => clearReview())

describe("session", () => {
  it("round-trip: сохранили → загрузили то же", () => {
    const state = initReview("смета.xlsx", MOCK_ROWS)
    saveReview(state)
    const loaded = loadReview()
    expect(loaded?.fileName).toBe("смета.xlsx")
    expect(loaded?.rows).toHaveLength(15)
  })
  it("loadReview без данных → null", () => {
    expect(loadReview()).toBeNull()
  })
  it("clearReview стирает", () => {
    saveReview(initReview("x.xlsx", MOCK_ROWS))
    clearReview()
    expect(loadReview()).toBeNull()
  })
})
