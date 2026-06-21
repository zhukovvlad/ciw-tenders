import { useCallback, useEffect, useState } from "react"
import { ApiError, AUTH_TOKEN_KEY, setOnUnauthorized } from "@/lib/api/client"
import * as authApi from "@/lib/api/auth"
import type { AuthUser } from "@/lib/types"
import { AuthContext } from "@/lib/auth/useAuth"

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(
    () => !!sessionStorage.getItem(AUTH_TOKEN_KEY)
  )
  const [error, setError] = useState<string | null>(null)

  const logout = useCallback(() => {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    setOnUnauthorized(logout)
    return () => setOnUnauthorized(null)
  }, [logout])

  useEffect(() => {
    const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
    if (!token) return
    let cancelled = false
    authApi
      .me()
      .then((u) => {
        if (!cancelled) setUser(u)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 401) logout()
        else setError("Бэкенд недоступен — попробуйте позже")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    setError(null)
    const token = await authApi.login(email, password)
    sessionStorage.setItem(AUTH_TOKEN_KEY, token)
    setUser(await authApi.me())
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, role: user?.role ?? null, loading, error, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}
