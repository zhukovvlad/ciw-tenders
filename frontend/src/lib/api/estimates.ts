import type {
  Candidate,
  MatchRow,
  MatchStatus,
  ReviewStatus,
  StructuralAnomaly,
} from "@/lib/types"
import { ApiError, apiGet, apiGetBlob, apiSend, apiUpload } from "./client"

interface RowDto {
  id: number
  code: string
  name: string
  status: MatchStatus
  score: number | null
  // опциональны защитно: старый бэк (до контракта крошек, Task 5) их не присылал
  source_index?: number
  breadcrumb?: string[]
  match_error?: string | null
  matched_code: string | null
  matched_name: string | null
  matched_article_id: number | null
  matched_breadcrumb?: string[]
  candidates: {
    id: number | null
    code: string
    name: string
    score: number | null
    breadcrumb?: string[]
  }[]
  review_status: ReviewStatus
  final_article_id: number | null
  final_breadcrumb?: string[]
  final_code: string | null
  final_name: string | null
}

interface DetailDto {
  id: number
  filename: string
  status: string
  // опциональны защитно: старый бэк (до соответствующих фич) их не присылал
  status_detail?: string | null
  // опционален защитно: старый бэк (до PR-1 машинных кодов) его не присылал —
  // фолбэк null сохраняет текущее поведение (сырой status_detail без заголовка по коду)
  status_code?: string | null
  completed_at?: string | null
  is_reference?: boolean
  rows: RowDto[]
  // опциональны защитно: старый бэк (до персиста аномалий, этап 3) их не присылал
  anomalies?: AnomalyDto[]
  outline_overrides?: number
}

interface AnomalyDto {
  kind: string
  source_index: number
  code: string
  name: string
  detail: string
}

function anomalyFromDto(a: AnomalyDto): StructuralAnomaly {
  return {
    kind: a.kind,
    sourceIndex: a.source_index,
    code: a.code,
    name: a.name,
    detail: a.detail,
  }
}

interface CreateDto {
  id: number
  status: string
  // Опциональны: старый бэк (до фичи структурных аномалий) их не присылает —
  // ниже читаются защитно (`?? []` / `?? 0`).
  anomalies?: AnomalyDto[]
  outline_overrides?: number
}

export interface UploadResult {
  id: number
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

export function rowFromDto(r: RowDto, prev?: MatchRow): MatchRow {
  return {
    row_number: r.id,
    section_code: r.code,
    source_name: r.name,
    sourceIndex: r.source_index ?? prev?.sourceIndex ?? 0,
    // ЕДИНСТВЕННАЯ merge-ветка: крошка СТРОКИ. PATCH её не пересчитывает
    // (нужны все строки сметы) и несёт [] — проверка длины, не ??, иначе
    // пустой массив затёр бы prev. Крошки СТАТЕЙ (final/matched/кандидаты) и
    // matchError НЕ мержатся из prev: легитимный null от сервера (например,
    // будущий PATCH, очищающий match_error) не должен воскрешать устаревший
    // текст ошибки; final_article_id меняется самим PATCH-ем — наследование
    // из prev подставило бы крошку прежней статьи под новую (пин-тест
    // «переигрывание решения...»).
    breadcrumb:
      r.breadcrumb && r.breadcrumb.length > 0
        ? r.breadcrumb
        : (prev?.breadcrumb ?? []),
    matchError: r.match_error ?? null,
    status: r.status,
    score: r.score ?? null,
    matched_code: r.matched_code,
    matched_name: r.matched_name,
    matched_article_id: r.matched_article_id,
    matchedBreadcrumb: r.matched_breadcrumb ?? [],
    candidates: r.candidates.map(
      (c): Candidate => ({
        id: c.id,
        article_code: c.code,
        name: c.name,
        score: c.score,
        breadcrumb: c.breadcrumb ?? [],
      })
    ),
    review_status: r.review_status,
    final_article_id: r.final_article_id,
    finalBreadcrumb: r.final_breadcrumb ?? [],
    final_code: r.final_code,
    final_name: r.final_name,
  }
}

export interface EstimateDetail {
  id: number
  fileName: string
  status: string
  statusDetail: string | null
  statusCode: string | null
  completedAt: string | null // ISO
  isReference: boolean
  rows: MatchRow[]
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

export async function getEstimate(id: number): Promise<EstimateDetail> {
  const dto = await apiGet<DetailDto>(`/estimates/${id}`)
  return {
    id: dto.id,
    fileName: dto.filename,
    status: dto.status,
    statusDetail: dto.status_detail ?? null,
    statusCode: dto.status_code ?? null,
    completedAt: dto.completed_at ?? null,
    isReference: dto.is_reference ?? false,
    rows: dto.rows.map((r) => rowFromDto(r)),
    anomalies: (dto.anomalies ?? []).map(anomalyFromDto),
    outlineOverrides: dto.outline_overrides ?? 0,
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
    anomalies: (dto.anomalies ?? []).map(anomalyFromDto),
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
  intervalMs = 1500,
  opts?: { signal?: AbortSignal }
): Promise<{ fileName: string; rows: MatchRow[] }> {
  return new Promise((resolve, reject) => {
    const signal = opts?.signal
    let timer: ReturnType<typeof setTimeout> | undefined
    const onAbort = () => {
      if (timer !== undefined) clearTimeout(timer)
      reject(new DOMException("Aborted", "AbortError"))
    }
    if (signal) {
      if (signal.aborted) {
        onAbort()
        return
      }
      signal.addEventListener("abort", onAbort)
    }
    const cleanup = () => signal?.removeEventListener("abort", onAbort)
    const check = async () => {
      if (signal?.aborted) return // onAbort уже отверг промис
      try {
        const dto = await apiGet<DetailDto>(`/estimates/${id}`)
        if (signal?.aborted) return // отменили, пока ждали ответ — не резолвим дальше
        if (TERMINAL_OK.has(dto.status)) {
          cleanup()
          resolve({
            fileName: dto.filename,
            rows: dto.rows.map((r) => rowFromDto(r)),
          })
          return
        }
        if (dto.status === "blocked") {
          cleanup()
          reject(
            new ApiError(
              0,
              "Обработка сметы заблокирована",
              "estimate_processing_blocked"
            )
          )
          return
        }
        // pending/running — узлы матчатся; «готовы» = строки с терминальным
        // статусом матчинга (всё, кроме ещё-не-обработанного pending).
        const done = dto.rows.filter(
          (r) => (r.status as string) !== "pending"
        ).length
        onProgress(dto.status, done, dto.rows.length)
        timer = setTimeout(() => void check(), intervalMs)
      } catch (err) {
        cleanup()
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
  articleId?: number,
  prev?: MatchRow
): Promise<MatchRow> {
  const dto = await apiSend<RowDto>(
    "PATCH",
    `/estimates/${estimateId}/rows/${rowId}/review`,
    { action, article_id: articleId ?? null }
  )
  return rowFromDto(dto, prev)
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
