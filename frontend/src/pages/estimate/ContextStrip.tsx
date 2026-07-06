// Полоса контекста под карточкой (спека §3b): ±2 соседних узла по source_index
// среди ВСЕХ строк (excluded — приглушённые). Не виртуализируется — окно
// константного размера (спека §5).
import type { MatchRow, ReviewState } from "@/lib/types"
import { decisionFor, statusLabel } from "@/lib/reviewState"
import { cn } from "@/lib/utils"
import { dsHairline } from "@/components/common/ds-table"
import { ArrowLeft } from "lucide-react"

const WINDOW = 2

// Открывашка — структурный предикат по крошке СЛЕДУЮЩЕЙ строки, НЕ по статусу
// (excluded — не детектор заголовка: WORK-заголовки матчатся; спека 3.5 §2).
// Равенства достаточно, prefix-сравнение не нужно: nearest-persisted-резолв
// не порождает неперсистированных уровней в крошке — у первого
// персистированного потомка X путь равен X.breadcrumb + [X.name] ТОЧНО.
function isOpener(r: MatchRow, next: MatchRow | undefined): boolean {
  if (!next) return false
  if (next.breadcrumb.length !== r.breadcrumb.length + 1) return false
  return (
    next.breadcrumb[r.breadcrumb.length] === r.source_name &&
    r.breadcrumb.every((name, k) => name === next.breadcrumb[k])
  )
}

function pathsEqual(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((x, k) => x === b[k])
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
  const openers = ordered.map((r, g) => isOpener(r, ordered[g + 1]))
  // Эффективный путь (спека §4 п.1): открывашка живёт в разделе, который открывает.
  const paths = ordered.map((r, g) =>
    openers[g] ? [...r.breadcrumb, r.source_name] : r.breadcrumb
  )
  const start = Math.max(0, i - WINDOW)
  const win = ordered.slice(start, i + WINDOW + 1)
  return (
    <div
      className={cn(
        "mb-4 rounded-md border bg-[var(--ds-surface-sunken)] text-xs",
        dsHairline
      )}
    >
      {/* Подпись справочной панели (спека 3.6 §2 п.2): тот же типографический
          словарь, что подпись разделителя «Раздел — …» ниже. */}
      <div className="px-3 pt-2 pb-1 text-[11px] tracking-wide text-muted-foreground uppercase">
        Окружение в смете
      </div>
      {win.map((r, j) => {
        const g = start + j
        const boundary = j > 0 && !pathsEqual(paths[g - 1], paths[g])
        // §4 п.3: перед открывашкой разделитель подавлен — заголовок объявляет
        // себя сам (стилизация — Task 8, вторая половина правила).
        const divider = boundary && !openers[g]
        // Последний уровень нового эффективного пути; пустой путь (граница к
        // корню, «путь укоротился») — разделитель без подписи.
        const label = paths[g][paths[g].length - 1]
        const muted = r.status === "excluded" || r.status === "pending"
        return (
          <div key={r.row_number}>
            {divider && (
              <div
                data-testid="section-boundary"
                className="border-t-2 border-[var(--ds-border-strong)]"
              >
                {label && (
                  <div className="px-3 pt-1 text-[11px] tracking-wide text-muted-foreground uppercase">
                    Раздел — {label}
                  </div>
                )}
              </div>
            )}
            <div
              data-row
              data-opener={openers[g] || undefined}
              data-active={r.row_number === activeRowNumber || undefined}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5",
                r.row_number === activeRowNumber &&
                  "bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]",
                muted && "opacity-60",
                openers[g] && "font-medium"
              )}
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
