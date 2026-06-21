import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiGet, apiSend, apiUpload, AUTH_TOKEN_KEY, setOnUnauthorized } from "./client"

function mockFetch(status: number, body: unknown, ok = status < 400) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    statusText: "x",
    json: async () => body,
  } as Response)
}

afterEach(() => {
  sessionStorage.clear()
  setOnUnauthorized(null)
  vi.restoreAllMocks()
})

describe("api client", () => {
  it("apiGet шлёт Bearer-токен и парсит JSON", async () => {
    sessionStorage.setItem(AUTH_TOKEN_KEY, "tok")
    const f = mockFetch(200, [{ id: 1 }])
    vi.stubGlobal("fetch", f)
    const out = await apiGet<{ id: number }[]>("/articles")
    expect(out).toEqual([{ id: 1 }])
    const [url, init] = f.mock.calls[0]
    expect(url).toBe("/api/articles")
    expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer tok" })
  })

  it("на 401 зовёт onUnauthorized и бросает ApiError", async () => {
    vi.stubGlobal("fetch", mockFetch(401, { detail: "no" }, false))
    const onUnauth = vi.fn()
    setOnUnauthorized(onUnauth)
    await expect(apiSend("POST", "/x", {})).rejects.toBeInstanceOf(ApiError)
    expect(onUnauth).toHaveBeenCalledOnce()
  })

  it("вытягивает detail.message из тела 409", async () => {
    vi.stubGlobal("fetch", mockFetch(409, { detail: { message: "конфликт", deleted: 3 } }, false))
    await expect(apiSend("POST", "/x", {})).rejects.toMatchObject({ status: 409, message: "конфликт" })
  })

  it("сетевой сбой → ApiError(0)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")))
    await expect(apiGet("/x")).rejects.toMatchObject({ status: 0 })
  })

  it("apiUpload шлёт FormData без ручного Content-Type", async () => {
    const f = mockFetch(200, { created: 1 })
    vi.stubGlobal("fetch", f)
    await apiUpload("/articles/import?dry_run=true&force=false", new File(["x"], "t.xlsx"))
    const [, init] = f.mock.calls[0]
    const headers = (init as RequestInit).headers as Record<string, string>
    expect(headers["Content-Type"]).toBeUndefined()
    expect((init as RequestInit).body).toBeInstanceOf(FormData)
  })
})
