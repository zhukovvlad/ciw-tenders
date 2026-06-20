// frontend/src/pages/estimate/EstimateFlow.tsx
import { useEffect, useReducer, useState } from "react"
import type { Progress } from "@/lib/mock/api"
import { downloadCsv, exportEstimateCsv, matchEstimate } from "@/lib/mock/api"
import { initReview, progress, reviewReducer } from "@/lib/reviewState"
import { clearReview, loadReview, saveReview } from "@/lib/session"
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
    const rows = await matchEstimate(file, setProg)
    // Чистая загрузка нового состояния в reducer (без мутаций): action "load" из Task 5.
    const fresh = initReview(file.name, rows)
    dispatch({ type: "load", state: fresh })
    saveReview(fresh)
    setPhase("review")
  }

  function handleNew() {
    clearReview()
    setFileName("")
    setPhase("start")
  }

  function handleExport() {
    downloadCsv(
      `${fileName.replace(/\.[^.]+$/, "")}_сопоставлено.csv`,
      exportEstimateCsv(state)
    )
    setPhase("done")
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
    />
  )
}
