import { describe, expect, it } from "vitest"
import i18n from "@/lib/i18n"

describe("i18n", () => {
  it("инициализирован с ru и поддерживает ru/tr", () => {
    expect(i18n.options.fallbackLng).toContain("ru")
    expect(i18n.options.supportedLngs).toEqual(
      expect.arrayContaining(["ru", "tr"])
    )
  })

  it("резолвит общий ключ и падает на ru как fallback", async () => {
    await i18n.changeLanguage("ru")
    expect(i18n.t("common.cancel")).toBe("Отмена")
    await i18n.changeLanguage("tr")
    expect(i18n.t("common.cancel")).toBe("İptal")
  })

  it("нормализует регион-вариант tr-TR → tr (load: languageOnly)", async () => {
    await i18n.changeLanguage("tr-TR")
    expect(i18n.resolvedLanguage).toBe("tr")
    expect(i18n.t("common.cancel")).toBe("İptal") // турецкий, не fallback ru
    await i18n.changeLanguage("ru")
  })

  it("синхронизирует document.documentElement.lang и title при смене языка", async () => {
    await i18n.changeLanguage("tr")
    expect(document.documentElement.lang).toBe("tr")
    expect(document.title).toBe("MR · Keşifler")
    await i18n.changeLanguage("ru")
    expect(document.title).toBe("MR · Сметы")
  })
})
