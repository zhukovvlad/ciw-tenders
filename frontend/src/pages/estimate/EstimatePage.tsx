// frontend/src/pages/estimate/EstimatePage.tsx
// Единственный владелец маппинга статус→экран (спека §3). Кэша ревью нет:
// источник истины — GET /estimates/:id + ответы PATCH.
import { useCallback, useEffect, useReducer, useRef, useState } from "react"
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom"
import { toast } from "sonner"
import type { Progress } from "@/lib/mock/api"
import type { StructuralAnomaly } from "@/lib/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { StructureNotice } from "@/components/estimate/StructureNotice"
import { initReview, reviewReducer } from "@/lib/reviewState"
import type { ReviewActionKind } from "@/pages/estimate/ReviewScreen"
import {
  exportEstimate,
  getEstimate,
  patchRowReview,
  pollEstimate,
  setCompletion,
} from "@/lib/api/estimates"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { DoneScreen } from "@/pages/estimate/DoneScreen"

interface NoticeState {
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

type Meta =
  | { kind: "loading" }
  | { kind: "processing" }
  | { kind: "blocked"; detail: string | null }
  | { kind: "open" }
  | { kind: "completed" }
  | { kind: "error"; message: string }

// pollEstimate реджектится DOMException('AbortError') при отмене через signal —
// такая отмена не ошибка, её нужно проглатывать молча (не показывать алерт).
function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError"
}

