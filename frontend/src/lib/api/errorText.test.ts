import type { TFunction } from "i18next"
import { describe, expect, it } from "vitest"

import { ApiError } from "./client"
import { apiErrorText } from "./errorText"

const t = ((k: string) =>
  k === "errors.estimate_not_found"
    ? "Смета не найдена"
    : k === "errors.generic"
      ? "Что-то пошло не так"
      : k === "screen.fallback"
        ? "Не удалось"
        : k) as unknown as TFunction

describe("apiErrorText", () => {
  it("код есть в словаре → перевод по коду", () => {
    expect(
      apiErrorText(
        new ApiError(404, "Смета не найдена", "estimate_not_found"),
        t,
        "screen.fallback"
      )
    ).toBe("Смета не найдена")
  })
  it("код неизвестен, есть detail → русский detail бэка", () => {
    expect(
      apiErrorText(
        new ApiError(400, "Спец-текст бэка", "some_new_code"),
        t,
        "screen.fallback"
      )
    ).toBe("Спец-текст бэка")
  })
  it("ApiError без detail и без известного кода → errors.generic", () => {
    expect(
      apiErrorText(new ApiError(500, "", undefined), t, "screen.fallback")
    ).toBe("Что-то пошло не так")
  })
  it("не ApiError → экранный fallback", () => {
    expect(apiErrorText(new Error("boom"), t, "screen.fallback")).toBe(
      "Не удалось"
    )
  })
})
