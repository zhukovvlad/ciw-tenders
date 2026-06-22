import { useState } from "react"
import { toast } from "sonner"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api/client"
import { importTemplate } from "@/lib/api/articles"
import type { ImportReport } from "@/lib/types"

export function TemplateUpload({ onApplied }: { onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportReport | null>(null)
  const [consent, setConsent] = useState(false)
  const [conflict, setConflict] = useState(false) // 409: состояние БД разошлось с превью
  const [busy, setBusy] = useState(false)

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    // смена файла сбрасывает предыдущее превью, согласие и флаг конфликта
    setPreview(null)
    setConsent(false)
    setConflict(false)
    setFile(f)
    if (!f) return
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось прочитать файл"
      )
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
        `Готово: создано ${res.created}, обновлено ${res.updated}, удалено ${res.deleted}, ` +
          `без изменений ${res.unchanged}, ожидают эмбеддинга ${res.pending_embeddings}.`
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
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось применить импорт"
      )
    } finally {
      setBusy(false)
    }
  }

  const applyDisabled = busy || !preview || (needsForce && !consent)

  return (
    <div className="text-sm">
      <Label htmlFor="tpl-file" className="text-xs text-[var(--ds-text-2)]">
        Файл шаблона (.xlsx)
      </Label>
      <Input
        id="tpl-file"
        type="file"
        accept=".xlsx"
        onChange={onPick}
        className="mt-1"
      />

      {busy && <p className="mt-2 text-muted-foreground">Обработка…</p>}

      {preview && (
        <div className="mt-3 rounded-md border border-[var(--ds-hairline)] p-3">
          <p>
            Создано {preview.created}, обновлено {preview.updated}, удалено{" "}
            {preview.deleted}, без изменений {preview.unchanged}, ожидают
            эмбеддинга {preview.pending_embeddings}.
          </p>
          {preview.skipped.length > 0 && (
            <Collapsible className="mt-2">
              <CollapsibleTrigger className="cursor-pointer text-xs text-muted-foreground">
                Пропущено строк: {preview.skipped.length}
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
                    ? "Состояние справочника изменилось с момента превью — для применения нужен принудительный режим."
                    : `Импорт удалит ${preview.deleted} строк (снос корня или большой доли). Это необратимо.`}
                </span>
                <div className="mt-1 flex items-center gap-2 text-xs">
                  <Checkbox
                    id="force-consent"
                    checked={consent}
                    onCheckedChange={(c) => setConsent(c === true)}
                  />
                  <Label htmlFor="force-consent">
                    Да, применить принудительно
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
            Применить
          </Button>
        </div>
      )}
    </div>
  )
}
