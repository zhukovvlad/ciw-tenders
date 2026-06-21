import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { deleteAllArticles } from "@/lib/api/articles"

const CONFIRM_WORD = "УДАЛИТЬ"

export function WipeCatalog({ onWiped }: { onWiped: () => void }) {
  const [word, setWord] = useState("")
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function wipe() {
    setBusy(true)
    setError(null)
    setMsg(null)
    try {
      const n = await deleteAllArticles()
      setMsg(`Удалено ${n}`)
      setWord("")
      onWiped()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не удалось очистить справочник")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        Полностью удалит все статьи. Введите «{CONFIRM_WORD}», чтобы подтвердить.
      </p>
      <div className="flex items-center gap-2">
        <label className="sr-only" htmlFor="wipe-confirm">
          Подтверждение
        </label>
        <Input
          id="wipe-confirm"
          value={word}
          onChange={(e) => setWord(e.target.value)}
          placeholder={CONFIRM_WORD}
          className="max-w-[160px]"
        />
        <Button
          variant="destructive"
          disabled={busy || word !== CONFIRM_WORD}
          onClick={() => void wipe()}
        >
          Очистить справочник
        </Button>
      </div>
      {msg && <p className="mt-2 text-foreground">{msg}</p>}
      {error && <p className="mt-2 text-destructive">{error}</p>}
    </div>
  )
}
