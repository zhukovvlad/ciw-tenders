import { useState } from "react"
import { isAuthed } from "@/lib/mock/auth"
import { LoginScreen } from "@/components/auth/LoginScreen"

interface AuthGateProps { children: React.ReactNode }

export function AuthGate({ children }: AuthGateProps) {
  const [authed, setAuthed] = useState(isAuthed())
  if (!authed) return <LoginScreen onSuccess={() => setAuthed(true)} />
  return <>{children}</>
}
