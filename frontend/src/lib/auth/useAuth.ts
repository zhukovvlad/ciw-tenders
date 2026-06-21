import { createContext, useContext } from "react"
import type { AuthUser } from "@/lib/types"

export interface AuthContextValue {
  user: AuthUser | null
  role: "user" | "admin" | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth вызван вне AuthProvider")
  return ctx
}
