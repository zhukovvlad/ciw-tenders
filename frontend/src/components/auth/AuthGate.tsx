import { useTranslation } from "react-i18next"
import { useAuth } from "@/lib/auth/useAuth"
import { LoginScreen } from "@/components/auth/LoginScreen"

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  const { t } = useTranslation()
  if (loading)
    return (
      <div className="flex min-h-svh items-center justify-center text-sm text-muted-foreground">
        {t("common.loading")}
      </div>
    )
  if (!user) return <LoginScreen />
  return <>{children}</>
}
