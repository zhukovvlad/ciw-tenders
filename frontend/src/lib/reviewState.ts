import type { Candidate, Decision, MatchRow, ReviewState } from "@/lib/types"

export function requiresDecision(row: MatchRow): boolean {
  return row.status !== "confident"
}

export function initReview(fileName: string, rows: MatchRow[]): ReviewState {
  const decisions: Record<number, Decision> = {}
  for (const r of rows) {
    decisions[r.row_number] =
      r.status === "confident" && r.matched_code && r.matched_name
        ? {
            kind: "confirmed",
            code: r.matched_code,
            name: r.matched_name,
            manual: false,
          }
        : { kind: "pending" }
  }
  return { fileName, rows, decisions, filter: "all" }
}

export type ReviewAction =
  | { type: "pickCandidate"; row: number; code: string }
  | { type: "confirmArbiter"; row: number }
  | { type: "manualPick"; row: number; candidate: Candidate }
  | { type: "confirmNoMatch"; row: number }
  | { type: "reopen"; row: number }
  | { type: "setFilter"; filter: ReviewState["filter"] }
  | { type: "load"; state: ReviewState }

function rowByNum(state: ReviewState, n: number): MatchRow | undefined {
  return state.rows.find((r) => r.row_number === n)
}

export function reviewReducer(
  state: ReviewState,
  action: ReviewAction
): ReviewState {
  const set = (row: number, d: Decision): ReviewState => ({
    ...state,
    decisions: { ...state.decisions, [row]: d },
  })
  switch (action.type) {
    case "load":
      return action.state
    case "setFilter":
      return { ...state, filter: action.filter }
    case "reopen":
      return set(action.row, { kind: "pending" })
    case "confirmNoMatch":
      return set(action.row, { kind: "no_match" })
    case "confirmArbiter": {
      const r = rowByNum(state, action.row)
      if (!r || !r.matched_code || !r.matched_name) return state
      return set(action.row, {
        kind: "confirmed",
        code: r.matched_code,
        name: r.matched_name,
        manual: false,
      })
    }
    case "pickCandidate": {
      const r = rowByNum(state, action.row)
      const c = r?.candidates.find((x) => x.article_code === action.code)
      if (!c) return state
      return set(action.row, {
        kind: "confirmed",
        code: c.article_code,
        name: c.name,
        manual: false,
      })
    }
    case "manualPick":
      return set(action.row, {
        kind: "confirmed",
        code: action.candidate.article_code,
        name: action.candidate.name,
        manual: true,
      })
    default:
      return state
  }
}

export function decisionFor(state: ReviewState, row: MatchRow): Decision {
  return state.decisions[row.row_number] ?? { kind: "pending" }
}

export function progress(state: ReviewState): {
  reviewed: number
  total: number
} {
  const required = state.rows.filter(requiresDecision)
  const reviewed = required.filter(
    (r) => decisionFor(state, r).kind !== "pending"
  ).length
  return { reviewed, total: required.length }
}

export function filteredRows(state: ReviewState): MatchRow[] {
  switch (state.filter) {
    case "review":
      return state.rows.filter((r) => r.status === "needs_review")
    case "no_match":
      return state.rows.filter((r) => r.status === "no_match")
    default:
      return state.rows
  }
}

export function statusLabel(_row: MatchRow, d: Decision): string {
  if (d.kind === "no_match") return "Нет совпадения"
  if (d.kind === "pending") return "Требует проверки"
  return d.manual ? "Ручной выбор" : "Подтверждено оператором"
}
