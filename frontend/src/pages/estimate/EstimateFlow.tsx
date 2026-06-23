// frontend/src/pages/estimate/EstimateFlow.tsx
import { useEffect, useReducer, useRef, useState } from "react"
import { toast } from "sonner"
import type { Progress } from "@/lib/mock/api"
import {
  exportEstimate,
  patchRowReview,
  pollEstimate,
  uploadEstimate,
} from "@/lib/api/estimates"
import { initReview, progress, reviewReducer } from "@/lib/reviewState"
import type { ReviewActionKind } from "@/pages/estimate/ReviewScreen"
import {
  clearReview,
  loadEstimateId,
  loadReview,
  saveEstimateId,
  saveReview,
} from "@/lib/session"
import { StartScreen } from "@/pages/estimate/StartScreen"
import { ProcessingScreen } from "@/pages/estimate/ProcessingScreen"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { DoneScreen } from "@/pages/estimate/DoneScreen"

type Phase = "start" | "processing" | "review" | "done"

export function EstimateFlow() {
  const [phase, setPhase] = useState<Phase>(() =>
    loadReview() ? "review" : "start"
  )
  const [fileName, setFileName] = useState<string>(
    () => loadReview()?.fileName ?? ""
  )
  const [prog, setProg] = useState<Progress>({
    phase: "parsing",
    done: 0,
    total: 0,
    etaSeconds: null,
  })
  const [state, dispatch] = useReducer(
    reviewReducer,
    undefined,
    () => loadReview() ?? initReview("", [])
  )
  // id сметы для коммита решений (PATCH) и экспорта; регидратируется из сессии
  const estimateIdRef = useRef<number | null>(loadEstimateId())

  // персист ревью на каждое изменение
  useEffect(() => {
    if (phase === "review" || phase === "done") saveReview(state)
  }, [state, phase])

  // guard от случайного ухода с незавершённой проверкой
  useEffect(() => {
    const { reviewed, total } = progress(state)
    if (phase !== "review" || reviewed >= total) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
      e.returnValue = ""
    }
    window.addEventListener("beforeunload", handler)
    return () => window.removeEventListener("beforeunload", handler)
  }, [phase, state])

  async function handleFile(file: File) {
    setFileName(file.name)
    setPhase("processing")
    try {
      // SP1: upload → get id, then poll until ready
      const id = await uploadEstimate(file)
      estimateIdRef.current = id
      saveEstimateId(id)
      setProg({ phase: "parsing", done: 0, total: 0, etaSeconds: null })

      const { fileName: serverFileName, rows } = await pollEstimate(
        id,
        (status, done, total) => {
          const mappedPhase: Progress["phase"] =
            status === "running" ? "matching" : "parsing"
          setProg({ phase: mappedPhase, done, total, etaSeconds: null })
        }
      )

      const fresh = initReview(serverFileName || file.name, rows)
      dispatch({ type: "load", state: fresh })
      saveReview(fresh)
      setPhase("review")
    } catch (err) {
      console.error(err)
      toast.error(
        err instanceof Error ? err.message : "Не удалось обработать смету"
      )
      setPhase("start")
    }
  }

  function handleNew() {
    estimateIdRef.current = null
    clearReview()
    setFileName("")
    setPhase("start")
  }

  async function handleExport() {
    const id = estimateIdRef.current
    if (id === null) {
      toast.error("Не удалось определить смету для экспорта")
      return
    }
    try {
      const blob = await exportEstimate(id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${fileName.replace(/\.[^.]+$/, "")}_сопоставлено.xlsx`
      a.click()
      URL.revokeObjectURL(url)
      setPhase("done")
    } catch (err) {
      console.error(err)
      toast.error(err instanceof Error ? err.message : "Экспорт не удался")
    }
  }

  // Коммит решения на бэк: PATCH .../review, затем синхронизация строки из
  // авторитетного ответа (с замороженными final_*). При ошибке — откат строки
  // в pending, чтобы не оставить её в полу-обновлённом виде.
  function handleReview(
    rowNumber: number,
    action: ReviewActionKind,
    articleId?: number
  ) {
    const id = estimateIdRef.current
    if (id === null) return
    void patchRowReview(id, rowNumber, action, articleId)
      .then((updated) => {
        dispatch({ type: "syncRow", row: updated })
      })
      .catch((err: unknown) => {
        console.error(err)
        dispatch({ type: "reopen", row: rowNumber })
        toast.error(
          err instanceof Error ? err.message : "Не удалось сохранить решение"
        )
      })
  }

  if (phase === "start") return <StartScreen onFile={handleFile} />
  if (phase === "processing")
    return <ProcessingScreen fileName={fileName} progress={prog} />
  if (phase === "done")
    return (
      <DoneScreen
        state={state}
        onExport={handleExport}
        onNewEstimate={handleNew}
      />
    )
  return (
    <ReviewScreen
      state={state}
      dispatch={dispatch}
      onExport={handleExport}
      onNewEstimate={handleNew}
      onReview={handleReview}
    />
  )
}
