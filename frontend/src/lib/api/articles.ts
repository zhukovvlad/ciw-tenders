import type { Article, ImportReport } from "@/lib/types"
import { apiGet, apiSend, apiUpload } from "./client"

export function listArticles(): Promise<Article[]> {
  return apiGet<Article[]>("/articles?limit=1000")
}

export function createArticle(input: {
  article_code: string
  name: string
  parent_code?: string | null
}): Promise<Article> {
  return apiSend<Article>("POST", "/articles", input)
}

export function deleteArticle(id: number): Promise<void> {
  return apiSend<void>("DELETE", `/articles/${id}`)
}

export function deleteAllArticles(): Promise<number> {
  return apiSend<{ deleted: number }>("DELETE", "/articles").then(
    (r) => r.deleted
  )
}

export function importTemplate(
  file: File,
  opts: { dryRun: boolean; force: boolean }
): Promise<ImportReport> {
  return apiUpload<ImportReport>(
    `/articles/import?dry_run=${opts.dryRun}&force=${opts.force}`,
    file
  )
}
