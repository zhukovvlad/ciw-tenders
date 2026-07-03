import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueueDone } from "@/pages/estimate/QueueDone"
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

const ROWS = [
  row(1, 0, "confident"),
  row(2, 1, "needs_review", {
    review_status: "confirmed",
    final_article_id: 7,
    final_code: "01.01",
    final_name: "Статья",
  }),
  row(3, 2, "no_match", {
    matched_code: null,
    matched_name: null,
    matched_article_id: null,
    review_status: "rejected",
  }),
]

describe("QueueDone", () => {
  it("сводка: заголовок, решено спорных, сопоставлено/без пары", () => {
    render(
      <QueueDone
        state={initReview("x", ROWS)}
        onComplete={vi.fn()}
        onShowGrid={vi.fn()}
      />
    )
    expect(screen.getByText(/все спорные строки решены/i)).toBeInTheDocument()
    expect(screen.getByText(/решено 2 из 2/i)).toBeInTheDocument()
  })

  it("CTA и ссылка на таблицу зовут колбэки", async () => {
    const onComplete = vi.fn()
    const onShowGrid = vi.fn()
    render(
      <QueueDone
        state={initReview("x", ROWS)}
        onComplete={onComplete}
        onShowGrid={onShowGrid}
      />
    )
    await userEvent.click(
      screen.getByRole("button", { name: /завершить проверку/i })
    )
    expect(onComplete).toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole("button", { name: /посмотреть таблицу/i })
    )
    expect(onShowGrid).toHaveBeenCalled()
  })
})
