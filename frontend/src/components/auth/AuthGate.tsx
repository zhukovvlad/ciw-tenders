import { useAuth } from "@/lib/auth/AuthContext"
import { LoginScreen } from "@/components/auth/LoginScreen"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading)
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        Загрузка…
      </div>
    )
  if (!user) return <LoginScreen />
  return <>{children}</>
}
