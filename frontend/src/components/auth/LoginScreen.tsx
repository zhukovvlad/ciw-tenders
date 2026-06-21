import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/useAuth"

export function LoginScreen() {
  const { login } = useAuth()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Неверный логин или пароль"
          : "Не удалось войти, попробуйте позже",
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-1 bg-background">
      <div className="font-display text-2xl">
        MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
      </div>
      <div className="mb-5 text-xs text-muted-foreground">Автоматизатор строительных смет</div>
      <form onSubmit={submit} className="flex w-60 flex-col gap-3">
        <label className="text-xs text-[var(--ds-text-2)]">
          Логин
          <Input value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1" />
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
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button type="submit" disabled={busy}>
          Войти
        </Button>
      </form>
    </div>
  )
}
