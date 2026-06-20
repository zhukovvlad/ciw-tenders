import type { Progress } from "@/lib/mock/api"

interface ProcessingScreenProps {
  progress: Progress
  fileName: string
}

const PHASES: { key: Progress["phase"]; label: string }[] = [
  { key: "parsing", label: "Отбор строк СМР" },
  { key: "embedding", label: "Векторизация" },
  { key: "matching", label: "Поиск + LLM-арбитр" },
]
const order: Progress["phase"][] = ["parsing", "embedding", "matching", "done"]

export function ProcessingScreen({
  progress,
  fileName,
}: ProcessingScreenProps) {
  const curIdx = order.indexOf(progress.phase)
  return (
    <div className="mx-auto max-w-md p-10">
      <div className="mb-6 text-sm">{fileName}</div>
      {PHASES.map((ph) => {
        const phIdx = order.indexOf(ph.key)
        const done = phIdx < curIdx
        const active = ph.key === progress.phase
        const pct = done
          ? 100
          : active
            ? (progress.total === 0 ? 0 : Math.round((progress.done / progress.total) * 100))
            : 0
        return (
          <div key={ph.key} className="mb-3">
            <div className="mb-1 text-xs tracking-wide text-muted-foreground uppercase">
              {done ? "✓ " : ""}
              {ph.label}
              {active ? ` · ${progress.done}/${progress.total}` : ""}
            </div>
            <div className="h-1.5 overflow-hidden rounded bg-secondary">
              <div
                className="h-1.5 bg-primary transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )
      })}
      {progress.etaSeconds !== null && progress.phase === "matching" && (
        <div className="mt-3 font-mono text-xs text-muted-foreground">
          ≈ {Math.ceil(progress.etaSeconds)} сек осталось
        </div>
      )}
    </div>
  )
}
