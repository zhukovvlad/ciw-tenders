export const AUTH_KEY = "ciw.auth.v1"

export async function login(email: string, password: string): Promise<boolean> {
  await new Promise((r) => setTimeout(r, 150))
  if (email.trim() && password.trim()) {
    localStorage.setItem(AUTH_KEY, "mock-token")
    return true
  }
  return false
}

export function isAuthed(): boolean {
  return Boolean(localStorage.getItem(AUTH_KEY))
}

export function logout(): void {
  localStorage.removeItem(AUTH_KEY)
}
