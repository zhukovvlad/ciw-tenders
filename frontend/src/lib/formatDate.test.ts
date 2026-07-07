import { describe, expect, it } from "vitest"
import { formatDate } from "./formatDate"

describe("formatDate", () => {
  const iso = "2026-07-07T09:05:00Z"
  it("форматирует по ru-RU", () => {
    expect(formatDate(iso, "ru")).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
  it("форматирует по tr-TR", () => {
    expect(formatDate(iso, "tr")).toMatch(/\d{2}\.\d{2}\.\d{4}/)
  })
  it("невалидную дату возвращает как есть", () => {
    expect(formatDate("нет", "ru")).toBe("нет")
  })
})
