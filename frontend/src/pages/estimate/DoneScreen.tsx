import { Download } from "lucide-react"
import type { ReviewState } from "@/lib/types"
import { decisionFor } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"

interface DoneScreenProps { state: ReviewState; onExport: () => void; onNewEstimate: () => void }

export function DoneScreen({ state, onExport, onNewEstimate }: DoneScreenProps) {
  const matched = state.rows.filter((r) => decisionFor(state, r).kind === "confirmed").length
  const noPair = state.rows.filter((r) => decisionFor(state, r).kind === "no_match").length
  return (
    <div className="mx-auto max-w-md p-10 text-center">
      <div className="mb-6 flex justify-center gap-10">
        <div><div className="font-display text-4xl text-[var(--success)]">{matched}</div><div className="text-xs uppercase tracking-wide text-muted-foreground">сопоставлено</div></div>
        <div><div className="font-display text-4xl text-destructive">{noPair}</div><div className="text-xs uppercase tracking-wide text-muted-foreground">без пары</div></div>
      </div>
      <p className="mb-5 text-sm text-muted-foreground">Исходный Excel + колонки: код статьи, наименование, score, статус, топ-3 альтернативы.</p>
      <Button onClick={onExport}><Download className="size-4" />Скачать обогащённый .xlsx</Button>
      <div className="mt-4">
        <button onClick={onNewEstimate} className="text-sm text-[var(--ds-accent-hover)]">＋ Загрузить следующую смету</button>
      </div>
    </div>
  )
}
