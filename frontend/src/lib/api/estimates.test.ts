import { afterEach, describe, expect, it, vi } from "vitest"
import * as client from "@/lib/api/client"
import {
  deleteEstimate,
  getEstimate,
  listEstimates,
  pollEstimate,
  rebuildFund,
  rowFromDto,
  setCompletion,
  setReference,
} from "@/lib/api/estimates"

afterEach(() => vi.restoreAllMocks())

describe("rowFromDto", () => {
  it("maps DTO to MatchRow (id→row_number, code→section_code)", () => {
    const row = rowFromDto({
      id: 42,
      code: "3.2",
      name: "Кладка",
      status: "needs_review",
      score: 0.7,
      matched_code: "2.1",
      matched_name: "Статья",
      matched_article_id: 7,
      candidates: [{ id: 7, code: "2.1", name: "Статья", score: 0.7 }],
      review_status: "unreviewed",
      final_article_id: null,
      final_code: null,
      final_name: null,
    })
    expect(row.row_number).toBe(42)
    expect(row.section_code).toBe("3.2")
    expect(row.source_name).toBe("Кладка")
    expect(row.candidates[0].article_code).toBe("2.1")
    expect(row.review_status).toBe("unreviewed")
  })
})

const BASE_ROW_DTO: Parameters<typeof rowFromDto>[0] = {
  id: 1,
  code: "1",
  name: "Row",
  status: "needs_review",
  score: 0.5,
  matched_code: null,
  matched_name: null,
  matched_article_id: null,
  candidates: [],
  review_status: "unreviewed",
  final_article_id: null,
  final_code: null,
  final_name: null,
}

describe("rowFromDto: крошки/merge (Task 6)", () => {
  it("rowFromDto мапит sourceIndex/breadcrumb/matchError и крошки кандидатов", () => {
    const dto = {
      ...BASE_ROW_DTO,
      source_index: 12,
      breadcrumb: ["Конструктив", "Подземная часть"],
      matched_breadcrumb: ["03 Фундаменты"],
      match_error: null,
      candidates: [
        {
          id: 3,
          code: "03.04",
          name: "Фунд.",
          score: 0.7,
          breadcrumb: ["03 Фундаменты"],
        },
      ],
    }
    const row = rowFromDto(dto)
    expect(row.sourceIndex).toBe(12)
    expect(row.breadcrumb).toEqual(["Конструктив", "Подземная часть"])
    expect(row.matchedBreadcrumb).toEqual(["03 Фундаменты"])
    expect(row.candidates[0].breadcrumb).toEqual(["03 Фундаменты"])
  })

  it("rowFromDto: PATCH-ответ наследует из prev ТОЛЬКО breadcrumb строки", () => {
    const prev = rowFromDto({
      ...BASE_ROW_DTO,
      source_index: 12,
      breadcrumb: ["Конструктив"],
    })
    const afterPatch = rowFromDto(
      {
        ...BASE_ROW_DTO,
        review_status: "confirmed",
        breadcrumb: [], // PATCH не пересчитывает крошку СТРОКИ — merge берёт prev
      },
      prev
    )
    expect(afterPatch.breadcrumb).toEqual(["Конструктив"])
    expect(afterPatch.sourceIndex).toBe(12)
  })

  it("ПИН: переигрывание решения не наследует крошку прежней статьи", () => {
    // строка была решена на статью A (через поиск), оператор переиграл на B:
    // PATCH-ответ ГИДРАТИРОВАН бэком (final_breadcrumb статьи B) — prev с крошкой A
    // не должен просочиться ни при каких merge-ветках
    const prev = rowFromDto({
      ...BASE_ROW_DTO,
      final_breadcrumb: ["08 Отделочные работы"], // предки статьи A
    })
    const afterRepick = rowFromDto(
      {
        ...BASE_ROW_DTO,
        review_status: "overridden",
        final_breadcrumb: ["03 Фундаменты"], // гидратация бэка: предки статьи B
      },
      prev
    )
    expect(afterRepick.finalBreadcrumb).toEqual(["03 Фундаменты"])
  })

  it("крошки СТАТЕЙ никогда не мержатся из prev: final_breadcrumb без ключа ⇒ []", () => {
    // Усиление пин-теста выше: там after-DTO несёт непустой final_breadcrumb,
    // и ошибочный fallback `?? prev?.finalBreadcrumb` тоже прошёл бы. Здесь
    // ключ отсутствует вовсе — любой merge из prev (?? или проверка длины по
    // образцу крошки строки) подставил бы устаревшую крошку статьи A.
    const prev = rowFromDto({
      ...BASE_ROW_DTO,
      final_breadcrumb: ["08 Отделочные работы"], // предки статьи A
    })
    const afterPatch = rowFromDto(
      { ...BASE_ROW_DTO, review_status: "confirmed" }, // final_breadcrumb нет
      prev
    )
    expect(afterPatch.finalBreadcrumb).toEqual([])
  })
})

