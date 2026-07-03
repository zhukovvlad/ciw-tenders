import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReviewCard, hasRecommendation } from "@/pages/estimate/ReviewCard"
import { searchArticles } from "@/lib/api/articles"
import type { Candidate, MatchRow, MatchStatus } from "@/lib/types"

vi.mock("@/lib/api/articles", () => ({ searchArticles: vi.fn() }))

// row(...) — хелпер как в useReviewQueue.test.ts (см. Task 2 Step 1)
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

const CAND: Candidate = {
  id: 3,
  article_code: "03.04",
  name: "Фундаменты под оборудование",
  score: 0.71,
  breadcrumb: ["03 Фундаменты и основания"],
}

function renderCard(
  r: MatchRow,
  over: Partial<Parameters<typeof ReviewCard>[0]> = {}
) {
  const props = {
    row: r,
    decision: { kind: "pending" as const },
    canUndo: false,
    onConfirmRecommendation: vi.fn(),
    onPickCandidate: vi.fn(),
    onManualPick: vi.fn(),
    onReject: vi.fn(),
    searchDebounceMs: 0,
    ...over,
  }
  render(<ReviewCard {...props} />)
  return props
}

describe("ReviewCard: спорная строка", () => {
  const r = row(5, 2, "needs_review", {
    breadcrumb: ["Раздел 1", "Конструктив"],
    matchedBreadcrumb: ["03 Фундаменты и основания"],
    candidates: [CAND],
  })

  it("крошка строки, полный текст работы, рекомендация с крошкой и score", () => {
    renderCard(r)
    expect(screen.getByText(/Раздел 1 › Конструктив/)).toBeInTheDocument()
    expect(screen.getByText("Строка 5")).toBeInTheDocument()
    expect(screen.getByText("Рекомендация AI")).toBeInTheDocument()
    expect(screen.getAllByText(/03 Фундаменты/).length).toBeGreaterThan(0)
  })

  it("клик по кандидату зовёт onPickCandidate с кандидатом", async () => {
    const p = renderCard(r)
    await userEvent.click(screen.getByText("Фундаменты под оборудование"))
    expect(p.onPickCandidate).toHaveBeenCalledWith(CAND)
  })

  it("«Оставить без пары» зовёт onReject; легенда клавиш постоянна", async () => {
    const p = renderCard(r)
    await userEvent.click(screen.getByRole("button", { name: /без пары/i }))
    expect(p.onReject).toHaveBeenCalled()
    expect(screen.getByText(/пропустить/i)).toBeInTheDocument()
  })

  it("поиск: хиты с крошками, выбор зовёт onManualPick", async () => {
    vi.mocked(searchArticles).mockResolvedValue([
      {
        id: 9,
        article_code: "08.01",
        name: "Штукатурка",
        score: 0,
        breadcrumb: ["08 Отделочные работы"],
      },
    ])
    const p = renderCard(r)
    await userEvent.type(
      screen.getByPlaceholderText(/искать в справочнике/i),
      "штук"
    )
    const hit = await screen.findByText("Штукатурка")
    await userEvent.click(hit)
    expect(p.onManualPick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 9, article_code: "08.01" })
    )
  })
})

describe("ReviewCard: подсветка рекомендации арбитра на pending-карточке", () => {
  // matched_code СОВПАДАЕТ с кандидатом (не синтетический случай) — по спеке
  // §3b рекомендация это подсвеченный кандидат, а не отдельный блок.
  const r = row(6, 4, "needs_review", {
    matched_code: CAND.article_code,
    matched_name: CAND.name,
    candidates: [CAND],
  })

  it("кандидат-рекомендация подсвечен, промаркирован «Рекомендация AI» и несёт Enter-чип без дублирования блока", () => {
    renderCard(r)
    const candidateButton = screen
      .getByText("Фундаменты под оборудование")
      .closest("button")
    expect(candidateButton).not.toBeNull()
    expect(candidateButton?.className).toContain("border-primary")
    // единственное вхождение — рекомендация не дублируется отдельным блоком
    expect(screen.getAllByText("Рекомендация AI")).toHaveLength(1)
    expect(
      within(candidateButton as HTMLElement).getByText("Enter")
    ).toBeInTheDocument()
  })
})