export function EstimatePage() {
  const params = useParams()
  const id = Number(params.id)
  const location = useLocation()
  const [searchParams] = useSearchParams()
  // Транзиентная справка по аномалиям: приходит только через navigate-state
  // при свежей загрузке; при прямом заходе по URL её нет (спека §5, этап 3).
  const notice = (location.state ?? {
    anomalies: [],
    outlineOverrides: 0,
  }) as NoticeState

  const [meta, setMeta] = useState<Meta>({ kind: "loading" })
  const [fileName, setFileName] = useState("")
  const [isReference, setIsReference] = useState(false)
  const [prog, setProg] = useState<Progress>({
    phase: "parsing",
    done: 0,
    total: 0,
    etaSeconds: null,
  })
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("", [])
  )
  // Отменяет предыдущий незавершённый load() при смене :id без ремаунта
  // (React переиспользует компонент — эффект без этого гонялся бы конкурентно
  // со старым запросом/поллингом и мог перезаписать состояние актуального id).
  const loadAbortRef = useRef<AbortController | null>(null)

  const load = useCallback(async () => {
    loadAbortRef.current?.abort()
    const controller = new AbortController()
    loadAbortRef.current = controller
    const { signal } = controller
    setMeta({ kind: "loading" })
    try {
      const detail = await getEstimate(id)
      if (signal.aborted) return
      setFileName(detail.fileName)
      setIsReference(detail.isReference)
      if (detail.status === "blocked") {
        setMeta({ kind: "blocked", detail: detail.statusDetail })
        return
      }
      if (detail.status === "pending" || detail.status === "running") {
        setMeta({ kind: "processing" })
        try {
          const { fileName: fn, rows } = await pollEstimate(
            id,
            (status, done, total) => {
              if (signal.aborted) return
              setProg({
                phase: status === "running" ? "matching" : "parsing",
                done,
                total,
                etaSeconds: null,
              })
            },
            1500,
            { signal }
          )
          if (signal.aborted) return
          dispatch({
            type: "load",
            state: initReview(fn || detail.fileName, rows),
          })
          setMeta({ kind: "open" })
        } catch (pollErr) {
          if (signal.aborted || isAbortError(pollErr)) return
          // Смета может уйти в blocked ВО ВРЕМЯ поллинга (напр., нет строк СМР):
          // pollEstimate реджектится generic-ошибкой без statusDetail.
          // Перечитываем статус один раз, чтобы показать честный алерт отказа.
          const fresh = await getEstimate(id) // упадёт — поймает внешний catch
          if (signal.aborted) return
          if (fresh.status === "blocked") {
            setMeta({ kind: "blocked", detail: fresh.statusDetail })
            return
          }
          throw pollErr
        }
        return
      }
      dispatch({
        type: "load",
        state: initReview(detail.fileName, detail.rows),
      })
      setMeta(
        detail.completedAt !== null ? { kind: "completed" } : { kind: "open" }
      )
    } catch (err) {
      if (signal.aborted || isAbortError(err)) return
      console.error(err)
      setMeta({
        kind: "error",
        message:
          err instanceof Error ? err.message : "Не удалось открыть смету",
      })
    }
  }, [id])

  useEffect(() => {
    // IIFE, а не прямой void load(): eslint (react-hooks/set-state-in-effect)
    // иначе считает setMeta внутри load() синхронным вызовом прямо в эффекте.
    void (async () => {
      if (Number.isInteger(id)) await load()
    })()
    return () => {
      loadAbortRef.current?.abort()
    }
  }, [id, load])

  function handleReview(
    rowNumber: number,
    action: ReviewActionKind,
    articleId?: number
  ): Promise<boolean> {
    const prev = state.rows.find((r) => r.row_number === rowNumber)
    return patchRowReview(id, rowNumber, action, articleId, prev)
      .then((updated) => {
        dispatch({ type: "syncRow", row: updated })
        return true
      })
      .catch((err: unknown) => {
        console.error(err)
        dispatch({ type: "reopen", row: rowNumber })
        // Текст нейтральный: «возвращена в начало очереди» была бы ложью для
        // confident-строки из грида (она не в очереди спорных — commitFailed
        // порядок для неё не трогает). Имя строки — требование спеки §3a.
        toast.error(
          `Не удалось сохранить решение по строке «${prev?.source_name ?? rowNumber}»`
        )
        return false
      })
  }

  async function handleExport() {
    try {
      const blob = await exportEstimate(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${fileName.replace(/\.[^.]+$/, "")}_сопоставлено.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : "Экспорт не удался")
    }
  }

  function toggleCompletion(completed: boolean) {
    setCompletion(id, completed)
      .then(({ completedAt }) =>
        setMeta(completedAt !== null ? { kind: "completed" } : { kind: "open" })
      )
      .catch((err: unknown) => {
        console.error(err)
        toast.error(
          err instanceof Error
            ? err.message
            : "Не удалось изменить статус сметы"
        )
      })
  }

  if (!Number.isInteger(id)) return <NotFound />
  if (meta.kind === "loading")
    return (
      <div className="space-y-2 p-8" aria-label="Загрузка">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  if (meta.kind === "processing")
    return <ProcessingScreen fileName={fileName} progress={prog} />
  if (meta.kind === "blocked" || meta.kind === "error")
    return (
      <div className="p-8">
        <Alert variant="destructive" role="alert">
          <AlertTitle>
            {meta.kind === "blocked" ? "Смета отклонена" : "Ошибка"}
          </AlertTitle>
          <AlertDescription>
            {meta.kind === "blocked" ? (meta.detail ?? "—") : meta.message}
          </AlertDescription>
        </Alert>
        <Link className="mt-4 inline-block text-sm underline" to="/estimates">
          ← Ко всем сметам
        </Link>
      </div>
    )
  if (meta.kind === "completed") {
    // Фаза сметы (completed) серверная и главнее режима (спека §3c): переход
    // в read-only грид — только через явный ?view=grid (кнопка DoneScreen или
    // прямая ссылка); сама completed-ветка ?view=grid не порождает.
    if (searchParams.get("view") === "grid")
      return (
        <ReviewScreen
          state={state}
          dispatch={dispatch}
          onExport={() => void handleExport()}
          onComplete={() => {}}
          readOnly
        />
      )
    return (
      <DoneScreen
        state={state}
        estimateId={id}
        isReference={isReference}
        onReferenceChange={setIsReference}
        onExport={() => void handleExport()}
        onResume={() => toggleCompletion(false)}
      />
    )
  }
  return (
    <>
      <StructureNotice
        anomalies={notice.anomalies}
        outlineOverrides={notice.outlineOverrides}
      />
      <ReviewScreen
        state={state}
        dispatch={dispatch}
        onExport={() => void handleExport()}
        onComplete={() => toggleCompletion(true)}
        onReview={handleReview}
      />
    </>
  )
}

function NotFound() {
  return (
    <div className="p-8">
      <Alert variant="destructive" role="alert">
        <AlertTitle>Смета не найдена</AlertTitle>
      </Alert>
      <Link className="mt-4 inline-block text-sm underline" to="/estimates">
        ← Ко всем сметам
      </Link>
    </div>
  )
}
