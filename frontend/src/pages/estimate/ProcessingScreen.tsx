import { useTranslation } from "react-i18next"
import type { Progress } from "@/lib/mock/api"

interface ProcessingScreenProps {
  progress: Progress
  fileName: string
}

const PHASES: { key: Progress["phase"]; labelKey: string }[] = [
  { key: "parsing", labelKey: "estimates.stepSelect" },
  { key: "embedding", labelKey: "estimates.stepVectorize" },
  { key: "matching", labelKey: "estimates.stepMatch" },
]
const order: Progress["phase"][] = ["parsing", "embedding", "matching", "done"]

export function ProcessingScreen({
  progress,
  fileName,
}: ProcessingScreenProps) {
  const { t } = useTranslation()
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
            ? progress.total === 0
              ? 0
              : Math.round((progress.done / progress.total) * 100)
            : 0
        return (
          <div key={ph.key} className="mb-3">
            <div className="mb-1 text-xs tracking-wide text-muted-foreground uppercase">
              {done ? "✓ " : ""}
              {t(ph.labelKey)}
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
          {t("estimates.etaLeft", { sec: Math.ceil(progress.etaSeconds) })}
        </div>
      )}
    </div>
  )
}
