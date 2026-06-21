import type { AuthUser } from "@/lib/types"
import { apiGet, apiSend } from "./client"

export function login(email: string, password: string): Promise<string> {
  return apiSend<{ access_token: string }>("POST", "/auth/login", { email, password }).then(
    (r) => r.access_token,
  )
}

export function me(): Promise<AuthUser> {
  return apiGet<AuthUser>("/auth/me")
}
