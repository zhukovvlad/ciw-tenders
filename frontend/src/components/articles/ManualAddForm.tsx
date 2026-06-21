import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { createArticle } from "@/lib/api/articles"

const EMPTY = { article_code: "", name: "", parent_code: "" }

export function ManualAddForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.article_code.trim() || !form.name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await createArticle({
        article_code: form.article_code.trim(),
        name: form.name.trim(),
        parent_code: form.parent_code.trim() || null,
      })
      setForm(EMPTY)
      onCreated()
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Не удалось добавить статью"
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="grid gap-3 sm:grid-cols-[160px_1fr_160px_auto]"
    >
      <label className="text-xs text-[var(--ds-text-2)]">
        Код
        <Input
          value={form.article_code}
          onChange={(e) => setForm({ ...form, article_code: e.target.value })}
          className="mt-1"
        />
      </label>
      <label className="text-xs text-[var(--ds-text-2)]">
        Наименование
        <Input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="mt-1"
        />
      </label>
      <label className="text-xs text-[var(--ds-text-2)]">
        Код родителя (необязательно)
        <Input
          value={form.parent_code}
          onChange={(e) => setForm({ ...form, parent_code: e.target.value })}
          className="mt-1"
        />
      </label>
      <Button type="submit" disabled={busy} className="self-end">
        <Plus className="size-4" />
        Добавить
      </Button>
      {error && (
        <p className="text-xs text-destructive sm:col-span-4">{error}</p>
      )}
    </form>
  )
}
