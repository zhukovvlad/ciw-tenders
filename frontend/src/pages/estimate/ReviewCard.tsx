import { type ReactNode, useEffect, useRef, useState } from "react"
import { Database } from "lucide-react"
import type { Candidate, Decision, MatchRow } from "@/lib/types"
import { searchArticles } from "@/lib/api/articles"
import { CrumbTrail } from "@/components/estimate/CrumbTrail"
import { Card, CardContent } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"

const DEFAULT_SEARCH_DEBOUNCE_MS = 250

interface ReviewCardProps {
  row: MatchRow
  decision: Decision // подсветка выбранного (перерешение открытой из грида/после ←)
  canUndo: boolean // легенда: ← приглушена на пустом стеке
  onConfirmRecommendation: () => void // Enter
  onPickCandidate: (c: Candidate) => void // 1–3
  onManualPick: (c: Candidate) => void // выбор из поиска
  onReject: () => void // 0 — оставить без пары
  searchDebounceMs?: number // default 250; тесты передают 0
  contextStrip?: ReactNode // полоса окружения (спека 3.5 §3 п.2): карточка не знает о ревью-стейте
}

/** Enter активен ⇔ блок рекомендации отрисован (правило: клавиша ⇔ элемент) */
// eslint-disable-next-line react-refresh/only-export-components -- hasRecommendation — гейт-хелпер, используемый экраном ревью (Task 9)
export function hasRecommendation(row: MatchRow): boolean {
  return (
    row.status !== "error" &&
    row.matched_code !== null &&
    row.matched_name !== null
  )
}

const candidateButtonClass =
  "mb-1.5 flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm"