describe("ReviewCard: no_match — реджект открыт из грида", () => {
  // matched_code входит в кандидаты — до фикса старая рекомендация
  // подсвечивалась бы, хотя решение «без пары».
  const r = row(8, 5, "needs_review", {
    matched_code: CAND.article_code,
    matched_name: CAND.name,
    candidates: [CAND],
  })

  it("ни один кандидат не подсвечен, кнопка «без пары» несёт selected-класс", () => {
    renderCard(r, { decision: { kind: "no_match" } })
    const candidateButton = screen
      .getByText("Фундаменты под оборудование")
      .closest("button")
    expect(candidateButton?.className).not.toContain("border-primary")
    const rejectButton = screen.getByRole("button", { name: /без пары/i })
    expect(rejectButton.className).toContain("border-primary")
  })
})

describe("ReviewCard: pending — рекомендация пре-подсвечена (регресс)", () => {
  const r = row(6, 4, "needs_review", {
    matched_code: CAND.article_code,
    matched_name: CAND.name,
    candidates: [CAND],
  })

  it("кандидат-рекомендация подсвечен при pending", () => {
    renderCard(r, { decision: { kind: "pending" } })
    const candidateButton = screen
      .getByText("Фундаменты под оборудование")
      .closest("button")
    expect(candidateButton?.className).toContain("border-primary")
  })
})

describe("ReviewCard: легенда клавиш кандидатов по числу кандидатов", () => {
  // легенда и кнопки-кандидаты оба несут числовые kbd-чипы — скоуп через
  // span легенды («выбрать кандидата») отличает её от кнопки первого
  // кандидата (kbd «1» внутри её собственной кнопки).
  function legendCandidateKey() {
    return screen
      .getByText("выбрать кандидата")
      .closest("span")
      ?.querySelector("kbd")?.textContent
  }

  it("4 кандидата — легенда «1–4»", () => {
    const cand2 = { ...CAND, id: 4, article_code: "04.01" }
    const cand3 = { ...CAND, id: 5, article_code: "05.01" }
    const cand4 = { ...CAND, id: 6, article_code: "06.01" }
    renderCard(
      row(9, 6, "needs_review", {
        candidates: [CAND, cand2, cand3, cand4],
      })
    )
    expect(legendCandidateKey()).toBe("1–4")
  })

  it("1 кандидат — легенда «1» (не «1–1»)", () => {
    renderCard(row(10, 7, "needs_review", { candidates: [CAND] }))
    expect(legendCandidateKey()).toBe("1")
  })
})

describe("ReviewCard: error-строка", () => {
  const err = row(7, 3, "error", {
    matched_code: null,
    matched_name: null,
    matched_article_id: null,
    matchError: "таймаут LLM-арбитра",
    candidates: [],
  })

  it("показывает текст ошибки; рекомендации и кандидатов нет; поиск и без пары есть", () => {
    renderCard(err)
    expect(screen.getByText("таймаут LLM-арбитра")).toBeInTheDocument()
    expect(screen.queryByText("Рекомендация AI")).not.toBeInTheDocument()
    expect(screen.getByPlaceholderText(/искать/i)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /без пары/i })
    ).toBeInTheDocument()
  })

  it("hasRecommendation: false для error даже при matched_*", () => {
    expect(hasRecommendation(row(1, 1, "error"))).toBe(false)
    expect(hasRecommendation(row(1, 1, "needs_review"))).toBe(true)
    expect(
      hasRecommendation(
        row(1, 1, "no_match", { matched_code: null, matched_name: null })
      )
    ).toBe(false)
  })
})
