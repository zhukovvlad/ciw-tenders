// frontend/src/pages/estimate/ReviewScreen.test.tsx
import { describe, expect, it, vi } from "vitest"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReducer } from "react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { ReviewScreen } from "@/pages/estimate/ReviewScreen"
import { initReview, reviewReducer } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

// ВСЕ ассерты «чья карточка открыта» — ТОЛЬКО внутри карточки: полоса
// контекста (±2 соседа) дублирует имена строк в DOM, screen.getByText по
// имени строки ловит не карточку, а полосу (ложноположительный тест)
const card = () => within(screen.getByTestId("review-card"))

vi.mock("@/lib/api/articles", () => ({
  searchArticles: vi.fn().mockResolvedValue([]),
}))

// row(...) — хелпер как в Task 2 Step 1 (frontend/src/lib/useReviewQueue.test.ts)
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

function Wrap({
  rows,
  url = "/estimates/5",
  onReview,
  readOnly,
}: {
  rows: MatchRow[]
  url?: string
  onReview?: (
    rowNumber: number,
    action: string,
    articleId?: number
  ) => Promise<boolean>
  readOnly?: boolean
}) {
  const [state, dispatch] = useReducer(reviewReducer, undefined, () =>
    initReview("смета.xlsx", rows)
  )
  // Зеркало продового контракта EstimatePage.handleReview: при неуспехе PATCH
  // вызывающий сам диспатчит reopen (откат оптимистичного решения) и лишь
  // потом резолвится false — без этого строка осталась бы «решённой» в
  // редьюсере и тест возврата в голову очереди был бы невыполним.
  const handleReview = onReview
    ? (rowNumber: number, action: string, articleId?: number) =>
        onReview(rowNumber, action, articleId).then((ok) => {
          if (!ok) dispatch({ type: "reopen", row: rowNumber })
          return ok
        })
    : undefined
  return (
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/estimates/:id"
          element={
            <ReviewScreen
              state={state}
              dispatch={dispatch}
              onExport={vi.fn()}
              onComplete={vi.fn()}
              onReview={handleReview as never}
              readOnly={readOnly}
            />
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

const ROWS: MatchRow[] = [
  row(1, 0, "excluded", { source_name: "Орг-заголовок" }),
  row(2, 1, "confident", { source_name: "Уверенная" }),
  row(3, 2, "needs_review", { source_name: "Спорная А" }),
  row(4, 3, "needs_review", { source_name: "Спорная Б" }),
]

describe("режимы", () => {
  it("дефолт — очередь: карточка первой спорной", () => {
    render(<Wrap rows={ROWS} />)
    expect(card().getByText("Спорная А")).toBeInTheDocument()
    // это карточка, а не таблица: у грида роль table
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("?view=grid — грид", () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    expect(screen.getByRole("table")).toBeInTheDocument()
  })

  it("шапка честная: «спорных решено 0 из 2» (excluded/confident не считаются)", () => {
    render(<Wrap rows={ROWS} />)
    expect(screen.getByText(/решено 0 из 2/i)).toBeInTheDocument()
  })
})

describe("поток очереди", () => {
  it("Enter коммитит рекомендацию и двигает к следующей спорной", async () => {
    const onReview = vi.fn().mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("{Enter}")
    expect(onReview).toHaveBeenCalledWith(3, "confirm", undefined)
    await waitFor(() =>
      expect(card().getByText("Спорная Б")).toBeInTheDocument()
    )
  })

  it("0 — без пары; ← возвращает к решённой", async () => {
    const onReview = vi.fn().mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("0")
    expect(onReview).toHaveBeenCalledWith(3, "reject", undefined)
    await userEvent.keyboard("{ArrowLeft}")
    expect(card().getByText("Спорная А")).toBeInTheDocument()
  })

  it("ошибка PATCH: строка в голову очереди — СЛЕДУЮЩЕЙ, активную не выдёргивает", async () => {
    const onReview = vi
      .fn()
      .mockResolvedValueOnce(false) // первый коммит падает
      .mockResolvedValue(true)
    render(<Wrap rows={ROWS} onReview={onReview} />)
    await userEvent.keyboard("{Enter}") // Спорная А → упало (async), активной стала Б
    // даже ПОСЛЕ отработки фейла активная остаётся Б (пин; страж stale closure)
    await waitFor(() => expect(onReview).toHaveBeenCalledTimes(1))
    expect(card().getByText("Спорная Б")).toBeInTheDocument()
    await userEvent.keyboard("{Enter}") // решаем Б
    // Спорная А вернулась в голову — теперь активна она
    await waitFor(() =>
      expect(card().getByText("Спорная А")).toBeInTheDocument()
    )
  })

  it("пустая очередь — терминальный экран", () => {
    render(<Wrap rows={[row(1, 0, "confident")]} />)
    expect(screen.getByText(/все спорные строки решены/i)).toBeInTheDocument()
  })
})

describe("грид ↔ очередь", () => {
  it("клик по строке грида открывает карточку этой строки (включая confident)", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    await userEvent.click(screen.getByText("Уверенная"))
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    // карточка ИМЕННО уверенной строки (перерешение) — скоуп обязателен,
    // «Уверенная» есть и в полосе контекста
    expect(card().getByText("Уверенная")).toBeInTheDocument()
  })

  it("возврат в очередь табом после клика из грида — поток, а не старая карточка", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" />)
    await userEvent.click(screen.getByText("Уверенная")) // очередь, карточка «Уверенная»
    await userEvent.click(screen.getByRole("tab", { name: /таблица/i })) // ушли в грид табом
    await userEvent.click(screen.getByRole("tab", { name: /очередь/i })) // вернулись
    // явный выбор сброшен (deselect при уходе в грид) — активна первая спорная
    expect(card().getByText("Спорная А")).toBeInTheDocument()
  })
})

describe("read-only (завершённая смета)", () => {
  it("клики выключены, переключателя нет, экспорт есть", async () => {
    render(<Wrap rows={ROWS} url="/estimates/5?view=grid" readOnly />)
    await userEvent.click(screen.getByText("Спорная А"))
    expect(screen.getByRole("table")).toBeInTheDocument() // остались в гриде
    expect(
      screen.queryByRole("tab", { name: /очередь/i })
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /выгрузить/i })
    ).toBeInTheDocument()
  })
})
