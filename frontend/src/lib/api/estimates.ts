import type {
  Candidate,
  MatchRow,
  MatchStatus,
  ReviewStatus,
  StructuralAnomaly,
} from "@/lib/types"
import { apiGet, apiGetBlob, apiSend, apiUpload } from "./client"

interface RowDto {
  id: number
  code: string
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
  // Опциональны: старый бэк (до фичи структурных аномалий) их не присылает —
  // ниже читаются защитно (`?? []` / `?? 0`).
  anomalies?: {
    kind: string
    source_index: number
    code: string
    name: string
    detail: string
  }[]
  outline_overrides?: number
}

export interface UploadResult {
  id: number
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

export function rowFromDto(r: RowDto): MatchRow {
  return {
    row_number: r.id,
    section_code: r.code,
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

export async function uploadEstimate(file: File): Promise<UploadResult> {
  const dto = await apiUpload<CreateDto>("/estimates", file)
  return {
    id: dto.id,
    anomalies: (dto.anomalies ?? []).map((a) => ({
      kind: a.kind,
      sourceIndex: a.source_index,
      code: a.code,
      name: a.name,
      detail: a.detail,
    })),
    outlineOverrides: dto.outline_overrides ?? 0,
  }
}

// Терминальные статусы сметы (см. бэк EstimateStatus): ready/partial_error —
// успех (есть строки для ревью), blocked — терминальный отказ. pending/running —
// ещё в работе.
const TERMINAL_OK = new Set(["ready", "partial_error"])

export async function pollEstimate(
  id: number,
  onProgress: (status: string, done: number, total: number) => void,
  intervalMs = 1500
): Promise<{ fileName: string; rows: MatchRow[] }> {
  return new Promise((resolve, reject) => {
    const check = async () => {
      try {
        const dto = await apiGet<DetailDto>(`/estimates/${id}`)
        if (TERMINAL_OK.has(dto.status)) {
          resolve({ fileName: dto.filename, rows: dto.rows.map(rowFromDto) })
          return
        }
        if (dto.status === "blocked") {
          reject(new Error("Обработка сметы заблокирована"))
          return
        }
        // pending/running — узлы матчатся; «готовы» = строки с терминальным
        // статусом матчинга (всё, кроме ещё-не-обработанного pending).
        const done = dto.rows.filter(
          (r) => (r.status as string) !== "pending"
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
  return apiGetBlob(`/estimates/${id}/export`)
}

interface SummaryDto {
  id: number
  filename: string
  status: string
  nodes_count: number
  created_at: string // ISO
}

export interface EstimateListItem {
  id: number
  filename: string
  status: string
  nodesCount: number
  createdAt: string // ISO — форматируется в UI
}

export async function listEstimates(): Promise<EstimateListItem[]> {
  const dtos = await apiGet<SummaryDto[]>("/estimates")
  return dtos.map((d) => ({
    id: d.id,
    filename: d.filename,
    status: d.status,
    nodesCount: d.nodes_count,
    createdAt: d.created_at,
  }))
}

export async function deleteEstimate(id: number): Promise<void> {
  await apiSend("DELETE", `/estimates/${id}`)
}
