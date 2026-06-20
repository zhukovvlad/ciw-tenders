import type { ReviewState } from "@/lib/types"

export const REVIEW_SESSION_KEY = "ciw.review.v1"

export function saveReview(state: ReviewState): void {
  try {
    sessionStorage.setItem(REVIEW_SESSION_KEY, JSON.stringify(state))
  } catch (err) {
    // Прототип-стенд-ин. На крупных сметах прод обязан использовать IndexedDB (per спека).
    // Не глушим молча: иначе провал восстановления невидим.
    console.warn(
      "saveReview: не удалось сохранить сессию (вероятно QuotaExceededError) — нужен IndexedDB в проде",
      err
    )
  }
}

export function loadReview(): ReviewState | null {
  const raw = sessionStorage.getItem(REVIEW_SESSION_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as ReviewState
  } catch {
    return null
  }
}

export function clearReview(): void {
  sessionStorage.removeItem(REVIEW_SESSION_KEY)
}
