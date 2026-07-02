import { describe, expect, it, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ReviewRow } from "@/pages/estimate/ReviewRow"
import { MOCK_ROWS } from "@/lib/mock/fixtures"

// Mock the real articles API so tests don't hit the network
vi.mock("@/lib/api/articles", () => ({
  searchArticles: async (q: string) => {
    const query = q.toLowerCase()
    return [
      {
        id: 11,
        article_code: "СМР-07-060",
        name: "Устройство кровли",
        score: 0,
      },
    ].filter((a) => a.name.toLowerCase().includes(query))
  },
}))

function tableWrap(ui: React.ReactNode) {
  return (
    <table>
      <tbody>{ui}</tbody>
    </table>
  )
}
const reviewRow = MOCK_ROWS.find((r) => r.status === "needs_review")!
const confidentRow = MOCK_ROWS.find((r) => r.status === "confident")!
const fundRow = { ...confidentRow, status: "matched_fund" as const }
// реалистичное решение фонд-строки: initReview авто-подтверждает её (manual:false)
const fundDecision = {
  kind: "confirmed" as const,
  code: fundRow.matched_code!,
  name: fundRow.matched_name!,
  manual: false,
}

describe("ReviewRow", () => {
  it("строка со статусом matched_fund показывает бейдж «из фонда»", () => {
    render(
      tableWrap(
        <ReviewRow
          row={fundRow}
          decision={fundDecision}
          expanded={false}
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    expect(screen.getByText(/из фонда/i)).toBeInTheDocument()
    expect(screen.queryByText(/требует проверки/i)).not.toBeInTheDocument()
    expect(
      screen.queryByText(/подтверждено оператором/i)
    ).not.toBeInTheDocument()
    // score у фонд-хита нет by design (спека §4.3) — ячейка пустая; проверяем отсутствие
    // РЕАЛЬНОГО значения фикстуры (0.96), иначе ассерция не упадёт при сломанном гарде
    expect(screen.queryByText(fundRow.score.toFixed(2))).not.toBeInTheDocument()
  })

  it("фонд-строка кликабельна: клик зовёт onToggle (переопределение доступно)", async () => {
    const onToggle = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={fundRow}
          decision={fundDecision}
          expanded={false}
          onToggle={onToggle}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    await userEvent.click(screen.getByText(/из фонда/i))
    expect(onToggle).toHaveBeenCalled()
  })

  it("раскрытая фонд-строка даёт ручной поиск по справочнику (override)", () => {
    render(
      tableWrap(
        <ReviewRow
          row={fundRow}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    expect(
      screen.getByPlaceholderText(/искать в справочнике/i)
    ).toBeInTheDocument()
  })

  it("раскрытая спорная строка показывает 3 кандидата", () => {
    render(
      tableWrap(
        <ReviewRow
          row={reviewRow}
          decision={{ kind: "pending" }}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    expect(screen.getAllByRole("button", { name: /СМР-/ })).toHaveLength(3)
  })

  it("клик по кандидату вызывает onPickCandidate с кодом", async () => {
    const onPick = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={reviewRow}
          decision={{ kind: "pending" }}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={onPick}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    await userEvent.click(
      screen.getByRole("button", {
        name: new RegExp(reviewRow.candidates[1].article_code),
      })
    )
    expect(onPick).toHaveBeenCalledWith(reviewRow.candidates[1].article_code)
  })

  it("ручной поиск находит статью и отдаёт её в onManualPick", async () => {
    const onManual = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={reviewRow}
          decision={{ kind: "pending" }}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={onManual}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    await userEvent.type(
      screen.getByPlaceholderText(/искать в справочнике/i),
      "кровл"
    )
    const hit = await screen.findByRole("button", { name: /кровл/i })
    await userEvent.click(hit)
    expect(onManual).toHaveBeenCalled()
  })
})

const fundRowNoCands = { ...fundRow, candidates: [] }

describe("ReviewRow: правка уверенных позиций", () => {
  it("уверенная строка кликабельна: клик зовёт onToggle", async () => {
    const onToggle = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={confidentRow}
          decision={fundDecision}
          expanded={false}
          onToggle={onToggle}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    await userEvent.click(screen.getByText(confidentRow.source_name))
    expect(onToggle).toHaveBeenCalled()
  })

  it("раскрытая уверенная строка даёт кандидатов и ручной поиск", () => {
    render(
      tableWrap(
        <ReviewRow
          row={confidentRow}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    // у confident matched-кандидат уже в candidates → синтетической карточки НЕТ
    // (прямой ассерт по подписи, не по количеству кнопок — устойчив к фикстуре)
    expect(
      screen.queryByText(/рекомендация ai|из фонда/i)
    ).not.toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: /СМР-/ })).toHaveLength(1)
    expect(
      screen.getByPlaceholderText(/искать в справочнике/i)
    ).toBeInTheDocument()
  })

  it("фонд-строка без кандидатов рисует карточку рекомендации; клик → onConfirmRecommendation", async () => {
    const onConfirmRec = vi.fn()
    const onPick = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={fundRowNoCands}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={onPick}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={onConfirmRec}
        />
      )
    )
    // спека §Тесты кейс 4: у карточки нет score (0.96 — реальный score фикстуры)
    expect(
      screen.queryByText(fundRowNoCands.score.toFixed(2))
    ).not.toBeInTheDocument()
    const card = screen.getByRole("button", {
      name: new RegExp(fundRowNoCands.matched_code!),
    })
    // спека §Тесты кейс 4: метка происхождения «Из фонда» ВНУТРИ карточки
    // (в статус-ячейке строки она тоже есть — поэтому within, не screen)
    expect(within(card).getByText(/из фонда/i)).toBeInTheDocument()
    await userEvent.click(card)
    expect(onConfirmRec).toHaveBeenCalled()
    expect(onPick).not.toHaveBeenCalled()
  })

  it("карточка рекомендации не-фонд строки подписана «Рекомендация AI»", () => {
    render(
      tableWrap(
        <ReviewRow
          row={{ ...confidentRow, candidates: [] }}
          decision={fundDecision}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={vi.fn()}
        />
      )
    )
    expect(screen.getByText(/рекомендация ai/i)).toBeInTheDocument()
  })

  // спека §Тесты кейс 3: «без пары» доступна и у confident, и у matched_fund
  it.each([
    ["confident", confidentRow],
    ["matched_fund", fundRow],
  ])(
    "«Оставить без пары» доступна на раскрытой %s-строке и зовёт onConfirmNoMatch",
    async (_status, row) => {
      const onNoMatch = vi.fn()
      render(
        tableWrap(
          <ReviewRow
            row={row}
            decision={fundDecision}
            expanded
            onToggle={vi.fn()}
            onPickCandidate={vi.fn()}
            onManualPick={vi.fn()}
            onConfirmNoMatch={onNoMatch}
            onConfirmRecommendation={vi.fn()}
          />
        )
      )
      await userEvent.click(
        screen.getByRole("button", { name: /оставить без пары/i })
      )
      expect(onNoMatch).toHaveBeenCalled()
    }
  )

  it("после override карточка показывает исходную рекомендацию (снимок иммутабелен) и откатывает через confirm", async () => {
    // регрессия по спеке §Тесты кейс 5: оператор увёл фонд-хит на другую статью —
    // matched_* строки не изменились, карточка продолжает предлагать исходную пару
    const onConfirmRec = vi.fn()
    render(
      tableWrap(
        <ReviewRow
          row={fundRowNoCands}
          decision={{
            kind: "confirmed",
            code: "СМР-99-999",
            name: "Другая статья",
            manual: true,
          }}
          expanded
          onToggle={vi.fn()}
          onPickCandidate={vi.fn()}
          onManualPick={vi.fn()}
          onConfirmNoMatch={vi.fn()}
          onConfirmRecommendation={onConfirmRec}
        />
      )
    )
    const card = screen.getByRole("button", {
      name: new RegExp(fundRowNoCands.matched_code!),
    })
    await userEvent.click(card)
    expect(onConfirmRec).toHaveBeenCalled()
  })
})
