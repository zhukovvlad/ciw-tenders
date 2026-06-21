import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ApiError } from "@/lib/api/client"
import { importTemplate } from "@/lib/api/articles"
import type { ImportReport } from "@/lib/types"

export function TemplateUpload({ onApplied }: { onApplied: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportReport | null>(null)
  const [consent, setConsent] = useState(false)
  const [conflict, setConflict] = useState(false) // 409: состояние БД разошлось с превью
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [doneMsg, setDoneMsg] = useState<string | null>(null)

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    // смена файла сбрасывает предыдущее превью, согласие и флаг конфликта
    setPreview(null)
    setConsent(false)
    setConflict(false)
    setError(null)
    setDoneMsg(null)
    setFile(f)
    if (!f) return
    setBusy(true)
    try {
      setPreview(await importTemplate(f, { dryRun: true, force: false }))
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Не удалось прочитать файл"
      )
    } finally {
      setBusy(false)
    }
  }

  // force требуется, если план превью просит его ИЛИ применение упёрлось в 409-дрейф
  const needsForce = !!preview && (preview.force_required || conflict)

  async function apply() {
    if (!file || !preview) return
    setBusy(true)
    setError(null)
    try {
      const res = await importTemplate(file, {
        dryRun: false,
        force: needsForce,
      })
      setDoneMsg(
        `Готово: создано ${res.created}, обновлено ${res.updated}, удалено ${res.deleted}, ` +
          `без изменений ${res.unchanged}, ожидают эмбеддинга ${res.pending_embeddings}.`
      )
      setPreview(null)
      setConsent(false)
      setConflict(false)
      onApplied()
    } catch (err) {
      // 409: состояние БД изменилось между превью и применением — поднимаем согласие на force,
      // не оставляя пользователя в тупике с устаревшим force_required=false.
      if (err instanceof ApiError && err.status === 409) {
        setConflict(true)
        setConsent(false)
      }
      setError(
        err instanceof ApiError ? err.message : "Не удалось применить импорт"
      )
    } finally {
      setBusy(false)
    }
  }

  const applyDisabled = busy || !preview || (needsForce && !consent)

  return (
    <div className="text-sm">
      <label className="text-xs text-[var(--ds-text-2)]">
        Файл шаблона (.xlsx)
        <input
          type="file"
          accept=".xlsx"
          onChange={onPick}
          className="mt-1 block text-xs"
        />
      </label>

      {busy && <p className="mt-2 text-muted-foreground">Обработка…</p>}

      {preview && (
        <div className="mt-3 rounded-md border border-[var(--ds-hairline)] p-3">
          <p>
            Создано {preview.created}, обновлено {preview.updated}, удалено{" "}
            {preview.deleted}, без изменений {preview.unchanged}, ожидают
            эмбеддинга {preview.pending_embeddings}.
          </p>
          {preview.skipped.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Пропущено строк: {preview.skipped.length}
              </summary>
              <ul className="mt-1 max-h-40 overflow-auto text-xs text-muted-foreground">
                {preview.skipped.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </details>
          )}
          {needsForce && (
            <div className="mt-2 rounded bg-destructive/10 p-2 text-destructive">
              <p className="text-xs">
                {conflict && !preview.force_required
                  ? "Состояние справочника изменилось с момента превью — для применения нужен принудительный режим."
                  : `Импорт удалит ${preview.deleted} строк (снос корня или большой доли). Это необратимо.`}
              </p>
              <label className="mt-1 flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                Да, применить принудительно
              </label>
            </div>
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

      {doneMsg && <p className="mt-2 text-foreground">{doneMsg}</p>}
      {error && <p className="mt-2 text-destructive">{error}</p>}
    </div>
  )
}
