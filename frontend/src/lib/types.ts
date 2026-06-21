export type MatchStatus = "confident" | "needs_review" | "no_match"

export interface Candidate {
  article_code: string
  name: string
  section_name: string
  score: number
}

export interface MatchRow {
  row_number: number
  source_name: string
  status: MatchStatus
  score: number
  matched_code: string | null
  matched_name: string | null
  candidates: Candidate[]
  rationale: string | null
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
