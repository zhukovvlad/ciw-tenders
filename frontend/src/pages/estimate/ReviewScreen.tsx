// frontend/src/pages/estimate/ReviewScreen.tsx
import { useMemo, useState } from "react"
import { Download, Plus } from "lucide-react"
import type { ReviewState } from "@/lib/types"
import {
  type ReviewAction, decisionFor, filteredRows, progress,
} from "@/lib/reviewState"
import { Button } from "@/components/ui/button"
import { ReviewRow } from "@/pages/estimate/ReviewRow"
import { useReviewKeyboard } from "@/lib/useReviewKeyboard"

interface ReviewScreenProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction>
  onExport: () => void
  onNewEstimate: () => void
}

const counts = (state: ReviewState) => ({
  confident: state.rows.filter((r) => r.status === "confident").length,
  review: state.rows.filter((r) => r.status === "needs_review").length,
  no_match: state.rows.filter((r) => r.status === "no_match").length,
})

export function ReviewScreen({ state, dispatch, onExport, onNewEstimate }: ReviewScreenProps) {
  // useMemo: rows/queue стабильны между рендерами, пока не изменился state — иначе
  // новый массив на каждый рендер пересоздавал бы автостарт-эффект (и нервировал
  // react-hooks/exhaustive-deps). Стабилизируем, а не глушим правило.
  const rows = useMemo(() => filteredRows(state), [state])
  const { reviewed, total } = progress(state)
  const c = counts(state)
  const [activeRowOverride, setActiveRowOverride] = useState<number | null | "auto">("auto")

  // Очередь навигации = спорные строки ИЗ ВИДИМОГО (отфильтрованного) набора,
  // чтобы «следующая» не уезжала на строку, скрытую активным фильтром.
  const queue = useMemo(() => rows.filter((r) => r.status !== "confident"), [rows])

  // Производное: если "auto" — первая нерешённая; иначе — явное значение
  const activeRow = useMemo<number | null>(() => {
    if (activeRowOverride === "auto") {
      const first = queue.find((r) => decisionFor(state, r).kind === "pending")
      return first ? first.row_number : null
    }
    return activeRowOverride
  }, [activeRowOverride, queue, state])

  const setActiveRow = (v: number | null) => setActiveRowOverride(v)

  const gotoNext = () => {
    const idx = queue.findIndex((r) => r.row_number === activeRow)
    const next = queue.slice(idx + 1).find((r) => decisionFor(state, r).kind === "pending")
      ?? queue.find((r) => decisionFor(state, r).kind === "pending")
    setActiveRowOverride(next ? next.row_number : null)
  }

  const active = state.rows.find((r) => r.row_number === activeRow)
  useReviewKeyboard({
    enabled: Boolean(active),
    candidateCount: active?.candidates.length ?? 0,
    onPick: (i) => { if (active?.candidates[i]) { dispatch({ type: "pickCandidate", row: active.row_number, code: active.candidates[i].article_code }); gotoNext() } },
    onConfirm: () => { if (active) { dispatch({ type: "confirmArbiter", row: active.row_number }); gotoNext() } },
    onNext: gotoNext,
  })

  const chip = (key: ReviewState["filter"], label: string) => (
    <button
      onClick={() => dispatch({ type: "setFilter", filter: key })}
      className={"rounded-full border px-3 py-1.5 text-xs " + (state.filter === key ? "border-primary bg-primary text-primary-foreground" : "border-border text-[var(--ds-text-2)]")}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--ds-hairline)] px-4 py-3">
        <span className="text-sm">{state.fileName}</span>
        <span className="text-xs text-muted-foreground">· {state.rows.length} строк СМР</span>
        <div className="flex gap-2">
          <span className="rounded-full bg-[color-mix(in_srgb,var(--success)_16%,transparent)] px-2.5 py-1 text-xs text-[var(--success)]">{c.confident} уверенных</span>
          <span className="rounded-full bg-[color-mix(in_srgb,var(--warning)_18%,transparent)] px-2.5 py-1 text-xs text-[var(--warning)]">{c.review} проверить</span>
          <span className="rounded-full bg-[color-mix(in_srgb,var(--destructive)_16%,transparent)] px-2.5 py-1 text-xs text-destructive">{c.no_match} без пары</span>
        </div>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" onClick={onNewEstimate}><Plus className="size-4" />Новая смета</Button>
          <Button size="sm" onClick={onExport}><Download className="size-4" />Выгрузить Excel</Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex gap-2">
          {chip("all", `Все · ${state.rows.length}`)}
          {chip("review", `Проверить · ${c.review}`)}
          {chip("no_match", `Без пары · ${c.no_match}`)}
        </div>
        <span className="ml-2 text-xs text-muted-foreground">проверено {reviewed} из {total}</span>
      </div>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-4 py-2.5 font-normal">#</th>
            <th className="px-4 py-2.5 font-normal">Работа из сметы</th>
            <th className="px-4 py-2.5 font-normal">Статья справочника СМР</th>
            <th className="px-4 py-2.5 text-right font-normal">Score</th>
            <th className="px-4 py-2.5 font-normal">Статус</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <ReviewRow
              key={row.row_number}
              row={row}
              decision={decisionFor(state, row)}
              expanded={activeRow === row.row_number}
              onToggle={() => setActiveRow(activeRow === row.row_number ? null : row.row_number)}
              onPickCandidate={(code) => { dispatch({ type: "pickCandidate", row: row.row_number, code }); gotoNext() }}
              onManualPick={(cand) => { dispatch({ type: "manualPick", row: row.row_number, candidate: cand }); gotoNext() }}
              onConfirmNoMatch={() => { dispatch({ type: "confirmNoMatch", row: row.row_number }); gotoNext() }}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
