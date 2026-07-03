import { useEffect } from "react"

interface Options {
  enabled: boolean
  candidateCount: number
  /** Enter активен ⇔ рекомендация отрисована (правило карточки: клавиша ⇔ элемент). Default true. */
  canConfirm?: boolean
  onPick: (index: number) => void
  onConfirm: () => void
  onNext: () => void
  /** 0 — «оставить без пары» */
  onReject?: () => void
  /** ← — undo; no-op при пустом стеке решает вызывающий */
  onUndo?: () => void
}

function isEditable(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  return Boolean(
    target.closest("input, textarea, select, [contenteditable='true']")
  )
}

export function useReviewKeyboard({
  enabled,
  candidateCount,
  canConfirm,
  onPick,
  onConfirm,
  onNext,
  onReject,
  onUndo,
}: Options): void {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      if (isEditable(e.target)) return
      // Единая точка глушения хоткеев при модалке (спека §3b): Radix держит
      // data-state="open" на контенте диалога
      if (
        document.querySelector(
          '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]'
        )
      )
        return
      if (e.key === "1" || e.key === "2" || e.key === "3") {
        const idx = Number(e.key) - 1
        if (idx < candidateCount) {
          e.preventDefault()
          onPick(idx)
        }
      } else if (e.key === "Enter") {
        if (canConfirm !== false) {
          e.preventDefault()
          onConfirm()
        }
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault()
        onNext()
      } else if (e.key === "0") {
        e.preventDefault()
        onReject?.()
      } else if (e.key === "ArrowLeft") {
        e.preventDefault()
        onUndo?.()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [
    enabled,
    candidateCount,
    canConfirm,
    onPick,
    onConfirm,
    onNext,
    onReject,
    onUndo,
  ])
}
