// frontend/src/pages/estimate/EstimateFlow.tsx
import { useEffect, useReducer, useRef, useState } from "react"
import { toast } from "sonner"
import type { Progress } from "@/lib/mock/api"
import {
  exportEstimate,
  getEstimate,
  patchRowReview,
  pollEstimate,
  uploadEstimate,
} from "@/lib/api/estimates"
import type { EstimateListItem } from "@/lib/api/estimates"
import type { StructuralAnomaly } from "@/lib/types"
import { StructureNotice } from "@/components/estimate/StructureNotice"
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

interface StructureNoticeState {
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

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
  // Транзиентная справка по аномалиям структуры: заполняется при загрузке,
  // сбрасывается при «новой смете». Не персистируется (при перезагрузке теряется).
  const [structureNotice, setStructureNotice] = useState<StructureNoticeState>({
    anomalies: [],
    outlineOverrides: 0,
  })

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
    setStructureNotice({ anomalies: [], outlineOverrides: 0 })
    try {
      // SP1: upload → get id, then poll until ready
      const { id, anomalies, outlineOverrides } = await uploadEstimate(file)
      estimateIdRef.current = id
      saveEstimateId(id)
      setStructureNotice({ anomalies, outlineOverrides })
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

  // Открыть ранее разобранную смету из списка. Готовые (ready/partial_error) —
  // сразу в review; ещё считающиеся (pending/running) — в processing с
  // возобновлением poll. blocked сюда не приходит (некликабелен в списке).
  async function handleOpen(item: EstimateListItem) {
    estimateIdRef.current = item.id
    saveEstimateId(item.id)
    setFileName(item.filename)
    // Аномалии — транзиентная справка по конкретной загрузке; GET /estimates/{id}
    // их не возвращает. При открытии из истории чистим справку, иначе блок от
    // предыдущей загрузки протёк бы над только что открытой сметой (обе ветки ниже).
    setStructureNotice({ anomalies: [], outlineOverrides: 0 })

    if (item.status === "pending" || item.status === "running") {
      setPhase("processing")
      setProg({ phase: "parsing", done: 0, total: 0, etaSeconds: null })
      try {
        const { fileName: serverFileName, rows } = await pollEstimate(
          item.id,
          (status, done, total) => {
            const mappedPhase: Progress["phase"] =
              status === "running" ? "matching" : "parsing"
            setProg({ phase: mappedPhase, done, total, etaSeconds: null })
          }
        )
        const fresh = initReview(serverFileName || item.filename, rows)
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
      return
    }

    try {
      const { fileName: serverFileName, rows } = await getEstimate(item.id)
      const fresh = initReview(serverFileName || item.filename, rows)
      dispatch({ type: "load", state: fresh })
      saveReview(fresh)
      setPhase("review")
    } catch (err) {
      console.error(err)
      toast.error(
        err instanceof Error ? err.message : "Не удалось открыть смету"
      )
      setPhase("start")
    }
  }

  function handleNew() {
    estimateIdRef.current = null
    clearReview()
    setFileName("")
    setStructureNotice({ anomalies: [], outlineOverrides: 0 })
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
    if (id === null) {
      // ReviewScreen уже применил оптимистичное решение — откатываем, иначе строка
      // покажется сохранённой, не уехав на бэк.
      dispatch({ type: "reopen", row: rowNumber })
      toast.error("Не удалось определить смету — решение не сохранено")
      return
    }
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

  if (phase === "start")
    return <StartScreen onFile={handleFile} onOpen={handleOpen} />
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
    <>
      <StructureNotice
        anomalies={structureNotice.anomalies}
        outlineOverrides={structureNotice.outlineOverrides}
      />
      <ReviewScreen
        state={state}
        dispatch={dispatch}
        onExport={handleExport}
        onNewEstimate={handleNew}
        onReview={handleReview}
      />
    </>
  )
}
