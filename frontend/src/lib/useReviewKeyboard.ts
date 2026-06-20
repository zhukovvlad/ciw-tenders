import { useEffect } from "react"

interface Options {
  enabled: boolean
  candidateCount: number
  onPick: (index: number) => void
  onConfirm: () => void
  onNext: () => void
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
  onPick,
  onConfirm,
  onNext,
}: Options): void {
  useEffect(() => {
    if (!enabled) return
    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      if (isEditable(e.target)) return
      if (e.key === "1" || e.key === "2" || e.key === "3") {
        const idx = Number(e.key) - 1
        if (idx < candidateCount) {
          e.preventDefault()
          onPick(idx)
        }
      } else if (e.key === "Enter") {
        e.preventDefault()
        onConfirm()
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault()
        onNext()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [enabled, candidateCount, onPick, onConfirm, onNext])
}