export function ReviewCard({
  row,
  decision,
  canUndo,
  onConfirmRecommendation,
  onPickCandidate,
  onManualPick,
  onReject,
  searchDebounceMs = DEFAULT_SEARCH_DEBOUNCE_MS,
  contextStrip,
}: ReviewCardProps) {
  const [query, setQuery] = useState("")
  const [hits, setHits] = useState<Candidate[]>([])
  const recommended = hasRecommendation(row)
  // no_match (реджект, в т.ч. переоткрытый из грида) — ни один кандидат не
  // подсвечен; pending — донный кейс, пре-подсветка рекомендации остаётся.
  const chosenCode =
    decision.kind === "confirmed"
      ? decision.code
      : decision.kind === "no_match"
        ? null
        : row.matched_code
  const rejectSelected = decision.kind === "no_match"
  // Гейт синтетической рекомендации (перенесено из ReviewRow без изменений):
  // отдельный блок рендерится, только если matched_code не входит в
  // candidates — иначе рекомендация это уже подсвеченный кандидат ниже.
  const syntheticRecommendation =
    recommended &&
    !row.candidates.some((c) => c.article_code === row.matched_code)

  // Дебаунс поиска (~250мс): не дёргаем /articles/search на каждый символ.
  // searchArticles сам отсекает запросы короче 2 символов (вернёт []), поэтому
  // и сброс, и поиск выполняются единообразно в отложенном колбэке (без
  // синхронного setState в теле эффекта).
  const reqIdRef = useRef(0)
  useEffect(() => {
    const reqId = ++reqIdRef.current
    const timer = setTimeout(() => {
      // searchArticles сам отсекает запросы короче 2 символов (вернёт []), но
      // короткий запрос отсекаем уже здесь — не дёргаем API по пустому полю
      // сразу после монтирования карточки.
      if (query.trim().length < 2) {
        if (reqId === reqIdRef.current) setHits([])
        return
      }
      void searchArticles(query)
        .then((res) => {
          // игнорируем устаревший ответ, если пользователь продолжил печатать
          if (reqId === reqIdRef.current) setHits(res)
        })
        .catch(() => {
          // сбой поиска не должен ронять промис и оставлять stale-подсказки
          if (reqId === reqIdRef.current) setHits([])
        })
    }, searchDebounceMs)
    return () => clearTimeout(timer)
  }, [query, searchDebounceMs])

  return (
    <Card data-testid="review-card">
      <CardContent className="flex flex-col gap-3">
        {/* 1. Крошка сметы */}
        <CrumbTrail levels={row.breadcrumb} />

        {/* 2. Работа: код раздела + полный текст без клампа */}
        <div className="text-sm">
          <span className="font-mono text-muted-foreground">
            {row.section_code}
          </span>{" "}
          <span>{row.source_name}</span>
        </div>

        {/* 2b. Окружение (спека 3.5): крошка → строка → окружение → кандидаты */}
        {contextStrip}

        {row.status === "error" ? (
          <Alert variant="destructive">
            <Badge variant="destructive" className="mb-1.5">
              Ошибка обработки
            </Badge>
            <AlertDescription>{row.matchError}</AlertDescription>
          </Alert>
        ) : (
          <>
            {/* 3. Рекомендация (гейт синтетической рекомендации) */}
            {syntheticRecommendation && (
              <button
                type="button"
                onClick={onConfirmRecommendation}
                className={
                  candidateButtonClass +
                  " " +
                  (chosenCode === row.matched_code
                    ? "border-primary shadow-[var(--ds-glow-violet)]"
                    : "border-border")
                }
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {row.matched_code}
                </span>
                <span className="flex-1">
                  <CrumbTrail levels={row.matchedBreadcrumb} />
                </span>
                {row.status !== "matched_fund" && (
                  <span className="font-mono text-xs text-muted-foreground">
                    {row.score.toFixed(2)}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {row.status === "matched_fund" ? (
                    <>
                      <Database className="mr-1 inline size-3" />
                      Из фонда
                    </>
                  ) : (
                    "Рекомендация AI"
                  )}
                </span>
                <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
                  Enter
                </kbd>
              </button>
            )}

            {/* 4. Кандидаты */}
            {row.candidates.map((c, i) => {
              const selected = c.article_code === chosenCode
              // Рекомендация арбитра ⇒ подсвеченный кандидат (не отдельный
              // блок) — синтетический блок выше уже покрывает случай, когда
              // matched_code не входит в candidates.
              const isRecommendation =
                recommended &&
                !syntheticRecommendation &&
                c.article_code === row.matched_code
              return (
                <button
                  key={c.article_code}
                  type="button"
                  onClick={() => onPickCandidate(c)}
                  className={
                    candidateButtonClass +
                    " " +
                    (selected
                      ? "border-primary shadow-[var(--ds-glow-violet)]"
                      : "border-border")
                  }
                >
                  <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
                    {i + 1}
                  </kbd>
                  <span className="font-mono text-xs text-muted-foreground">
                    {c.article_code}
                  </span>
                  <span className="flex-1">{c.name}</span>
                  <CrumbTrail levels={c.breadcrumb} />
                  <span className="font-mono text-xs text-muted-foreground">
                    {c.score.toFixed(2)}
                  </span>
                  {isRecommendation && (
                    <>
                      <span className="text-xs text-muted-foreground">
                        {row.status === "matched_fund" ? (
                          <>
                            <Database className="mr-1 inline size-3" />
                            Из фонда
                          </>
                        ) : (
                          "Рекомендация AI"
                        )}
                      </span>
                      <kbd className="rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
                        Enter
                      </kbd>
                    </>
                  )}
                </button>
              )
            })}
          </>
        )}

        {/* 5. Поиск по справочнику (сервер фильтрует сам) */}
        <Command
          shouldFilter={false}
          className="rounded-md border border-border"
        >
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Нет верного — искать в справочнике…"
          />
          <CommandList>
            {query.trim() !== "" && hits.length === 0 && (
              <CommandEmpty>Ничего не найдено</CommandEmpty>
            )}
            {hits.map((c) => (
              <CommandItem
                key={c.article_code}
                value={c.article_code}
                onSelect={() => onManualPick(c)}
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {c.article_code}
                </span>
                <span className="flex-1">{c.name}</span>
                <CrumbTrail levels={c.breadcrumb} />
              </CommandItem>
            ))}
          </CommandList>
        </Command>

        {/* 6. Оставить без пары */}
        <Button
          variant="outline"
          onClick={onReject}
          className={
            "self-start" +
            (rejectSelected
              ? " border-primary shadow-[var(--ds-glow-violet)]"
              : "")
          }
        >
          Оставить без пары{" "}
          <kbd className="ml-1 rounded bg-secondary px-1.5 text-xs text-[var(--ds-text-2)]">
            0
          </kbd>
        </Button>

        {/* 7. Постоянная легенда клавиш */}
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <LegendItem
            keyLabel={
              row.candidates.length <= 1 ? "1" : `1–${row.candidates.length}`
            }
            text="выбрать кандидата"
            muted={row.candidates.length === 0}
          />
          <LegendItem keyLabel="0" text="без пары" muted={false} />
          <LegendItem
            keyLabel="Enter"
            text="подтвердить рекомендацию"
            muted={!recommended}
          />
          <LegendItem keyLabel="N" text="пропустить" muted={false} />
          <LegendItem keyLabel="←" text="вернуться" muted={!canUndo} />
        </div>
      </CardContent>
    </Card>
  )
}

function LegendItem({
  keyLabel,
  text,
  muted,
}: {
  keyLabel: string
  text: string
  muted: boolean
}) {
  return (
    <span className={"flex items-center gap-1 " + (muted ? "opacity-50" : "")}>
      <kbd className="rounded bg-secondary px-1.5 text-[var(--ds-text-2)]">
        {keyLabel}
      </kbd>
      {text}
    </span>
  )
}
