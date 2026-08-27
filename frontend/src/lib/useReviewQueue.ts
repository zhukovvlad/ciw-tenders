// Сессионный (in-memory) слой навигации очереди ревью — спека этапа 2 §3a.
// reviewState НЕ трогает: решения остаются зеркалом сервера; здесь живёт только
// порядок/активная/undo текущей сессии (F5 всё сбрасывает — это by design).
import { useMemo, useRef, useState } from "react"
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
  navigateTo: (rowNumber: number) => void
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
  const [undoStack, setUndoStack] = useState<number[]>([])
  const [selection, setSelection] = useState<Selection | null>(null)
  // Позиция скраббера: sourceIndex последней обработанной строки. Следующая
  // активная — первая нерешённая СТРОГО ПОСЛЕ неё по порядку документа, с
  // обёрткой к самой ранней. null — сессия только началась, ищем с начала.
  // Заменяет прежнее переупорядочивание order: оператор движется в одном
  // направлении по смете, а полоса лишь переставляет точку продолжения.
  const [position, setPosition] = useState<number | null>(null)
  // Инвариант PR-B «ошибка PATCH → строка становится следующей». Позиции для
  // этого мало: commitFailed пиннит оператора на строке, которую он решает
  // сейчас, а её committed перезапишет позицию на «после себя» — откатившаяся
  // (она обычно раньше по документу) снова уехала бы в хвост. Поэтому
  // отдельный список, проверяемый ПЕРЕД позицией.
  // Именно СПИСОК, не одиночный слот: два PATCH-а бывают in-flight и падают
  // оба — слот затёр бы первую откатившуюся строку, а прежний order держал
  // обе. Порядок «последний откат первым», как делало [rowNumber, ...rest].
  const [priorities, setPriorities] = useState<number[]>([])
  // Решённые В ЭТОЙ СЕССИИ (оптимистично, до/независимо от ответа PATCH):
  // decisionFor обновится только после dispatch снаружи — хук не ждёт этого.
  // Именно МНОЖЕСТВО, не undoStack: стек — мультисет (повторный коммит той же
  // строки из грида кладёт её дважды), и после commitFailed, снявшего одно
  // вхождение, строка осталась бы «решённой» по стеку — потерянное решение.
  const sessionDecided = useRef<Set<number>>(new Set())

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
    setUndoStack([])
    setSelection(null)
    setPosition(null)
    setPriorities([])
    // Сброс сессии — мутировать ref во время рендера здесь безопасно: ветка
    // выполняется однократно на смену набора и не участвует в выводе JSX.
    // eslint-disable-next-line react-hooks/refs
    sessionDecided.current = new Set()
  }

  const byNum = useMemo(
    () => new Map(state.rows.map((r) => [r.row_number, r])),
    [state.rows]
  )

  // Очередь спорных в порядке документа. НЕИЗМЕНЯЕМА: в позиционной модели ни
  // skip, ни commitFailed её не переупорядочивают — «следующую» задают
  // position/priorities, а не порядок массива.
  const queue = useMemo(
    () =>
      state.rows
        .filter(requiresDecision)
        .sort((a, b) => a.sourceIndex - b.sourceIndex),
    [state.rows]
  )

  // Чтение sessionDecided во время рендера сознательно: набор меняется только
  // синхронно с setState (committed/undo/commitFailed всегда двигают undoStack),
  // так что за мутацией ref-а всегда следует ре-рендер — устаревшего вывода
  // не бывает. Полноценный useState здесь дал бы лишний рендер на каждый коммит.
  const isPending = (r: MatchRow) =>
    decisionFor(state, r).kind === "pending" &&
    !sessionDecided.current.has(r.row_number)

  // eslint-disable-next-line react-hooks/refs -- см. комментарий у sessionDecided/isPending
  const pending = queue.filter(isPending)

  const nextByPosition = (): MatchRow | null => {
    if (pending.length === 0) return null
    if (position === null) return pending[0]
    // Обёртка к самой ранней нерешённой, если впереди по документу пусто.
    return pending.find((r) => r.sourceIndex > position) ?? pending[0]
  }

  // Откаты PATCH идут ПЕРЕД позицией. Берём первый ещё нерешённый: список
  // упорядочен «последний откат первым», а не-pending элементы просто
  // пропускаются, поэтому чистить его обязательно не нужно.
  const priorityRow =
    priorities
      .map((n) => byNum.get(n))
      .find((r): r is MatchRow => r !== undefined && pending.includes(r)) ??
    null

  const autoActive = priorityRow ?? nextByPosition()

  const activeRow = selection ? (byNum.get(selection.row) ?? null) : autoActive
  const origin: CardOrigin = selection?.origin ?? { kind: "flow" }

  // Свежая активная для АСИНХРОННЫХ вызовов (commitFailed из .then PATCH-а):
  // замыкание там — из рендера до committed(), где активной была сама упавшая
  // строка; читать её из замыкания нельзя (пин-тест «STALE CLOSURE»).
  // Запись — ИМЕННО во время рендера, не в useEffect: пассивный эффект
  // флашится отдельной задачей и микротаск .then упавшего PATCH-а может успеть
  // раньше — ref в этот момент ещё показывал бы саму упавшую строку, пиннинг
  // не сработал бы и оператора выдернуло бы назад (запрещено спекой §3a).
  const activeRowRef = useRef(activeRow)
  // eslint-disable-next-line react-hooks/refs
  activeRowRef.current = activeRow

  const exitFor = (o: CardOrigin): CommitExit =>
    o.kind === "grid"
      ? { kind: "grid" }
      : o.kind === "undo" && o.returnTo !== null
        ? { kind: "row", rowNumber: o.returnTo }
        : { kind: "next" }

  const openFromGrid = (rowNumber: number) =>
    setSelection({ row: rowNumber, origin: { kind: "grid" } })

  // Скраббер: клик по строке окружения. От openFromGrid отличается только
  // origin — после решения оператор продолжает поток от этой позиции, а не
  // возвращается в грид. В undo-стек не пишется: навигация ≠ решение.
  const navigateTo = (rowNumber: number) =>
    setSelection({ row: rowNumber, origin: { kind: "flow" } })

  // Позиция = sourceIndex обработанной строки; следующая ищется строго после.
  const advanceFrom = (rowNumber: number) => {
    const si = byNum.get(rowNumber)?.sourceIndex
    if (si !== undefined) setPosition(si)
  }

  const deselect = () => setSelection(null)

  const skip = (): CommitExit => {
    const n = activeRow?.row_number
    if (n === undefined) return { kind: "next" }
    // N = «пропустить», поэтому строка выходит из приоритетов: иначе приоритет
    // (он проверяется раньше позиции) вернул бы её тем же рендером и оператор
    // залип бы на ней. Строка остаётся нерешённой и подхватится обёрткой.
    setPriorities((p) => p.filter((x) => x !== n))
    if (!queue.some((r) => r.row_number === n)) {
      // Ad-hoc строка (confident/фонд): «пропустить» = передумал — уходим
      // туда, откуда пришли.
      const exit = exitFor(origin)
      if (exit.kind === "row")
        setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
      else setSelection(null)
      // Позицию двигаем ТОЛЬКО если пришли потоком/полосой: тогда оператор
      // движется по документу и ждёт продолжения после этой строки. Из грида
      // (origin=grid) выход возвращает в таблицу, а undo — это отступление;
      // в обоих случаях трогать позицию потока нельзя.
      if (origin.kind === "flow") advanceFrom(n)
      return exit
    }
    // Пропущенная строка остаётся нерешённой на своём месте в порядке
    // документа и подхватится обёрткой в конце прохода — переупорядочивать
    // очередь больше не нужно.
    advanceFrom(n)
    setSelection(null)
    return { kind: "next" }
  }

  const undo = () => {
    if (undoStack.length === 0) return
    const top = undoStack[undoStack.length - 1]
    const returnTo = activeRow?.row_number ?? null
    setUndoStack((s) => s.slice(0, -1))
    sessionDecided.current.delete(top) // строка снова «в работе»
    setSelection({ row: top, origin: { kind: "undo", returnTo } })
  }

  const committed = (rowNumber: number): CommitExit => {
    setUndoStack((s) => [...s, rowNumber])
    sessionDecided.current.add(rowNumber)
    // Решена — приоритет больше не нужен (фильтр по pending в autoActive и так
    // бы её пропустил, но не копим мусор в списке).
    setPriorities((p) => p.filter((x) => x !== rowNumber))
    const exit = exitFor(origin)
    if (exit.kind === "row")
      setSelection({ row: exit.rowNumber, origin: { kind: "flow" } })
    else {
      // Позицию двигаем ТОЛЬКО при origin=flow — тот же гейт, что и в skip.
      // exit.kind тут "next" или "grid"; "grid" бывает исключительно при
      // origin=grid и уже отсекается условием, но exit.kind==="next" также
      // достижим из origin=undo (returnTo===null) — а undo это отступление,
      // не проход по документу, и позицию потока трогать нельзя: иначе после
      // решения строки из грида (или после отступления) оператор при
      // возврате в поток «прыгнет» на sourceIndex этой строки вместо того,
      // чтобы продолжить с места, где был до захода туда.
      if (origin.kind === "flow") advanceFrom(rowNumber)
      setSelection(null)
    }
    return exit
  }

  const commitFailed = (rowNumber: number) => {
    setUndoStack((s) => {
      const i = s.lastIndexOf(rowNumber)
      return i === -1 ? s : [...s.slice(0, i), ...s.slice(i + 1)]
    })
    sessionDecided.current.delete(rowNumber)
    // Откатившаяся строка — следующая, как только оператор закончит текущую.
    // Добавляем В ГОЛОВУ и НЕ затираем прежние: два in-flight PATCH-а могут
    // упасть оба, и терять первую откатившуюся строку нельзя.
    setPriorities((p) => [rowNumber, ...p.filter((x) => x !== rowNumber)])
    // Не выдёргивать оператора из текущей строки: пиннуть её, если явного
    // выбора не было.
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
    navigateTo,
    skip,
    undo,
    committed,
    commitFailed,
    deselect,
  }
}
