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
    // синтетическая рекомендация несёт имя статьи (r.matched_name), не только код/крошку
    expect(screen.getByText(r.matched_name!)).toBeInTheDocument()
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

describe("ReviewCard: строка кандидата — имя+крошка вместе, score у края", () => {
  // Task 3 (спека 3.5 §3 п.3): имя кандидата и его крошка — в одном
  // flex-контейнере (крошка примыкает к имени), score — последний элемент
  // строки, у правого края.
  const candWithCrumb: Candidate = {
    id: 12,
    article_code: "07.02",
    name: "Пусконаладочные работы ИТП",
    score: 0.89,
    breadcrumb: ["ВИС", "Индивидуальный тепловой пункт"],
  }
  const r = row(12, 9, "needs_review", { candidates: [candWithCrumb] })

  it("крошка кандидата примыкает к имени, score — у правого края", () => {
    renderCard(r)
    const name = screen.getByText("Пусконаладочные работы ИТП")
    const crumb = screen.getByTitle("ВИС › Индивидуальный тепловой пункт")
    // имя и крошка — в одном flex-контейнере, а не просто оба прямые дети
    // кнопки (иначе проверка равенства parentElement была бы тривиальной)
    expect(name.parentElement).toBe(crumb.parentElement)
    const button = name.closest("button")!
    expect(name.parentElement).not.toBe(button)
    // score — последний элемент строки кандидата (matched_code по умолчанию
    // "01.01" не совпадает с "07.02" — рекомендационный чип не подмешивается)
    expect(button.lastElementChild?.textContent).toBe("0.89")
  })
})

