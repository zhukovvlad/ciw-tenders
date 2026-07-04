// frontend/src/pages/estimate/ReviewScreen.tsx
import { useRef } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { ArrowLeft, Check, Download } from "lucide-react"
import type { MatchRow, ReviewState } from "@/lib/types"
import { type ReviewAction, decisionFor, progress } from "@/lib/reviewState"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { ReviewCard, hasRecommendation } from "@/pages/estimate/ReviewCard"
import { ContextStrip } from "@/pages/estimate/ContextStrip"
import { ReviewGrid } from "@/pages/estimate/ReviewGrid"
import { QueueDone } from "@/pages/estimate/QueueDone"
import { useReviewQueue } from "@/lib/useReviewQueue"
import { useReviewKeyboard } from "@/lib/useReviewKeyboard"
import { pluralizeRu } from "@/lib/plural"

export type ReviewActionKind = "confirm" | "pick" | "reject"

interface ReviewScreenProps {
  state: ReviewState
  dispatch: React.Dispatch<ReviewAction>
  onExport: () => void
  onComplete: () => void
  /** Коммит на бэк; резолвится true=сохранено / false=ошибка (откат+toast сделал вызывающий) */
  onReview?: (
    rowNumber: number,
    action: ReviewActionKind,
    articleId?: number
  ) => Promise<boolean>
  /** Завершённая смета + ?view=grid: только грид, клики и решение выключены */
  readOnly?: boolean
  /**
   * ТЕСТОВЫЙ проп: под vitest (jsdom) ResizeObserver — no-op заглушка
   * (см. src/test/setup.ts), и виртуализатор ReviewGrid с нулевым rect не
   * отрисовывает ни одной строки (проверено эмпирически при разработке
   * Task 9). В production не передаётся: реальный ResizeObserver измеряет
   * контейнер сразу после монтирования, initialRect не нужен. Явное
   * значение здесь имеет приоритет над авто-дефолтом для vitest ниже.
   */
  gridInitialRect?: { width: number; height: number }
}

// Дефолт для интеграционных тестов экрана (jsdom): включается только под
// vitest (import.meta.env.MODE === "test"), в собранном приложении остаётся
// undefined — ReviewGrid не подменяет observeElementRect и слушает реальный
// ResizeObserver (см. комментарий у gridInitialRect выше).
const TEST_GRID_RECT = { width: 1024, height: 600 }

