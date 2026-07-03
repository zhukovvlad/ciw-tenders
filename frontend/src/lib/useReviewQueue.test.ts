import { describe, expect, it } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { useReviewQueue } from "@/lib/useReviewQueue"
import { initReview } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

function row(
  n: number,
  si: number,
  status: MatchStatus = "needs_review",
  over: Partial<MatchRow> = {}
): MatchRow {
  return {
    row_number: n,
    section_code: `1.${n}`,
    source_name: `Строка ${n}`,
    sourceIndex: si,
    breadcrumb: [],
    matchError: null,
    status,
    score: 0.8,
    matched_code: "01.01",
    matched_name: "Статья",
    matched_article_id: 7,
    matchedBreadcrumb: [],
    candidates: [],
    review_status: "unreviewed",
    final_article_id: null,
    finalBreadcrumb: [],
    final_code: null,
    final_name: null,
    ...over,
  }
}

// ВНИМАНИЕ: sourceIndex нарочно не совпадает с row_number — очередь
// сортируется по ПОРЯДКУ ДОКУМЕНТА, а не по id строки
const ROWS: MatchRow[] = [
  row(10, 5), // спорная, в документе ПОСЛЕ строки 20
  row(20, 1), // спорная, первая по документу
  row(30, 2, "confident"), // не в очереди
  row(40, 3, "excluded"), // не в очереди
  row(50, 4, "no_match", {
    matched_code: null,
    matched_name: null,
    matched_article_id: null,
  }),
]

function setup(rows: MatchRow[] = ROWS) {
  const state = initReview("смета.xlsx", rows)
  return renderHook(() => useReviewQueue(state))
}

describe("useReviewQueue: порядок и активная", () => {
  it("очередь = спорные по sourceIndex; активная — первая нерешённая", () => {
    const { result } = setup()
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "flow" })
    expect(result.current.canUndo).toBe(false)
  })

  it("пустая очередь: activeRow === null", () => {
    const { result } = setup([row(1, 1, "confident"), row(2, 2, "excluded")])
    expect(result.current.queue).toEqual([])
    expect(result.current.activeRow).toBeNull()
  })
})

describe("useReviewQueue: skip (N)", () => {
  it("активная уходит в хвост, следующей встаёт очередная нерешённая", () => {
    const { result } = setup()
    let exit
    act(() => {
      exit = result.current.skip()
    })
    expect(exit).toEqual({ kind: "next" })
    expect(result.current.activeRow?.row_number).toBe(50)
    expect(result.current.queue.map((r) => r.row_number)).toEqual([50, 10, 20])
  })

  it("N на ad-hoc строке из грида (не в порядке спорных): порядок цел, выход в грид", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30)) // confident — не в очереди
    let exit
    act(() => {
      exit = result.current.skip()
    })
    expect(exit).toEqual({ kind: "grid" })
    // confident-строка НЕ просочилась в очередь спорных
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(20) // выбор сброшен
  })
})

describe("useReviewQueue: deselect (ручной уход в грид табом)", () => {
  it("сбрасывает явный выбор — очередь возвращается к потоку", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    act(() => result.current.deselect())
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "flow" })
  })
})

describe("useReviewQueue: committed / undo (←)", () => {
  it("поток: committed → {next}, пушит undo-стек", () => {
    const { result } = setup()
    let exit
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "next" })
    expect(result.current.canUndo).toBe(true)
  })

  it("← открывает последнюю закоммиченную; committed после ← → {row: прежняя}", () => {
    const { result } = setup()
    act(() => void result.current.committed(20))
    // активной стала следующая (50); ← возвращает к 20
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(20)
    expect(result.current.origin).toEqual({ kind: "undo", returnTo: 50 })
    let exit
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "row", rowNumber: 50 })
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("← на пустом стеке — no-op", () => {
    const { result } = setup()
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(20)
  })
})

describe("useReviewQueue: открытие из грида", () => {
  it("openFromGrid делает активной любую строку, включая confident", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    expect(result.current.activeRow?.row_number).toBe(30)
    expect(result.current.origin).toEqual({ kind: "grid" })
  })

  it("committed из грида → {grid}; ad-hoc решение пушится в undo наравне", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    let exit
    act(() => {
      exit = result.current.committed(30)
    })
    expect(exit).toEqual({ kind: "grid" })
    act(() => result.current.undo())
    expect(result.current.activeRow?.row_number).toBe(30)
  })
})

describe("useReviewQueue: ошибка PATCH", () => {
  it("commitFailed: строка в голову порядка, из undo-стека вон, активная не прыгает", () => {
    const { result } = setup()
    act(() => void result.current.committed(20)) // активной стала 50
    act(() => result.current.commitFailed(20))
    expect(result.current.canUndo).toBe(false)
    // 20 в голове сессионного порядка…
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    // …но активная осталась 50 (запинована) — 20 станет следующей
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("commitFailed для строки не из очереди (confident) порядок не трогает", () => {
    const { result } = setup()
    act(() => result.current.openFromGrid(30))
    act(() => void result.current.committed(30))
    act(() => result.current.commitFailed(30))
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
  })

  it("STALE CLOSURE: commitFailed из рендера ДО коммита не выдёргивает оператора", () => {
    // Прод-сценарий: commit(A) захватывает queue рендера R0 (активная A=20),
    // committed(20) двигает активную на 50, PATCH падает ПОЗЖЕ — .then зовёт
    // commitFailed из СТАРОГО замыкания. Пиннинг обязан читать активную из
    // ref-на-последний-рендер, иначе «cur !== n» видит A===A и не пиннит →
    // активная прыгает назад на 20 (запрещено спекой §3a).
    const { result } = setup()
    const stale = result.current // ← замыкание рендера до коммита
    act(() => void result.current.committed(20)) // активная стала 50
    act(() => stale.commitFailed(20)) // асинхронный фейл со старым замыканием
    expect(result.current.activeRow?.row_number).toBe(50) // осталась 50
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
  })
})
