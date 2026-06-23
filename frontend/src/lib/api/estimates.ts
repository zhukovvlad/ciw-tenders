import type {
  Candidate,
  MatchRow,
  MatchStatus,
  ReviewStatus,
} from "@/lib/types"
import { apiGet, apiSend, apiUpload } from "./client"

interface RowDto {
  id: number
  name: string
  status: MatchStatus
  score: number | null
  matched_code: string | null
  matched_name: string | null
  matched_article_id: number | null
  candidates: { id: number | null; code: string; name: string; score: number }[]
  review_status: ReviewStatus
  final_article_id: number | null
  final_code: string | null
  final_name: string | null
}

interface DetailDto {
  id: number
  filename: string
  status: string
  rows: RowDto[]
}

interface CreateDto {
  id: number
  status: string
}

export function rowFromDto(r: RowDto): MatchRow {
  return {
    row_number: r.id,
    source_name: r.name,
    status: r.status,
    score: r.score ?? 0,
    matched_code: r.matched_code,
    matched_name: r.matched_name,
    matched_article_id: r.matched_article_id,
    candidates: r.candidates.map(
      (c): Candidate => ({
        id: c.id,
        article_code: c.code,
        name: c.name,
        score: c.score,
      })
    ),
    review_status: r.review_status,
    final_article_id: r.final_article_id,
    final_code: r.final_code,
    final_name: r.final_name,
  }
}

export async function getEstimate(
  id: number
): Promise<{ fileName: string; rows: MatchRow[] }> {
  const dto = await apiGet<DetailDto>(`/estimates/${id}`)
  return { fileName: dto.filename, rows: dto.rows.map(rowFromDto) }
}

export async function uploadEstimate(file: File): Promise<number> {
  const dto = await apiUpload<CreateDto>("/estimates", file)
  return dto.id
}

export async function pollEstimate(
  id: number,
  onProgress: (phase: string, done: number, total: number) => void,
  intervalMs = 1500
): Promise<{ fileName: string; rows: MatchRow[] }> {
  return new Promise((resolve, reject) => {
    const check = async () => {
      try {
        const dto = await apiGet<DetailDto>(`/estimates/${id}`)
        if (dto.status === "ready" || dto.status === "partial_error") {
          resolve({ fileName: dto.filename, rows: dto.rows.map(rowFromDto) })
          return
        }
        if (dto.status === "error") {
          reject(new Error("Обработка сметы завершилась ошибкой"))
          return
        }
        // still running — report progress
        const done = dto.rows.filter(
          (r) => r.status !== ("running" as MatchStatus)
        ).length
        onProgress(dto.status, done, dto.rows.length)
        setTimeout(() => void check(), intervalMs)
      } catch (err) {
        reject(err)
      }
    }
    void check()
  })
}

export async function patchRowReview(
  estimateId: number,
  rowId: number,
  action: "confirm" | "pick" | "reject",
  articleId?: number
): Promise<MatchRow> {
  const dto = await apiSend<RowDto>(
    "PATCH",
    `/estimates/${estimateId}/rows/${rowId}/review`,
    { action, article_id: articleId ?? null }
  )
  return rowFromDto(dto)
}

export async function exportEstimate(id: number): Promise<Blob> {
  const token = sessionStorage.getItem("ciw.auth.token")
  const res = await fetch(`/api/estimates/${id}/export`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`Экспорт не удался (${res.status})`)
  return res.blob()
}
