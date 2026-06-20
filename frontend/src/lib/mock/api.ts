import type { Candidate, MatchRow, ReviewState } from "@/lib/types"
import { MOCK_ARTICLES, MOCK_ROWS } from "@/lib/mock/fixtures"
import { decisionFor, statusLabel } from "@/lib/reviewState"

export interface Progress {
  phase: "parsing" | "embedding" | "matching" | "done"
  done: number
  total: number
  etaSeconds: number | null
}

const delay = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

/** Мок сопоставления: имитирует фазы и прогресс, отдаёт фикстуру. */
export async function matchEstimate(
  _file: File,
  onProgress: (p: Progress) => void,
): Promise<MatchRow[]> {
  const total = MOCK_ROWS.length
  onProgress({ phase: "parsing", done: 0, total, etaSeconds: null })
  await delay(150)
  for (let i = 1; i <= total; i++) {
    onProgress({ phase: "embedding", done: i, total, etaSeconds: null })
    await delay(20)
  }
  const review = MOCK_ROWS.filter((r) => r.status !== "confident").length
  for (let i = 1; i <= total; i++) {
    // ETA известен: ~0.4с на спорную строку (LLM дороже эмбеддинга)
    const remainingReview = Math.max(0, review - Math.round((i / total) * review))
    onProgress({ phase: "matching", done: i, total, etaSeconds: remainingReview * 0.4 })
    await delay(20)
  }
  onProgress({ phase: "done", done: total, total, etaSeconds: 0 })
  return MOCK_ROWS
}

/** Escape-hatch: ручной поиск по справочнику (мок). */
export async function searchArticles(query: string): Promise<Candidate[]> {
  await delay(120)
  const q = query.trim().toLowerCase()
  if (!q) return []
  return MOCK_ARTICLES.filter(
    (c) =>
      c.name.toLowerCase().includes(q) ||
      c.article_code.toLowerCase().includes(q) ||
      c.section_name.toLowerCase().includes(q),
  )
}

const HEADERS = ["row", "Работа из сметы", "Код статьи", "Наименование статьи", "Score", "Статус", "Альтернатива 2", "Альтернатива 3"]

/** Стенд-ин выгрузки: CSV (`;`-разделитель). Прод заменит на бэкенд .xlsx. */
export function exportEstimateCsv(state: ReviewState): string {
  const esc = (v: string) => (v.includes(";") || v.includes('"') ? `"${v.replace(/"/g, '""')}"` : v)
  const lines = [HEADERS.join(";")]
  for (const row of state.rows) {
    const d = decisionFor(state, row)
    const manual = d.kind === "confirmed" && d.manual
    const code = d.kind === "confirmed" ? d.code : ""
    const name = d.kind === "confirmed" ? d.name : ""
    const score = manual || d.kind === "no_match" ? "" : row.score.toFixed(2)
    const alt2 = row.candidates[1] ? `${row.candidates[1].article_code} ${row.candidates[1].name}` : ""
    const alt3 = row.candidates[2] ? `${row.candidates[2].article_code} ${row.candidates[2].name}` : ""
    lines.push([String(row.row_number), row.source_name, code, name, score, statusLabel(row, d), alt2, alt3].map(esc).join(";"))
  }
  return lines.join("\n")
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
