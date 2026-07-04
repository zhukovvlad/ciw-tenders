// Полоса контекста под карточкой (спека §3b): ±2 соседних узла по source_index
// среди ВСЕХ строк (excluded — приглушённые). Не виртуализируется — окно
// константного размера (спека §5).
import type { MatchRow, ReviewState } from "@/lib/types"
import { decisionFor, statusLabel } from "@/lib/reviewState"
import { cn } from "@/lib/utils"
import { dsHairline } from "@/components/common/ds-table"
import { ArrowLeft } from "lucide-react"

const WINDOW = 2

function topSection(r: MatchRow): string {
  return r.breadcrumb[0] ?? r.source_name
}

function rightSide(state: ReviewState, r: MatchRow): string {
  // форма Decision сверена по types.ts: confirmed-вариант несёт code/name
  // (при изменении Decision сверь по lib/types.ts, не выдумывай поля)
  const d = decisionFor(state, r)
  if (d.kind === "confirmed") return `${d.code} ${d.name}`
  return statusLabel(r, d)
}

export function ContextStrip({
  state,
  activeRowNumber,
}: {
  state: ReviewState
  activeRowNumber: number
}) {
  const ordered = [...state.rows].sort((a, b) => a.sourceIndex - b.sourceIndex)
  const i = ordered.findIndex((r) => r.row_number === activeRowNumber)
  if (i === -1) return null
  const win = ordered.slice(Math.max(0, i - WINDOW), i + WINDOW + 1)
  return (
    <div className={cn("rounded-md border text-xs", dsHairline)}>
      {win.map((r, j) => {
        const boundary = j > 0 && topSection(win[j - 1]) !== topSection(r)
        const muted = r.status === "excluded" || r.status === "pending"
        return (
          <div key={r.row_number}>
            {boundary && (
              <div
                data-testid="section-boundary"
                className="border-t-2 border-[var(--ds-border-strong)]"
              />
            )}
            <div
              data-row
              data-active={r.row_number === activeRowNumber || undefined}
              className={
                "flex items-center gap-2 px-3 py-1.5 " +
                (r.row_number === activeRowNumber
                  ? "bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]"
                  : "") +
                (muted ? " opacity-60" : "")
              }
            >
              <span className="font-mono text-muted-foreground">
                {r.section_code}
              </span>
              <span className="truncate">{r.source_name}</span>
              {r.row_number === activeRowNumber ? (
                // статус активной дублировал бы решаемое прямо сейчас (спека 3.5 §2)
                <ArrowLeft
                  aria-label="вы здесь"
                  className="ml-auto size-3 shrink-0 text-primary"
                />
              ) : (
                <span className="ml-auto shrink-0 text-muted-foreground">
                  → {rightSide(state, r)}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
