// Полоса контекста под карточкой (спека §3b): ±2 соседних узла по source_index
// среди ВСЕХ строк (excluded — приглушённые). Не виртуализируется — окно
// константного размера (спека §5).
import { useTranslation } from "react-i18next"
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

// Присвоенный сосед: код статьи (моноширинно) — сигнал «ушёл вон куда»; полное
// имя в title. Однородный раздел иначе повторял бы длинный хвост имени в каждой
// строке и весил больше кандидатов (спека 3.6 §2 п.3). Осознанный trade-off:
// title недоступен с клавиатуры/тача — для сигнала соседства кода достаточно.
// Неприсвоенные соседи — статусная подпись без изменений.
// (форму Decision.confirmed сверять по lib/types.ts, не выдумывать поля)
function rightSide(
  state: ReviewState,
  r: MatchRow
): { text: string; title?: string; mono?: boolean } {
  const d = decisionFor(state, r)
  if (d.kind === "confirmed")
    return { text: d.code, title: `${d.code} ${d.name}`, mono: true }
  return { text: statusLabel(r, d) }
}

export function ContextStrip({
  state,
  activeRowNumber,
  onNavigate,
}: {
  state: ReviewState
  activeRowNumber: number
  // Скраббер (спека фичи 2): клик по строке делает её активной. Проп
  // опциональный — без него полоса остаётся чистой справкой, как была.
  onNavigate?: (rowNumber: number) => void
}) {
  const { t } = useTranslation()
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
        {t("review.envInEstimate")}
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
        const rs = rightSide(state, r)
        const isActive = r.row_number === activeRowNumber
        // Кликабельны те же строки, что в гриде: excluded/pending — контекст,
        // не решения. Активная не кликабельна: клик по себе — no-op.
        const clickable = onNavigate !== undefined && !muted && !isActive
        const rowClass = cn(
          "flex w-full items-center gap-2 border-l-2 border-transparent px-3 py-1.5 text-left",
          isActive &&
            "border-primary bg-[color-mix(in_srgb,var(--primary)_8%,transparent)]",
          muted && "opacity-60",
          openers[g] && "font-medium",
          // Аффорданс — словарь ГРИДА, не рамка кандидата: в покое полоса
          // остаётся утопленной справкой, интерактивность проявляется только
          // на hover (иначе вернулась бы проблема «полоса читается как
          // кандидаты», этап 3.6). focus-visible — по конвенции ui/button.
          clickable &&
            "cursor-pointer outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
        )
        const inner = (
          <>
            <span className="font-mono text-muted-foreground">
              {r.section_code}
            </span>
            <span
              className={cn(
                "truncate",
                // Вторая ось открывашки (спека §2 решение #6): опускаем фон —
                // рядовой сосед (не активная, не открывашка) приглушается, а
                // открывашка остаётся на полном тоне + font-medium. Её классы
                // не трогаются, изгородь 3.5 цела.
                // excluded/pending исключены (спека §2 решение #6 финал): у
                // них своя ось «тихо» — opacity-60; тон был бы двойным
                // кодированием и риском двойного затухания на sunken.
                !openers[g] && !isActive && !muted && "text-[var(--ds-text-2)]"
              )}
            >
              {r.source_name}
            </span>
            {isActive ? (
              // статус активной дублировал бы решаемое прямо сейчас (спека 3.5 §2)
              <ArrowLeft
                aria-label={t("review.youAreHere")}
                className="ml-auto size-3 shrink-0 text-primary"
              />
            ) : (
              <span
                title={rs.title}
                className={cn(
                  "ml-auto shrink-0 text-muted-foreground",
                  rs.mono && "font-mono"
                )}
              >
                → {t(rs.text)}
              </span>
            )}
          </>
        )
        return (
          <div key={r.row_number}>
            {divider && (
              <div
                data-testid="section-boundary"
                className="border-t-2 border-[var(--ds-border-strong)]"
              >
                {label && (
                  <div className="px-3 pt-1 text-[11px] tracking-wide text-muted-foreground uppercase">
                    {t("review.section", { label })}
                  </div>
                )}
              </div>
            )}
            {clickable ? (
              <button
                type="button"
                data-row
                data-opener={openers[g] || undefined}
                onClick={() => onNavigate(r.row_number)}
                className={rowClass}
              >
                {inner}
              </button>
            ) : (
              <div
                data-row
                data-opener={openers[g] || undefined}
                data-active={isActive || undefined}
                className={rowClass}
              >
                {inner}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
