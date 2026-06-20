import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { login } from "@/lib/mock/auth"

interface LoginScreenProps {
  onSuccess: () => void
}

export function LoginScreen({ onSuccess }: LoginScreenProps) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState(false)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(false)
    try {
      const ok = await login(email, password)
      if (ok) onSuccess()
      else setError(true)
    } catch {
      setError(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
      </div>
      <div className="mb-5 text-xs text-muted-foreground">
        Автоматизатор строительных смет
      </div>
      <form onSubmit={submit} className="flex w-60 flex-col gap-3">
        <label className="text-xs text-[var(--ds-text-2)]">
          Логин
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1"
          />
        </label>
        <label className="text-xs text-[var(--ds-text-2)]">
          Пароль
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1"
          />
        </label>
        {error && (
          <p className="text-xs text-destructive">Неверный логин или пароль</p>
        )}
        <Button type="submit" disabled={busy}>
          Войти
        </Button>
      </form>
    </div>
  )
}
