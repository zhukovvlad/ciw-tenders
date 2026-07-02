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
  // опциональны защитно: старый бэк (до соответствующих фич) их не присылал
  status_detail?: string | null
  completed_at?: string | null
  is_reference?: boolean
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

export interface EstimateDetail {
  id: number
  fileName: string
  status: string
  statusDetail: string | null
  completedAt: string | null // ISO
  isReference: boolean
  rows: MatchRow[]
}

export async function getEstimate(id: number): Promise<EstimateDetail> {
  const dto = await apiGet<DetailDto>(`/estimates/${id}`)
  return {
    id: dto.id,
    fileName: dto.filename,
    status: dto.status,
    statusDetail: dto.status_detail ?? null,
    completedAt: dto.completed_at ?? null,
    isReference: dto.is_reference ?? false,
    rows: dto.rows.map(rowFromDto),
  }
}

export async function setCompletion(
  id: number,
  completed: boolean
): Promise<{ completedAt: string | null }> {
  const dto = await apiSend<{ completed_at: string | null }>(
    "PATCH",
    `/estimates/${id}/completion`,
    { completed }
  )
  return { completedAt: dto.completed_at }
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
  // опциональны защитно: старый бэк (до соответствующих фич) их не присылал
  completed_at?: string | null
  reviewed_count?: number
  total_reviewable?: number
}

export interface EstimateListItem {
  id: number
  filename: string
  status: string
  nodesCount: number
  createdAt: string // ISO — форматируется в UI
  completedAt: string | null
  reviewedCount: number
  totalReviewable: number
}

export async function listEstimates(opts?: {
  limit?: number
  offset?: number
}): Promise<{ items: EstimateListItem[]; total: number }> {
  const limit = opts?.limit ?? 50
  const offset = opts?.offset ?? 0
  const dto = await apiGet<{ items: SummaryDto[]; total: number }>(
    `/estimates?limit=${limit}&offset=${offset}`
  )
  return {
    items: dto.items.map((d) => ({
      id: d.id,
      filename: d.filename,
      status: d.status,
      nodesCount: d.nodes_count,
      createdAt: d.created_at,
      completedAt: d.completed_at ?? null,
      reviewedCount: d.reviewed_count ?? 0,
      totalReviewable: d.total_reviewable ?? 0,
    })),
    total: dto.total,
  }
}

export async function deleteEstimate(id: number): Promise<void> {
  await apiSend("DELETE", `/estimates/${id}`)
}

export async function setReference(
  id: number,
  value: boolean
): Promise<{ is_reference: boolean; promoted: number }> {
  return apiSend("PATCH", `/estimates/${id}/reference`, {
    is_reference: value,
  })
}

export async function rebuildFund(): Promise<void> {
  await apiSend("POST", "/estimates/fund/rebuild")
}
