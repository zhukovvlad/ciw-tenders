import type { TFunction } from "i18next"

import { ApiError } from "./client"

/**
 * Единая цепочка показа ошибки API (спека §4.4):
 *   код есть в словаре → русский detail бэка → errors.generic;
 *   не ApiError → экранный fallbackKey.
 */
export function apiErrorText(
  err: unknown,
  t: TFunction,
  fallbackKey: string
): string {
  if (err instanceof ApiError) {
    if (err.code) {
      const key = `errors.${err.code}`
      const translated = t(key)
      if (translated !== key) return translated
    }
    if (err.message) return err.message
    return t("errors.generic")
  }
  return t(fallbackKey)
}
