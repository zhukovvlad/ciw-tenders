// Сессионный (in-memory) слой навигации очереди ревью — спека этапа 2 §3a.
// reviewState НЕ трогает: решения остаются зеркалом сервера; здесь живёт только
// порядок/активная/undo текущей сессии (F5 всё сбрасывает — это by design).
import { useEffect, useMemo, useRef, useState } from "react"
import type { MatchRow, ReviewState } from "@/lib/types"
import { decisionFor, requiresDecision } from "@/lib/reviewState"

export type CardOrigin =
  | { kind: "flow" }
  | { kind: "grid" }
  | { kind: "undo"; returnTo: number | null }

export type CommitExit =
  | { kind: "next" }
  | { kind: "grid" }
  | { kind: "row"; rowNumber: number }

export interface ReviewQueue {
  queue: MatchRow[]
  activeRow: MatchRow | null
  origin: CardOrigin
  canUndo: boolean
  openFromGrid: (rowNumber: number) => void
  skip: () => CommitExit
  undo: () => void
  committed: (rowNumber: number) => CommitExit
  commitFailed: (rowNumber: number) => void
  deselect: () => void
}

interface Selection {
  row: number
  origin: CardOrigin
}

export function useReviewQueue(state: ReviewState): ReviewQueue {
  const initialOrder = () =>
    state.rows
      .filter(requiresDecision)
      .sort((a, b) => a.sourceIndex - b.sourceIndex)
      .map((r) => r.row_number)

  const [order, setOrder] = useState<number[]>(initialOrder)
  const [undoStack, setUndoStack] = useState<number[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)

  // Пересборка порядка ТОЛЬКО при смене набора спорных (загрузка новой сметы);
  // ключ — отсортированные row_number, чтобы syncRow-обновления не сбивали сессию.
  const idsKey = state.rows
    .filter(requiresDecision)
    .map((r) => r.row_number)
    .sort((a, b) => a - b)
    .join(",")
  // Паттерн React «сохранить значение с прошлого рендера» (useState, НЕ ref —
  // eslint react-hooks/refs запрещает читать/писать .current во время рендера):
  // сравнение и сброс идут прямо в теле рендера, это легальный setState-во-время-
  // рендера того же компонента.
  const [prevIdsKey, setPrevIdsKey] = useState(idsKey)
  if (prevIdsKey !== idsKey) {
    setPrevIdsKey(idsKey)
    setOrder(initialOrder())
    setUndoStack([])
    setSelection(null)
  }

  const byNum = useMemo(
    () => new Map(state.rows.map((r) => [r.row_number, r])),
    [state.rows]
  )

  const queue = useMemo(
    () =>
      order
        .map((n) => byNum.get(n))
        .filter((r): r is MatchRow => r !== undefined),
    [order, byNum]
  )

  // Решённые В ЭТОЙ СЕССИИ (оптимистично, до/независимо от ответа PATCH):
  // decisionFor обновится только после dispatch снаружи — хук не ждёт этого.
  // undoStack уже ведёт этот набор один-в-один (committed добавляет, undo/
  // commitFailed убирают), отдельный Set был бы дублирующим источником истины.
  const isPending = (r: MatchRow) =>
    decisionFor(state, r).kind === "pending" &&
    !undoStack.includes(r.row_number)

  const autoActive = queue.find(isPending) ?? null
  const activeRow = selection ? (byNum.get(selection.row) ?? null) : autoActive
  const origin: CardOrigin = selection?.origin ?? { kind: "flow" }

  // Свежая активная для АСИНХРОННЫХ вызовов (commitFailed из .then PATCH-а):
  // замыкание там — из рендера до committed(), где активной была сама упавшая
  // строка; читать её из замыкания нельзя (пин-тест «STALE CLOSURE»). Ref —
  // тот же объект во всех рендерах, но пишем в него ТОЛЬКО из эффекта (после
  // коммита рендера), а не во время самого рендера — этого требует
  // eslint react-hooks/refs.
  const activeRowRef = useRef(activeRow)
  useEffect(() => {
    activeRowRef.current = activeRow
  })

  const exitFor = (o: CardOrigin): CommitExit =>
    o.kind === "grid"
      ? { kind: "grid" }
      : o.kind === "undo" && o.returnTo !== null
        ? { kind: "row", rowNumber: o.returnTo }
        : { kind: "next" }

  const openFromGrid = (rowNumber: number) =>
    setSelection({ row: rowNumber, origin: { kind: "grid" } })

  const deselect = () => setSelection(null)

  const skip = (): CommitExit => {
    const n = activeRow?.row_number
    if (n === undefined) return { kind: "next" }
    if (!order.includes(n)) {
      // Ad-hoc строка (confident/фонд из грида): «пропустить» = передумал —
      // порядок спорных НЕ загрязняем, уходим туда, откуда пришли
      const exit = exitFor(origin)
      if (exit.kind === "row")
        setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
      else setSelection(null)
      return exit
    }
    setOrder((o) => [...o.filter((x) => x !== n), n])
    setSelection(null)
    return { kind: "next" }
  }

  const undo = () => {
    if (undoStack.length === 0) return
    const top = undoStack[undoStack.length - 1]
    const returnTo = activeRow?.row_number ?? null
    setUndoStack((s) => s.slice(0, -1)) // строка снова «в работе» (isPending)
    setSelection({ row: top, origin: { kind: "undo", returnTo } })
  }

  const committed = (rowNumber: number): CommitExit => {
    setUndoStack((s) => [...s, rowNumber]) // строка «решена в сессии» (isPending)
    const exit = exitFor(origin)
    if (exit.kind === "row")
      setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
    else setSelection(null)
    return exit
  }

  const commitFailed = (rowNumber: number) => {
    setUndoStack((s) => {
      const i = s.lastIndexOf(rowNumber)
      return i === -1 ? s : [...s.slice(0, i), ...s.slice(i + 1)]
    }) // строка снова «в работе» (isPending) — вышла из undoStack
    setOrder((o) =>
      o.includes(rowNumber)
        ? [rowNumber, ...o.filter((x) => x !== rowNumber)]
        : o
    )
    // Не выдёргивать оператора из текущей строки: пиннуть её, если явного
    // выбора не было — вернувшаяся строка станет СЛЕДУЮЩЕЙ (голова очереди).
    // ВАЖНО: активная — из ref-а, НЕ из замыкания: commitFailed зовётся из
    // .then PATCH-а, а замыкание захвачено рендером ДО committed(), где
    // активной была сама упавшая строка (пин-тест «STALE CLOSURE»)
    setSelection((prev) => {
      if (prev) return prev
      const cur = activeRowRef.current
      return cur && cur.row_number !== rowNumber
        ? { row: cur.row_number, origin: { kind: "flow" } }
        : null
    })
  }

  return {
    queue,
    activeRow,
    origin,
    canUndo: undoStack.length > 0,
    openFromGrid,
    skip,
    undo,
    committed,
    commitFailed,
    deselect,
  }
}
