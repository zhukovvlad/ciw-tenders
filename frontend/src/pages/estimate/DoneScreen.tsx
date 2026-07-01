import { useRef, useState } from "react"
import { Download } from "lucide-react"
import { toast } from "sonner"
import type { ReviewState } from "@/lib/types"
import { decisionFor } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { setReference } from "@/lib/api/estimates"

interface DoneScreenProps {
  state: ReviewState
  onExport: () => void
  onNewEstimate: () => void
  estimateId: number | null
}

export function DoneScreen({
  state,
  onExport,
  onNewEstimate,
  estimateId,
}: DoneScreenProps) {
  const [inFund, setInFund] = useState(false)
  const toggleSeq = useRef(0)
  const matched = state.rows.filter(
    (r) => decisionFor(state, r).kind === "confirmed"
  ).length
  const noPair = state.rows.filter(
    (r) => decisionFor(state, r).kind === "no_match"
  ).length

  function handleToggleFund(next: boolean) {
    if (estimateId === null) {
      toast.error("Не удалось определить смету для добавления в фонд")
      return
    }
    const seq = ++toggleSeq.current
    setInFund(next)
    setReference(estimateId, next)
      .then((r) => {
        if (seq === toggleSeq.current) setInFund(r.is_reference)
      })
      .catch((err: unknown) => {
        if (seq === toggleSeq.current) setInFund(!next)
        console.error(err)
        toast.error(
          err instanceof Error
            ? err.message
            : "Не удалось обновить фонд решений"
        )
      })
  }

  return (
    <div className="mx-auto max-w-md p-10 text-center">
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
      <p className="mb-5 text-sm text-muted-foreground">
        Исходный Excel + колонки: код статьи, наименование, score, статус, топ-3
        альтернативы.
      </p>
      <Button onClick={onExport}>
        <Download className="size-4" />
        Скачать обогащённый .xlsx
      </Button>
      <div className="mt-6 flex items-center justify-center gap-3 text-left">
        <span className="text-sm text-[var(--ds-text-2)]">
          Эталонная смета — добавить в фонд решений
        </span>
        <Switch
          checked={inFund}
          disabled={estimateId === null}
          onCheckedChange={handleToggleFund}
          aria-label="Эталонная смета — добавить в фонд решений"
        />
      </div>
      <div className="mt-4">
        <button
          onClick={onNewEstimate}
          className="text-sm text-[var(--ds-accent-hover)]"
        >
          ＋ Загрузить следующую смету
        </button>
      </div>
    </div>
  )
}