describe("ReviewCard: слот contextStrip", () => {
  const r = row(11, 8, "needs_review", { candidates: [CAND] })

  it("слот contextStrip рендерится между строкой работы и кандидатами", () => {
    renderCard(r, { contextStrip: <div data-testid="strip-slot" /> })
    const slot = screen.getByTestId("strip-slot")
    const work = screen.getByText("Строка 11")
    const candidate = screen.getByText("Фундаменты под оборудование")
    // работа ПЕРЕД слотом, слот ПЕРЕД кандидатом (DOM-порядок)
    expect(
      work.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
    expect(
      slot.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it("без пропа contextStrip карточка рендерится как раньше", () => {
    renderCard(r)
    expect(screen.getByTestId("review-card")).toBeInTheDocument()
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

describe("ReviewCard: блок «Ваш выбор»", () => {
  const CAND2: Candidate = {
    id: 9,
    article_code: "07.01",
    name: "Кровельные работы",
    score: 0.64,
    breadcrumb: ["07 Кровля"],
  }

  it("override: показывает код, имя и крошку кандидата по коду", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [CAND, CAND2],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: CAND2.article_code,
        name: CAND2.name,
        manual: false,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).getByText("07.01")).toBeInTheDocument()
    expect(within(block).getByText("Кровельные работы")).toBeInTheDocument()
    expect(within(block).getByText(/07 Кровля/)).toBeInTheDocument()
  })

  it("выбор из поиска: крошка из finalBreadcrumb, когда код совпал с final_code", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
      final_code: "09.09",
      finalBreadcrumb: ["09 Прочее"],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).getByText(/09 Прочее/)).toBeInTheDocument()
  })

  it("крошки нет, если код решения не совпал с final_code и не найден в кандидатах", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
      final_code: "99.99",
      finalBreadcrumb: ["99 Устаревшее"],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    expect(within(block).queryByText(/99 Устаревшее/)).toBeNull()
  })

  it("строка no_match, решённая через поиск: блок есть, подписи рекомендации нет", () => {
    const r = row(5, 2, "no_match", {
      matched_code: null,
      matched_name: null,
      candidates: [],
      final_code: "09.09",
      finalBreadcrumb: [],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    expect(screen.getByTestId("your-choice")).toBeInTheDocument()
    expect(screen.queryByText("Рекомендация системы")).toBeNull()
  })

  it("строка error, решённая через поиск: блок есть и стоит ВЫШЕ Alert-а", () => {
    const r = row(5, 2, "error", {
      matched_code: null,
      matched_name: null,
      matchError: "LLM timeout",
      candidates: [],
      final_code: "09.09",
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "09.09",
        name: "Найденная статья",
        manual: true,
      },
    })
    const block = screen.getByTestId("your-choice")
    const alertText = screen.getByText("LLM timeout")
    // DOCUMENT_POSITION_FOLLOWING === 4: alert идёт ПОСЛЕ блока
    expect(
      block.compareDocumentPosition(alertText) &
        Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it("подтверждение самой рекомендации блок НЕ показывает", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "01.01",
        name: "Статья",
        manual: false,
      },
    })
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("нерешённая строка блок НЕ показывает (pending)", () => {
    renderCard(row(5, 2, "needs_review", { candidates: [] }))
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("нерешённая error-строка блок НЕ показывает", () => {
    renderCard(
      row(5, 2, "error", {
        matched_code: null,
        matched_name: null,
        matchError: "LLM timeout",
        candidates: [],
      })
    )
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("reject-решение блок НЕ показывает", () => {
    renderCard(row(5, 2, "no_match", { candidates: [] }), {
      decision: { kind: "no_match" },
    })
    expect(screen.queryByTestId("your-choice")).toBeNull()
  })

  it("при показанном блоке рекомендация уходит под подпись «Рекомендация системы»", () => {
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [CAND2],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: CAND2.article_code,
        name: CAND2.name,
        manual: false,
      },
    })
    expect(screen.getByText("Рекомендация системы")).toBeInTheDocument()
  })

  it("рекомендация ВНУТРИ candidates: блок есть, подписи над списком нет", () => {
    // matched_code входит в candidates ⇒ рекомендация это подсвеченный
    // кандидат внутри списка (syntheticRecommendation === false), а не
    // отдельная секция. Подпись «Рекомендация системы» здесь заголовком
    // всего списка из пяти произвольных кандидатов была бы враньём — она
    // обязана существовать ровно тогда, когда есть отдельная секция
    // рекомендации, которую подписывать.
    const r = row(5, 2, "needs_review", {
      matched_code: "01.01",
      matched_name: "Статья",
      candidates: [{ ...CAND, article_code: "01.01" }, CAND2],
    })
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: CAND2.article_code,
        name: CAND2.name,
        manual: false,
      },
    })
    expect(screen.getByTestId("your-choice")).toBeInTheDocument()
    expect(screen.queryByText("Рекомендация системы")).toBeNull()
  })
})

describe("ReviewCard: Enter гаснет на решённых строках", () => {
  const r = row(5, 2, "needs_review", {
    matched_code: "01.01",
    matched_name: "Статья",
    candidates: [],
  })

  it("на pending-строке бейдж Enter внутри рекомендации есть", () => {
    renderCard(r)
    const rec = screen.getByText("Статья").closest("button")!
    expect(within(rec).getByText("Enter")).toBeInTheDocument()
  })

  it("на решённой строке бейджа Enter у рекомендации нет", () => {
    renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "07.01",
        name: "Кровельные работы",
        manual: false,
      },
    })
    // легенда клавиш содержит слово Enter всегда — проверяем именно бейдж
    // внутри кнопки рекомендации
    const rec = screen.getByText("Статья").closest("button")!
    expect(within(rec).queryByText("Enter")).toBeNull()
  })

  it("клик по рекомендации на решённой строке по-прежнему работает", async () => {
    const props = renderCard(r, {
      decision: {
        kind: "confirmed",
        code: "07.01",
        name: "Кровельные работы",
        manual: false,
      },
    })
    const rec = screen.getByText("Статья").closest("button")!
    await userEvent.click(rec)
    expect(props.onConfirmRecommendation).toHaveBeenCalledTimes(1)
  })

  // ВТОРОЙ бейдж: когда matched_code входит в candidates, рекомендация — это
  // кандидатная строка с веткой isRecommendation и собственным kbd Enter.
  const recAsCandidate: Candidate = {
    id: 1,
    article_code: "01.01",
    name: "Статья",
    score: 0.9,
    breadcrumb: ["01 Раздел"],
  }
  const rc = row(6, 3, "needs_review", {
    matched_code: "01.01",
    matched_name: "Статья",
    candidates: [recAsCandidate],
  })

  it("рекомендация ВНУТРИ candidates: на pending бейдж Enter есть", () => {
    renderCard(rc)
    const cand = screen.getByText("Статья").closest("button")!
    expect(within(cand).getByText("Enter")).toBeInTheDocument()
  })

  it("рекомендация ВНУТРИ candidates: на решённой строке бейджа Enter нет", () => {
    renderCard(rc, {
      decision: {
        kind: "confirmed",
        code: "07.01",
        name: "Кровельные работы",
        manual: false,
      },
    })
    const cand = screen.getByText("Статья").closest("button")!
    expect(within(cand).queryByText("Enter")).toBeNull()
  })
})

describe("ReviewCard: score null (tree-движок)", () => {
  it("не рендерит score строки и кандидата, когда он null", () => {
    const r = row(7, 3, "needs_review", {
      score: null,
      matched_code: "4.2.1",
      candidates: [
        {
          id: 5,
          article_code: "4.2.1",
          name: "Гориз",
          score: null,
          breadcrumb: [],
        },
        {
          id: 6,
          article_code: "4.2.3",
          name: "Гориз проч",
          score: null,
          breadcrumb: [],
        },
      ],
    })
    renderCard(r)
    expect(screen.queryByText("0.00")).toBeNull()
    expect(screen.getByText("Гориз")).toBeInTheDocument()
    expect(screen.getByText("Гориз проч")).toBeInTheDocument()
  })
})
