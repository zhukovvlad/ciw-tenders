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
  it("N: очередь НЕ переупорядочивается, активной встаёт следующая по документу", () => {
    const { result } = setup()
    // порядок документа: 20 (si=1), 50 (si=4), 10 (si=5)
    expect(result.current.activeRow?.row_number).toBe(20)
    act(() => void result.current.skip())
    // пропущенная 20 осталась на месте — «следующую» задаёт позиция, не порядок
    expect(result.current.queue.map((r) => r.row_number)).toEqual([20, 50, 10])
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("обёртка: после последней нерешённой поток возвращается к самой ранней", () => {
    const { result } = setup()
    act(() => void result.current.skip()) // с 20 → 50
    act(() => void result.current.skip()) // с 50 → 10
    expect(result.current.activeRow?.row_number).toBe(10)
    act(() => void result.current.skip()) // дальше нет → обёртка к ранней
    expect(result.current.activeRow?.row_number).toBe(20)
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

  it("N на СПОРНОЙ строке, открытой ИЗ ГРИДА, не двигает позицию потока (mirror FIX-1)", () => {
    const { result } = setup()
    // до захода в грид поток стоит на самой ранней спорной — 20 (si=1)
    expect(result.current.activeRow?.row_number).toBe(20)
    // открываем ИЗ ГРИДА другую спорную строку (50, si=4) — она не текущая
    // строка потока; в отличие от N-на-ad-hoc-строке выше, 50 состоит в
    // очереди спорных, поэтому идёт по «in-queue»-ветке skip
    act(() => result.current.openFromGrid(50))
    act(() => void result.current.skip())
    act(() => result.current.deselect())
    // поток обязан вернуться туда, где был ДО захода в грид (20), а не
    // «прыгнуть» вперёд на sourceIndex строки из грида (иначе была бы 10 —
    // первая нерешённая строго после si=4)
    expect(result.current.activeRow?.row_number).toBe(20)
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

  it("committed из грида не двигает позицию потока (FIX-1)", () => {
    const { result } = setup()
    // до захода в грид поток стоит на самой ранней спорной — 20 (si=1)
    expect(result.current.activeRow?.row_number).toBe(20)
    // решаем ИЗ ГРИДА другую спорную строку (50, si=4) — она не текущая
    // строка потока, поэтому её позиция не должна стать новой точкой отсчёта
    act(() => result.current.openFromGrid(50))
    act(() => void result.current.committed(50))
    act(() => result.current.deselect())
    // поток обязан вернуться туда, где был ДО захода в грид (20), а не
    // «прыгнуть» вперёд на sourceIndex решённой в гриде строки (иначе была
    // бы 10 — первая нерешённая строго после si=4)
    expect(result.current.activeRow?.row_number).toBe(20)
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

  it("двойной коммит одной строки: провал повторного PATCH возвращает её в pending", () => {
    const { result } = setup()
    act(() => void result.current.committed(20))
    act(() => result.current.openFromGrid(20))
    act(() => void result.current.committed(20)) // undoStack=[20,20], Set={20}
    act(() => result.current.commitFailed(20)) // undoStack=[20]; Set={}
    act(() => result.current.deselect()) // снять пин, вернуться к потоку
    expect(result.current.activeRow?.row_number).toBe(20) // упавшее решение снова в работе
  })
})

describe("useReviewQueue: скраббер-навигация", () => {
  it("navigateTo делает произвольную строку активной с origin=flow", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(10))
    expect(result.current.activeRow?.row_number).toBe(10)
    expect(result.current.origin).toEqual({ kind: "flow" })
  })

  it("navigateTo не пишется в undo-стек (навигация ≠ решение)", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(10))
    expect(result.current.canUndo).toBe(false)
  })

  it("после решения строки из полосы поток идёт от её позиции вперёд", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(20)) // si=1, самая ранняя
    let exit: ReturnType<typeof result.current.committed> | undefined
    act(() => {
      exit = result.current.committed(20)
    })
    expect(exit).toEqual({ kind: "next" })
    // следующая нерешённая строго после si=1 — это 50 (si=4)
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("ad-hoc строка из полосы (confident) решается, поток идёт от её позиции", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(30)) // confident, si=2, не в очереди
    expect(result.current.activeRow?.row_number).toBe(30)
    act(() => void result.current.committed(30))
    // первая нерешённая строго после si=2 — 50 (si=4)
    expect(result.current.activeRow?.row_number).toBe(50)
  })

  it("линейный проход сверху вниз не изменился (пин обратной совместимости)", () => {
    const { result } = setup()
    const seen: number[] = []
    for (let k = 0; k < 3; k++) {
      const n = result.current.activeRow?.row_number
      if (n === undefined) break
      seen.push(n)
      act(() => void result.current.committed(n))
    }
    expect(seen).toEqual([20, 50, 10])
    expect(result.current.activeRow).toBeNull()
  })

  it("commitFailed: откатившаяся строка следующая ПОСЛЕ текущей (пин PR-B)", () => {
    const { result } = setup()
    // решаем 20 (si=1) — активной становится 50
    act(() => void result.current.committed(20))
    expect(result.current.activeRow?.row_number).toBe(50)
    // PATCH по 20 падает: оператора не выдёргиваем, но 20 должна стать следующей
    act(() => result.current.commitFailed(20))
    expect(result.current.activeRow?.row_number).toBe(50)
    // решаем текущую 50 — и вот теперь всплывает откатившаяся 20,
    // хотя по документу она ПОЗАДИ позиции (si=1 < si=4)
    act(() => void result.current.committed(50))
    expect(result.current.activeRow?.row_number).toBe(20)
  })

  it("N на откатившейся строке действительно её пропускает (без залипания)", () => {
    const { result } = setup()
    act(() => void result.current.committed(20))
    act(() => result.current.commitFailed(20))
    act(() => void result.current.committed(50))
    expect(result.current.activeRow?.row_number).toBe(20) // приоритет поднял
    // приоритет проверяется раньше позиции — без снятия N вернул бы ту же 20
    act(() => void result.current.skip())
    expect(result.current.activeRow?.row_number).toBe(10)
  })

  it("два конкурентных отката: первый не потерян (FIX-2)", () => {
    // Локальная фикстура: добавлена спорная 60 (si=6) — ПОСЛЕ si=4, до
    // которого доходит поток к финальному ассерту. Без неё обёртка к
    // pending[0] «спасала» бы финальный ассерт и на одиночном слоте: слот
    // потерял бы первый откат (20), но wrap-around после committed(50) с
    // пустым pending-хвостом всё равно вернул бы pending[0]=20 — тест
    // проходил бы и на неправильной реализации (см. RED-трассировку в
    // фикс-отчёте). С 60 в хвосте слот и список расходятся: слот после
    // committed(50) продолжит поток вперёд к 60, а список — вернёт
    // приоритетную 20.
    const rows = [...ROWS, row(60, 6)]
    const { result } = setup(rows)
    act(() => void result.current.committed(20))
    act(() => void result.current.committed(50))
    // оба PATCH-а падают; активной остаётся 10 (оператора не выдёргиваем)
    act(() => result.current.commitFailed(20))
    act(() => result.current.commitFailed(50))
    expect(result.current.activeRow?.row_number).toBe(10)
    // решаем текущую: всплывает ПОСЛЕДНИЙ откат
    act(() => void result.current.committed(10))
    expect(result.current.activeRow?.row_number).toBe(50)
    // и только теперь — первый, который одиночный слот бы затёр (и увёл бы
    // поток вперёд на 60 вместо возврата к 20)
    act(() => void result.current.committed(50))
    expect(result.current.activeRow?.row_number).toBe(20)
  })

  it("N на ad-hoc строке из полосы двигает позицию вперёд", () => {
    const { result } = setup()
    act(() => result.current.navigateTo(30)) // confident, si=2, не в очереди
    act(() => void result.current.skip())
    // поток продолжается ПОСЛЕ si=2 → 50 (si=4), а не с начала документа
    expect(result.current.activeRow?.row_number).toBe(50)
  })
})
