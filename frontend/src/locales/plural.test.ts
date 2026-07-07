import { afterAll, describe, expect, it } from "vitest"
import i18n from "@/lib/i18n"

describe("плюрализация review.pendingRows", () => {
  afterAll(async () => {
    await i18n.changeLanguage("ru")
  })
  it("ru: one/few/many", async () => {
    await i18n.changeLanguage("ru")
    expect(i18n.t("review.pendingRows", { count: 1 })).toContain(
      "спорная строка"
    )
    expect(i18n.t("review.pendingRows", { count: 3 })).toContain(
      "спорные строки"
    )
    expect(i18n.t("review.pendingRows", { count: 5 })).toContain(
      "спорных строк"
    )
  })
  it("tr: one/other резолвятся без падения", async () => {
    await i18n.changeLanguage("tr")
    const one = i18n.t("review.pendingRows", { count: 1 })
    const other = i18n.t("review.pendingRows", { count: 5 })
    expect(one).not.toBe("review.pendingRows") // ключ разрешился
    expect(other).not.toBe("review.pendingRows")
  })
})
