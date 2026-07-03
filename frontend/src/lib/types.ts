export type MatchStatus =
  | "pending" // матчинг ещё не завершён
  | "excluded" // орг-заголовок: контекст, НЕ решается в ревью
  | "confident"
  | "needs_review"
  | "no_match"
  | "error"
  | "matched_fund"
export type ReviewStatus =
  | "unreviewed"
  | "confirmed"
  | "overridden"
  | "rejected"

export interface Candidate {
  id: number | null
  article_code: string
  name: string
  score: number
  breadcrumb: string[]
}

export interface MatchRow {
  row_number: number // ← row.id из бэка (идентичность строки: key/навигация/PATCH)
  section_code: string // ← row.code: «№ раздела» из сметы (для показа в UI)
  source_name: string // ← row.name
  sourceIndex: number // порядок исходного документа (полоса контекста, PR-B)
  breadcrumb: string[] // ПОЛНАЯ цепочка предков (включая org) — крошка карточки
  matchError: string | null // текст ошибки для status="error"
  status: MatchStatus
  score: number
  matched_code: string | null
  matched_name: string | null
  matched_article_id: number | null
  matchedBreadcrumb: string[]
  candidates: Candidate[]
  review_status: ReviewStatus
  final_article_id: number | null
  finalBreadcrumb: string[] // крошка статьи решения (выбор из поиска ≠ кандидаты)
  final_code: string | null
  final_name: string | null
}

export type Decision =
  | { kind: "pending" }
  | { kind: "confirmed"; code: string; name: string; manual: boolean }
  | { kind: "no_match" }

export interface ReviewState {
  fileName: string
  rows: MatchRow[]
  decisions: Record<number, Decision>
  filter: "all" | "review" | "no_match"
}

export interface Article {
  id: number
  article_code: string
  name: string
  parent_id: number | null
}

export interface AuthUser {
  id: number
  email: string
  role: "user" | "admin"
  is_active: boolean
}

export interface ImportReport {
  created: number
  updated: number
  deleted: number
  unchanged: number
  skipped: string[]
  pending_embeddings: number
  dry_run: boolean
  force_required: boolean
}

export interface StructuralAnomaly {
  kind: string
  sourceIndex: number
  code: string
  name: string
  detail: string
}
