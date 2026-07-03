import { afterEach, describe, expect, it, vi } from "vitest"
import * as client from "./client"
import {
  createArticle,
  deleteAllArticles,
  deleteArticle,
  importTemplate,
  listArticles,
  searchArticles,
} from "./articles"

afterEach(() => vi.restoreAllMocks())

describe("articles api", () => {
  it("listArticles тянет с limit=1000", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue([])
    await listArticles()
    expect(spy).toHaveBeenCalledWith("/articles?limit=1000")
  })

  it("createArticle шлёт POST с телом", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue({ id: 1 })
    await createArticle({ article_code: "1.1", name: "n", parent_code: "1" })
    expect(spy).toHaveBeenCalledWith("POST", "/articles", {
      article_code: "1.1",
      name: "n",
      parent_code: "1",
    })
  })

  it("deleteAllArticles возвращает число", async () => {
    vi.spyOn(client, "apiSend").mockResolvedValue({ deleted: 7 })
    expect(await deleteAllArticles()).toBe(7)
  })

  it("deleteArticle шлёт DELETE по id", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await deleteArticle(42)
    expect(spy).toHaveBeenCalledWith("DELETE", "/articles/42")
  })

  it("importTemplate кодирует dry_run/force в query", async () => {
    const spy = vi.spyOn(client, "apiUpload").mockResolvedValue({} as never)
    const file = new File(["x"], "t.xlsx")
    await importTemplate(file, { dryRun: true, force: false })
    expect(spy).toHaveBeenCalledWith(
      "/articles/import?dry_run=true&force=false",
      file
    )
  })

  it("searchArticles мапит breadcrumb из ответа (?? [] для старого бэка)", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 3, code: "03.04", name: "Фунд.", breadcrumb: ["03 Фундаменты"] },
      { id: 4, code: "03.05", name: "Без крошки" },
    ])
    const result = await searchArticles("фунд")
    expect(result[0].breadcrumb).toEqual(["03 Фундаменты"])
    expect(result[1].breadcrumb).toEqual([])
  })
})
