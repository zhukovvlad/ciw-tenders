// Тонкий клиент REST API бэкенда. В dev запросы /api проксируются Vite на :8000.

export interface Article {
  id: number
  article_code: string
  name: string
  section_name: string
}

export interface ArticleCreate {
  article_code: string
  name: string
  section_name: string
}

export interface Candidate {
  article_code: string
  name: string
  section_name: string
  score: number
}

export interface MatchResult {
  row_number: number
  source_name: string
  status: string
  score: number
  matched_code: string | null
  matched_name: string | null
  candidates: Candidate[]
}

const BASE = "/api"

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`Ошибка ${response.status}: ${detail}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  listArticles: (): Promise<Article[]> =>
    fetch(`${BASE}/articles`).then((r) => handle<Article[]>(r)),

  createArticle: (payload: ArticleCreate): Promise<Article> =>
    fetch(`${BASE}/articles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => handle<Article>(r)),

  deleteArticle: (id: number): Promise<void> =>
    fetch(`${BASE}/articles/${id}`, { method: "DELETE" }).then((r) => {
      if (!r.ok) throw new Error(`Ошибка ${r.status}`)
    }),

  matchEstimate: (file: File): Promise<MatchResult[]> => {
    const form = new FormData()
    form.append("file", file)
    return fetch(`${BASE}/estimates/match`, { method: "POST", body: form }).then((r) =>
      handle<MatchResult[]>(r),
    )
  },
}
