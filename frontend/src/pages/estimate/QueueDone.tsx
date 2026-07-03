import type { ReviewState } from "@/lib/types"
import { decisionFor, progress } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"

interface QueueDoneProps {
  state: ReviewState
  onComplete: () => void
  onShowGrid: () => void
}

export function QueueDone({ state, onComplete, onShowGrid }: QueueDoneProps) {
  const { reviewed, total } = progress(state)

  const matched = state.rows.filter(
    (r) => decisionFor(state, r).kind === "confirmed"
  ).length
  const noPair = state.rows.filter(
    (r) => decisionFor(state, r).kind === "no_match"
  ).length

  return (
    <div className="mx-auto max-w-md p-10 text-center">
      <h2 className="mb-6 text-xl font-semibold">Все спорные строки решены</h2>
      <p className="mb-6 text-muted-foreground">
        Решено {reviewed} из {total}
      </p>

      <div className="mb-6 flex justify-center gap-10">
        <div>
          <div className="font-display text-4xl text-[var(--success)]">
            {matched}
          </div>
          <div className="text-xs tracking-wide text-muted-foreground uppercase">
            сопоставлено
          </div>
        </div>
        <div>
          <div className="font-display text-4xl text-destructive">{noPair}</div>
          <div className="text-xs tracking-wide text-muted-foreground uppercase">
            без пары
          </div>
        </div>
      </div>

      <Button onClick={onComplete} className="mb-4 w-full">
        Завершить проверку
      </Button>

      <Button variant="outline" onClick={onShowGrid} className="w-full">
        Посмотреть таблицу
      </Button>
    </div>
  )
}
