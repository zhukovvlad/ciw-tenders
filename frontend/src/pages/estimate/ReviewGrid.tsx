import { useEffect, useRef } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import { Database } from "lucide-react"
import type { MatchStatus, ReviewState } from "@/lib/types"
import {
  type ReviewAction,
  decisionFor,
  filteredRows,
  isNoMatch,
  isPendingReview,
  requiresDecision,
  statusLabel,
} from "@/lib/reviewState"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  dsHairline,
  dsHeadCellClass,
  dsHeadRowClass,
} from "@/components/common/ds-table"

const ROW_H = 64
const GRID_COLS = "grid-cols-[100px_1fr_1fr_80px_160px]"

interface ReviewGridProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction> // чипы-фильтры (setFilter) живут в гриде
  /** undefined ⇒ read-only (завершённая смета): клики выключены */
  onOpenRow?: (rowNumber: number) => void
  /** память позиции скролла между режимами; null — грид ещё не открывали */
  scrollOffsetRef: React.MutableRefObject<number | null>
  /** скролл к строке при входе (в очередь вошли не из грида → активная) */
  focusRowNumber?: number | null
  /** только для jsdom-тестов: размер вьюпорта виртуализатора */
  initialRect?: { width: number; height: number }
}

// Exhaustive-контракт (спека §2b): все семь MatchStatus обязаны иметь тон —
// добавление статуса в MatchStatus без ключа здесь роняет компиляцию.
const statusTone: Record<MatchStatus, string> = {
  pending: "text-muted-foreground",
  excluded: "text-muted-foreground",
  confident: "text-[var(--success)]",
  needs_review: "text-[var(--warning)]",
  no_match: "text-destructive",
  error: "text-destructive",
  matched_fund: "text-[var(--ds-accent-hover)]",
}

// Счётчики чипов decision-aware (см. isPendingReview/isNoMatch): решённая строка
// покидает группу, «Проверить»/«Без пары» показывают реальный остаток работы.
const counts = (state: ReviewState) => ({
  confident: state.rows.filter((r) => r.status === "confident").length,
  review: state.rows.filter((r) => isPendingReview(r, decisionFor(state, r)))
    .length,
  no_match: state.rows.filter((r) => isNoMatch(r, decisionFor(state, r)))
    .length,
})

export function ReviewGrid({
  state,
  dispatch,
  onOpenRow,
  scrollOffsetRef,
  focusRowNumber,
  initialRect,
}: ReviewGridProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const rows = filteredRows(state)
  const c = counts(state)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_H,
    overscan: 8,
    // jsdom не считает layout: offsetWidth/offsetHeight контейнера всегда 0,
    // и штатный observeElementRect тут же затирает initialRect нулевым
    // прямоугольником. В тестах (initialRect передан) подменяем измеритель
    // константным колбэком — единственный способ реально включить
    // виртуализацию окна под jsdom.
    ...(initialRect
      ? {
          initialRect,
          observeElementRect: (
            _instance: unknown,
            cb: (rect: { width: number; height: number }) => void
          ) => {
            cb(initialRect)
            return () => {}
          },
        }
      : {}),
  })

  useEffect(() => {
    if (focusRowNumber != null) {
      const idx = rows.findIndex((r) => r.row_number === focusRowNumber)
      if (idx >= 0) virtualizer.scrollToIndex(idx, { align: "center" })
    } else if (scrollOffsetRef.current != null) {
      virtualizer.scrollToOffset(scrollOffsetRef.current)
    }
    // только на монтаж — восстановление позиции
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const chip = (key: ReviewState["filter"], label: string) => (
    <button
      key={key}
      onClick={() => dispatch({ type: "setFilter", filter: key })}
      className={
        "rounded-full border px-3 py-1.5 text-xs " +
        (state.filter === key
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border text-[var(--ds-text-2)]")
      }
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <div className="flex gap-2">
          {chip("all", `Все · ${state.rows.length}`)}
          {chip("review", `Проверить · ${c.review}`)}
          {chip("no_match", `Без пары · ${c.no_match}`)}
        </div>
      </div>

      <div
        ref={parentRef}
        onScroll={(e) => {
          scrollOffsetRef.current = e.currentTarget.scrollTop
        }}
        className="relative h-[calc(100vh-184px)] overflow-auto"
        role="table"
      >
        <div className="min-w-[720px]">
          <div
            role="row"
            className={cn(
              "sticky top-0 z-10 grid items-center text-left",
              dsHeadRowClass,
              dsHeadCellClass,
              GRID_COLS
            )}
          >
            <div role="columnheader">№ раздела</div>
            <div role="columnheader">Работа из сметы</div>
            <div role="columnheader">Статья справочника СМР</div>
            <div role="columnheader" className="text-right">
              Score
            </div>
            <div role="columnheader">Статус</div>
          </div>
          <div
            style={{
              height: virtualizer.getTotalSize(),
              position: "relative",
            }}
          >
            {virtualizer.getVirtualItems().map((vi) => {
              const r = rows[vi.index]
              const decision = decisionFor(state, r)
              const contextRow =
                r.status === "excluded" || r.status === "pending"
              const clickable =
                onOpenRow !== undefined &&
                r.status !== "excluded" &&
                r.status !== "pending"
              // warning-рамка слева: только реально спорные строки (как в
              // старом ReviewRow) — requiresDecision уже исключает
              // excluded/pending, поэтому не пересекается с contextRow
              const flagged = requiresDecision(r)
              const label = statusLabel(r, decision)
              const chosenCode =
                decision.kind === "confirmed" ? decision.code : r.matched_code

              return (
                <div
                  key={r.row_number}
                  role="row"
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: ROW_H,
                    transform: `translateY(${vi.start}px)`,
                  }}
                  onClick={
                    clickable ? () => onOpenRow(r.row_number) : undefined
                  }
                  className={cn(
                    "grid items-center border-b px-4 text-sm",
                    dsHairline,
                    GRID_COLS,
                    clickable && "cursor-pointer hover:bg-muted/50",
                    flagged && "border-l-2 border-l-[var(--warning)]",
                    contextRow && "opacity-60"
                  )}
                >
                  <div role="cell" className="font-mono text-muted-foreground">
                    {r.section_code}
                  </div>
                  <div
                    role="cell"
                    className="line-clamp-2 text-[var(--ds-text-2)]"
                  >
                    {r.source_name}
                  </div>
                  <div role="cell">
                    {contextRow ? (
                      <span className="text-muted-foreground">—</span>
                    ) : isNoMatch(r, decision) ? (
                      <span className="text-muted-foreground">
                        — без пары —
                      </span>
                    ) : (
                      <span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {chosenCode}
                        </span>{" "}
                        {decision.kind === "confirmed"
                          ? decision.name
                          : r.matched_name}
                      </span>
                    )}
                  </div>
                  <div
                    role="cell"
                    className="text-right font-mono text-xs text-muted-foreground"
                  >
                    {r.status !== "no_match" &&
                    r.status !== "matched_fund" &&
                    !contextRow
                      ? r.score.toFixed(2)
                      : ""}
                  </div>
                  <div
                    role="cell"
                    className={"text-sm " + statusTone[r.status]}
                  >
                    {contextRow ? (
                      <Badge variant="outline">{label}</Badge>
                    ) : (
                      <>
                        {label === "Из фонда" && (
                          <Database className="mr-1 inline size-3" />
                        )}
                        {label}
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
