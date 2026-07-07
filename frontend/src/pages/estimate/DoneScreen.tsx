import { useRef, useState } from "react"
import { Link } from "react-router-dom"
import { Download } from "lucide-react"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import type { ReviewState } from "@/lib/types"
import { decisionFor, promotableCount } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"
import { Switch } from "@/components/ui/switch"
import { setReference } from "@/lib/api/estimates"
import { apiErrorText } from "@/lib/api/errorText"

interface DoneScreenProps {
  state: ReviewState
  onExport: () => void
  onResume: () => void
  estimateId: number | null
  isReference: boolean
  onReferenceChange?: (value: boolean) => void
}

export function DoneScreen({
  state,
  onExport,
  onResume,
  estimateId,
  isReference,
  onReferenceChange,
}: DoneScreenProps) {
  const { t } = useTranslation()
  const [inFund, setInFund] = useState(isReference)
  const toggleSeq = useRef(0)

  const matched = state.rows.filter(
    (r) => decisionFor(state, r).kind === "confirmed"
  ).length
  const noPair = state.rows.filter(
    (r) => decisionFor(state, r).kind === "no_match"
  ).length
  const promotable = promotableCount(state.rows)
  // 0 промоутабельных блокирует ТОЛЬКО включение — уже эталонная смета
  // (inFund=true) обязана оставаться снимаемой всегда (unreference — законная
  // операция независимо от текущего состава решений, см. reverse-флоу фонда)
  const blockedByEmpty = promotable === 0 && !inFund

  function handleToggleFund(next: boolean) {
    if (estimateId === null) {
      toast.error(t("estimates.fundUndetermined"))
      return
    }
    const seq = ++toggleSeq.current
    setInFund(next)
    setReference(estimateId, next)
      .then((r) => {
        if (seq !== toggleSeq.current) return
        setInFund(r.is_reference)
        onReferenceChange?.(r.is_reference)
        if (next && !r.is_reference && r.promoted === 0) {
          // бэк не ставит is_reference при 0 промоученных строк (toggle_reference) —
          // объясняем отщёлкивание, иначе тумблер выглядит сломанным
          toast.info(t("estimates.fundNoDecisions"))
        }
      })
      .catch((err: unknown) => {
        if (seq === toggleSeq.current) setInFund(!next)
        console.error(err)
        toast.error(apiErrorText(err, t, "estimates.fundUpdateFailed"))
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
            {t("review.matched")}
          </div>
        </div>
        <div>
          <div className="font-display text-4xl text-destructive">{noPair}</div>
          <div className="text-xs tracking-wide text-muted-foreground uppercase">
            {t("review.noMatch")}
          </div>
        </div>
      </div>
      <p className="mb-5 text-sm text-muted-foreground">
        {t("estimates.exportHint")}
      </p>
      <Button onClick={onExport}>
        <Download className="size-4" />
        {t("estimates.downloadXlsx")}
      </Button>
      <div className="mt-6 flex items-center justify-center gap-3 text-left">
        <span className="text-sm text-[var(--ds-text-2)]">
          {t("estimates.referenceToggle")}
        </span>
        <Switch
          checked={inFund}
          disabled={estimateId === null || blockedByEmpty}
          onCheckedChange={handleToggleFund}
          aria-label={t("estimates.referenceToggle")}
        />
      </div>
      {blockedByEmpty && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("estimates.fundHint")}
        </p>
      )}
      <div className="mt-4 flex flex-col items-center gap-2">
        <Button variant="outline" size="sm" onClick={onResume}>
          {t("estimates.resumeReview")}
        </Button>
        <Button variant="outline" size="sm" asChild>
          <Link to="?view=grid">{t("estimates.viewRows")}</Link>
        </Button>
        <Link to="/estimates" className="text-sm text-[var(--ds-accent-hover)]">
          {t("estimates.uploadNext")}
        </Link>
      </div>
    </div>
  )
}
