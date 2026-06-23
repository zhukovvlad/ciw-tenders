import { useState } from "react"
import { ChevronDown, Search } from "lucide-react"
import type { Candidate, Decision, MatchRow } from "@/lib/types"
import { statusLabel } from "@/lib/reviewState"
import { searchArticles } from "@/lib/api/articles"

interface ReviewRowProps {
  row: MatchRow
  decision: Decision
  expanded: boolean
  onToggle: () => void
  onPickCandidate: (code: string) => void
  onManualPick: (c: Candidate) => void
  onConfirmNoMatch: () => void
}

const statusTone: Record<string, string> = {
  confident: "text-[var(--success)]",
  needs_review: "text-[var(--warning)]",
  no_match: "text-destructive",
}

export function ReviewRow({
  row,
  decision,
  expanded,
  onToggle,
  onPickCandidate,
  onManualPick,
  onConfirmNoMatch,
}: ReviewRowProps) {
  const [query, setQuery] = useState("")
  const [hits, setHits] = useState<Candidate[]>([])
  const flagged = row.status !== "confident"
  const chosenCode =
    decision.kind === "confirmed" ? decision.code : row.matched_code

  async function runSearch(q: string) {
    setQuery(q)
    setHits(await searchArticles(q))
  }

  return (
    <>
      <tr
        className={
          flagged ? "cursor-pointer border-l-2 border-l-[var(--warning)]" : ""
        }
        onClick={flagged ? onToggle : undefined}
        data-state={expanded ? "open" : "closed"}
      >
        <td className="px-4 py-2 font-mono text-muted-foreground">
          {row.row_number}
        </td>
        <td className="px-4 py-2 text-[var(--ds-text-2)]">{row.source_name}</td>
        <td className="px-4 py-2">
          {decision.kind === "no_match" || row.status === "no_match" ? (
            <span className="text-muted-foreground">— без пары —</span>
          ) : (
            <span>
              {flagged && (
                <ChevronDown className="mr-1 inline size-3 text-[var(--ds-accent-hover)]" />
              )}
              <span className="font-mono text-xs text-muted-foreground">
                {chosenCode}
              </span>{" "}
              {decision.kind === "confirmed" ? decision.name : row.matched_name}
            </span>
          )}
        </td>
        <td className="px-4 py-2 text-right font-mono text-xs text-muted-foreground">
          {row.status !== "no_match" ? row.score.toFixed(2) : ""}
        </td>
        <td className={"px-4 py-2 text-sm " + (statusTone[row.status] ?? "")}>
          {statusLabel(row, decision)}
        </td>
      </tr>

      {expanded && flagged && (
        <tr>
          <td
            colSpan={5}
            className="bg-[color-mix(in_srgb,var(--primary)_5%,transparent)] px-12 py-3"
          >
            {row.candidates.map((c, i) => {
              const sel = c.article_code === chosenCode
              return (
                <button
                  key={c.article_code}
                  onClick={(e) => {
                    e.stopPropagation()
                    onPickCandidate(c.article_code)
                  }}
                  className={
                    "mb-1.5 flex w-full items-center gap-3 rounded-md border px-3 py-2 text-left text-sm " +
                    (sel
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
                  <span className="font-mono text-xs text-muted-foreground">
                    {c.score.toFixed(2)}
                  </span>
                </button>
              )
            })}

            <div className="mt-2 flex items-center gap-2 rounded-md border border-border px-2">
              <Search className="size-3.5 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => runSearch(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                aria-label="Поиск статьи в справочнике"
                placeholder="Нет верного — искать в справочнике…"
                className="flex-1 bg-transparent py-2 text-sm outline-none"
              />
            </div>
            {hits.map((c) => (
              <button
                key={c.article_code}
                onClick={(e) => {
                  e.stopPropagation()
                  onManualPick(c)
                }}
                className="mt-1 flex w-full items-center gap-3 rounded-md border border-border px-3 py-1.5 text-left text-sm hover:border-[var(--ds-border-strong)]"
              >
                <span className="font-mono text-xs text-muted-foreground">
                  {c.article_code}
                </span>
                <span className="flex-1">{c.name}</span>
              </button>
            ))}

            {row.status === "no_match" && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onConfirmNoMatch()
                }}
                className="mt-2 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
              >
                Оставить без пары
              </button>
            )}
          </td>
        </tr>
      )}
    </>
  )
}
