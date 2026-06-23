export const AUTH_TOKEN_KEY = "ciw.auth.token"

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = "ApiError"
  }
}

let onUnauthorized: (() => void) | null = null
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorized = cb
}

function authHeaders(): Record<string, string> {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError(0, "Сеть недоступна — проверьте подключение")
  }
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = (await res.json()) as { detail?: unknown }
      const detail = body?.detail
      if (typeof detail === "string") message = detail
      else if (
        detail &&
        typeof (detail as { message?: unknown }).message === "string"
      )
        message = (detail as { message: string }).message
    } catch {
      // тело не JSON — оставляем statusText
    }
    // 401 = протухшая сессия → разлогин; но неверный логин (/auth/login) — НЕ сессия, не разлогиниваем
    if (res.status === 401 && !path.startsWith("/auth/login"))
      onUnauthorized?.()
    throw new ApiError(res.status, message)
  }
  return res
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await request(path, { headers: { ...authHeaders() } })
  return res.json() as Promise<T>
}

export async function apiSend<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const res = await request(path, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// Бинарная загрузка (напр. экспорт .xlsx) через общий request — токен и обработка
// ошибок (ApiError) централизованы здесь, как требует auth-storage-контракт.
export async function apiGetBlob(path: string): Promise<Blob> {
  const res = await request(path, { headers: { ...authHeaders() } })
  return res.blob()
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append("file", file)
  // Content-Type НЕ ставим — браузер сам выставит multipart boundary.
  const res = await request(path, {
    method: "POST",
    headers: { ...authHeaders() },
    body: form,
  })
  return res.json() as Promise<T>
}
