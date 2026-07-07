import { useState } from "react"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Label } from "@/components/ui/label"
import { Dropzone } from "@/components/Dropzone"
import { ApiError } from "@/lib/api/client"
import { apiErrorText } from "@/lib/api/errorText"
import { importTemplate } from "@/lib/api/articles"
import type { ImportReport } from "@/lib/types"

export function TemplateUpload({ onApplied }: { onApplied: () => void }) {
  const { t } = useTranslation()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportReport | null>(null)
  const [consent, setConsent] = useState(false)
  const [conflict, setConflict] = useState(false) // 409: состояние БД разошлось с превью
  const [busy, setBusy] = useState(false)

  async function onPick(f: File) {
    // смена файла сбрасывает предыдущее превью, согласие и флаг конфликта
    setPreview(null)
    setConsent(false)
    setConflict(false)
    setFile(f)
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      toast.error(apiErrorText(err, t, "articles.readFailed"))
    } finally {
      setBusy(false)
    }
  }

  // force требуется, если план превью просит его ИЛИ применение упёрлось в 409-дрейф
  const needsForce = !!preview && (preview.force_required || conflict)

  async function apply() {
    if (busy) return
    if (!file || !preview) return
    setBusy(true)
    try {
      const res = await importTemplate(file, {
        dryRun: false,
        force: needsForce,
      })
      toast.success(
        t("articles.importDone", {
          created: res.created,
          updated: res.updated,
          deleted: res.deleted,
          unchanged: res.unchanged,
          pending: res.pending_embeddings,
        })
      )
      setPreview(null)
      setConsent(false)
      setConflict(false)
      onApplied()
    } catch (err) {
      // 409: состояние БД изменилось между превью и применением — поднимаем согласие на force.
      if (err instanceof ApiError && err.status === 409) {
        setConflict(true)
        setConsent(false)
      }
      toast.error(apiErrorText(err, t, "articles.applyFailed"))
    } finally {
      setBusy(false)
    }
  }

  const applyDisabled = busy || !preview || (needsForce && !consent)

  return (
    <div className="text-sm">
      <Dropzone
        onFile={onPick}
        accept=".xlsx"
        id="tpl-file"
        ariaLabel={t("articles.fileLabel")}
        idleText={t("articles.dropIdle")}
        hint={t("articles.hint")}
        disabled={busy}
      />
      {file && (
        <p className="mt-2 text-xs text-muted-foreground">
          {t("articles.fileName", { name: file.name })}
        </p>
      )}

      {busy && (
        <p className="mt-2 text-muted-foreground">{t("articles.processing")}</p>
      )}

      {preview && (
        <div className="mt-3 rounded-md border border-[var(--ds-hairline)] p-3">
          <p>
            {t("articles.previewSummary", {
              created: preview.created,
              updated: preview.updated,
              deleted: preview.deleted,
              unchanged: preview.unchanged,
              pending: preview.pending_embeddings,
            })}
          </p>
          {preview.skipped.length > 0 && (
            <Collapsible className="mt-2">
              <CollapsibleTrigger className="cursor-pointer text-xs text-muted-foreground">
                {t("articles.skipped", { n: preview.skipped.length })}
              </CollapsibleTrigger>
              <CollapsibleContent>
                <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted-foreground">
                  {preview.skipped.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </CollapsibleContent>
            </Collapsible>
          )}
          {needsForce && (
            <Alert variant="destructive" className="mt-2">
              <AlertDescription>
                <span>
                  {conflict && !preview.force_required
                    ? t("articles.staleForce")
                    : t("articles.forceConfirmBody", {
                        count: preview.deleted,
                      })}
                </span>
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <Checkbox
                    id="force-consent"
                    checked={consent}
                    onCheckedChange={(c) => setConsent(c === true)}
                  />
                  <Label htmlFor="force-consent">
                    {t("articles.applyForce")}
                  </Label>
                </div>
              </AlertDescription>
            </Alert>
          )}
          <Button
            onClick={() => void apply()}
            disabled={applyDisabled}
            className="mt-3"
          >
            {t("articles.apply")}
          </Button>
        </div>
      )}
    </div>
  )
}