export function ReviewScreen({
  state,
  dispatch,
  onExport,
  onComplete,
  onReview,
  readOnly = false,
  gridInitialRect,
}: ReviewScreenProps) {
  const [searchParams, setSearchParams] = useSearchParams()
  const view: "queue" | "grid" =
    readOnly || searchParams.get("view") === "grid" ? "grid" : "queue"

  const queue = useReviewQueue(state)
  const active = queue.activeRow

  // Переживает переключение режимов очередь↔грид (спека §3c): «к таблице»
  // возвращает на позицию скролла.
  const scrollOffsetRef = useRef<number | null>(null)

  const switchToGrid = () =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set("view", "grid")
      return next
    })

  const switchToQueue = () =>
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete("view")
      return next
    })

  // Ручной уход в грид (таб или «Посмотреть таблицу») обязан сбросить явный
  // выбор — иначе, вернувшись в очередь, оператор увидит давно открытую из
  // грида карточку вместо потока. Программный уход после коммита
  // (exit.kind === "grid") deselect НЕ зовёт — selection уже сброшен самим
  // queue.committed().
  const goToGridManually = () => {
    queue.deselect()
    switchToGrid()
  }

  const commit = (
    row: MatchRow,
    action: ReviewAction,
    kind: ReviewActionKind,
    articleId?: number
  ) => {
    dispatch(action)
    const exit = queue.committed(row.row_number)
    if (exit.kind === "grid") switchToGrid()
    const p = onReview?.(row.row_number, kind, articleId)
    if (p)
      void p.then((ok) => {
        if (!ok) queue.commitFailed(row.row_number)
      })
  }

  useReviewKeyboard({
    enabled: view === "queue" && !readOnly && active !== null,
    candidateCount: active?.candidates.length ?? 0,
    canConfirm: active ? hasRecommendation(active) : false,
    onPick: (i) => {
      const c = active?.candidates[i]
      if (active && c)
        commit(
          active,
          {
            type: "pickCandidate",
            row: active.row_number,
            code: c.article_code,
          },
          "pick",
          c.id ?? undefined
        )
    },
    onConfirm: () => {
      if (active)
        commit(
          active,
          { type: "confirmArbiter", row: active.row_number },
          "confirm"
        )
    },
    onNext: () => {
      // N = пропустить; для ad-hoc строки из грида skip возвращает выход по
      // происхождению — обрабатываем так же, как committed
      const exit = queue.skip()
      if (exit.kind === "grid") switchToGrid()
    },
    onReject: () => {
      if (active)
        commit(
          active,
          { type: "confirmNoMatch", row: active.row_number },
          "reject"
        )
    },
    onUndo: queue.undo,
  })

  const { reviewed, total } = progress(state)
  const pending = total - reviewed

  const effectiveGridRect =
    gridInitialRect ??
    (import.meta.env.MODE === "test" ? TEST_GRID_RECT : undefined)

  // Спека §3c: грид открытый впервые (в очередь вошли не из него, скролл
  // ещё не запоминался) — скроллит к активной строке; «к таблице» после
  // скролла — к запомненной позиции. Читаем ref во время рендера сознательно
  // (см. аналогичный паттерн и обоснование в lib/useReviewQueue.ts): значение
  // меняется только синхронно с onScroll в самом ReviewGrid, а ReviewGrid
  // использует его лишь в эффекте на монтаж — устаревшего вывода не бывает.
  /* eslint-disable react-hooks/refs -- см. комментарий выше; блочный disable,
     т.к. Prettier переносит строки внутри тернарника и next-line не попадает
     на нужную строку после форматирования */
  const focusRowNumber =
    scrollOffsetRef.current === null
      ? (queue.activeRow?.row_number ?? null)
      : null
  /* eslint-enable react-hooks/refs */

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--ds-hairline)] px-4 py-3">
        <span className="text-sm">{state.fileName}</span>
        <span className="text-xs text-muted-foreground">
          · спорных решено {reviewed} из {total}
        </span>

        {!readOnly && (
          <Tabs
            value={view}
            onValueChange={(v) =>
              v === "grid" ? goToGridManually() : switchToQueue()
            }
          >
            <TabsList>
              <TabsTrigger value="queue">Очередь</TabsTrigger>
              <TabsTrigger value="grid">Таблица</TabsTrigger>
            </TabsList>
          </Tabs>
        )}

        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" size="sm" asChild>
            <Link to="/estimates">
              <ArrowLeft className="size-4" />
              Ко всем сметам
            </Link>
          </Button>
          <Button size="sm" variant="outline" onClick={onExport}>
            <Download className="size-4" />
            Выгрузить Excel
          </Button>
          {!readOnly &&
            (pending === 0 ? (
              <Button size="sm" onClick={onComplete}>
                <Check className="size-4" />
                Завершить
              </Button>
            ) : (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  {/* Демоушен (спека 3.5 §2): primary «загорается» при pending === 0 —
                      кнопка не приглашает, пока по нажатию ругается диалогом */}
                  <Button size="sm" variant="outline">
                    <Check className="size-4" />
                    Завершить
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      Остались нерешённые строки
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      Без решения — {pending}{" "}
                      {pluralizeRu(pending, [
                        "спорная строка",
                        "спорные строки",
                        "спорных строк",
                      ])}
                      . Завершить всё равно? Возобновить можно в любой момент.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Отмена</AlertDialogCancel>
                    <AlertDialogAction onClick={onComplete}>
                      Завершить всё равно
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            ))}
        </div>
      </div>

      {view === "grid" ? (
        <ReviewGrid
          state={state}
          dispatch={dispatch}
          onOpenRow={
            readOnly
              ? undefined
              : (n) => {
                  queue.openFromGrid(n)
                  switchToQueue()
                }
          }
          scrollOffsetRef={scrollOffsetRef}
          focusRowNumber={focusRowNumber}
          initialRect={effectiveGridRect}
        />
      ) : active === null ? (
        <QueueDone
          state={state}
          onComplete={onComplete}
          onShowGrid={goToGridManually}
          canUndo={queue.canUndo}
          onUndo={queue.undo}
        />
      ) : (
        <div
          data-testid="decision-zone"
          className="mx-auto w-full max-w-[68rem] px-4 py-4"
        >
          <ReviewCard
            key={active.row_number}
            row={active}
            decision={decisionFor(state, active)}
            canUndo={queue.canUndo}
            contextStrip={
              <ContextStrip state={state} activeRowNumber={active.row_number} />
            }
            onConfirmRecommendation={() =>
              commit(
                active,
                { type: "confirmArbiter", row: active.row_number },
                "confirm"
              )
            }
            onPickCandidate={(c) =>
              commit(
                active,
                {
                  type: "pickCandidate",
                  row: active.row_number,
                  code: c.article_code,
                },
                "pick",
                c.id ?? undefined
              )
            }
            onManualPick={(c) =>
              commit(
                active,
                {
                  type: "manualPick",
                  row: active.row_number,
                  candidate: c,
                },
                "pick",
                c.id ?? undefined
              )
            }
            onReject={() =>
              commit(
                active,
                { type: "confirmNoMatch", row: active.row_number },
                "reject"
              )
            }
          />
        </div>
      )}
    </div>
  )
}