describe("estimates api list/delete", () => {
  it("listEstimates маппит snake_case DTO в camelCase", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      items: [
        {
          id: 1,
          filename: "a.xlsx",
          status: "ready",
          nodes_count: 12,
          created_at: "2026-06-24T10:00:00Z",
          completed_at: null,
          reviewed_count: 0,
          total_reviewable: 0,
        },
      ],
      total: 1,
    })
    const { items, total } = await listEstimates()
    expect(total).toBe(1)
    expect(items).toEqual([
      {
        id: 1,
        filename: "a.xlsx",
        status: "ready",
        nodesCount: 12,
        createdAt: "2026-06-24T10:00:00Z",
        completedAt: null,
        reviewedCount: 0,
        totalReviewable: 0,
      },
    ])
  })

  it("listEstimates ходит на GET /estimates с дефолтными limit/offset", async () => {
    const spy = vi
      .spyOn(client, "apiGet")
      .mockResolvedValue({ items: [], total: 0 })
    await listEstimates()
    expect(spy).toHaveBeenCalledWith("/estimates?limit=50&offset=0")
  })

  it("getEstimate возвращает status и completedAt", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 5,
      filename: "a.xlsx",
      status: "ready",
      status_detail: null,
      completed_at: "2026-07-02T12:00:00Z",
      is_reference: false,
      rows: [],
    })
    const d = await getEstimate(5)
    expect(d.status).toBe("ready")
    expect(d.completedAt).toBe("2026-07-02T12:00:00Z")
  })

  it("setCompletion шлёт PATCH /completion", async () => {
    const spy = vi
      .spyOn(client, "apiSend")
      .mockResolvedValue({ completed_at: null })
    const r = await setCompletion(5, false)
    expect(r.completedAt).toBeNull()
    expect(spy).toHaveBeenCalledWith("PATCH", "/estimates/5/completion", {
      completed: false,
    })
  })

  it("listEstimates отдаёт items+total и прокидывает limit/offset", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue({
      items: [
        {
          id: 1,
          filename: "a.xlsx",
          status: "ready",
          nodes_count: 3,
          created_at: "2026-07-01T00:00:00Z",
          completed_at: null,
          reviewed_count: 1,
          total_reviewable: 2,
        },
      ],
      total: 7,
    })
    const r = await listEstimates({ limit: 10, offset: 20 })
    expect(spy).toHaveBeenCalledWith("/estimates?limit=10&offset=20")
    expect(r.total).toBe(7)
    expect(r.items[0].reviewedCount).toBe(1)
  })

  it("deleteEstimate шлёт DELETE по id", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await deleteEstimate(7)
    expect(spy).toHaveBeenCalledWith("DELETE", "/estimates/7")
  })

  it("setReference шлёт PATCH /estimates/{id}/reference с is_reference и возвращает распарсенный DTO", async () => {
    const spy = vi
      .spyOn(client, "apiSend")
      .mockResolvedValue({ is_reference: true, promoted: 3 })
    const result = await setReference(7, true)
    expect(spy).toHaveBeenCalledWith("PATCH", "/estimates/7/reference", {
      is_reference: true,
    })
    expect(result).toEqual({ is_reference: true, promoted: 3 })
  })

  it("setReference(id, false) снимает смету из фонда", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await setReference(7, false)
    expect(spy).toHaveBeenCalledWith("PATCH", "/estimates/7/reference", {
      is_reference: false,
    })
  })

  it("rebuildFund шлёт POST /estimates/fund/rebuild без тела", async () => {
    const spy = vi.spyOn(client, "apiSend").mockResolvedValue(undefined)
    await rebuildFund()
    expect(spy).toHaveBeenCalledWith("POST", "/estimates/fund/rebuild")
  })
})

describe("pollEstimate отмена через AbortSignal", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("signal уже отменён до вызова → реджект AbortError без запроса", async () => {
    const spy = vi.spyOn(client, "apiGet")
    const controller = new AbortController()
    controller.abort()
    await expect(
      pollEstimate(1, vi.fn(), 1000, { signal: controller.signal })
    ).rejects.toMatchObject({ name: "AbortError" })
    expect(spy).not.toHaveBeenCalled()
  })

  it("отмена во время ожидания следующего тика останавливает цикл поллинга", async () => {
    vi.useFakeTimers()
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 1,
      filename: "a.xlsx",
      status: "running",
      rows: [],
    })
    const controller = new AbortController()
    const promise = pollEstimate(1, vi.fn(), 1000, {
      signal: controller.signal,
    })
    // первый тик: apiGet резолвится, таймер на следующий опрос выставлен
    await vi.advanceTimersByTimeAsync(0)
    expect(spy).toHaveBeenCalledTimes(1)
    controller.abort()
    await expect(promise).rejects.toMatchObject({ name: "AbortError" })
    // сдвигаем время дальше интервала — новых запросов быть не должно
    await vi.advanceTimersByTimeAsync(5000)
    expect(spy).toHaveBeenCalledTimes(1)
  })
})
