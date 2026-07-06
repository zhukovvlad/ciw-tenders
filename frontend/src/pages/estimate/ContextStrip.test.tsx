import { describe, expect, it } from "vitest"
import { render, screen, within } from "@testing-library/react"
import { ContextStrip } from "@/pages/estimate/ContextStrip"
import { initReview } from "@/lib/reviewState"
import type { MatchRow, MatchStatus } from "@/lib/types"

// row(...) — хелпер как в Task 2 Step 1
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

const ROWS: MatchRow[] = [
  row(1, 0, "excluded", { source_name: "Орг-заголовок", breadcrumb: [] }),
  row(2, 1, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(3, 2, "needs_review", { breadcrumb: ["Орг-заголовок"] }),
  row(4, 3, "confident", { breadcrumb: ["Орг-заголовок"] }),
  row(5, 4, "confident", {
    source_name: "Другой раздел работа",
    breadcrumb: ["Раздел Б"],
  }),
  row(6, 5, "confident", { breadcrumb: ["Раздел Б"] }),
]

describe("ContextStrip", () => {
  it("окно ±2 вокруг активной по sourceIndex, включая excluded (приглушён)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    // окно: строки 1..5 (source_index 0..4); строки 6 нет
    expect(screen.getByText(/Орг-заголовок/)).toBeInTheDocument()
    expect(screen.queryByText("Строка 6")).not.toBeInTheDocument()
    const org = screen.getByText(/Орг-заголовок/).closest("[data-row]")!
    expect(org.className).toContain("opacity-60")
  })

  it("активная строка помечена", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen.getByText("Строка 3").closest("[data-row]")!
    expect(active).toHaveAttribute("data-active", "true")
  })

  it("разделитель на границе верхнеуровневого раздела", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={4} />)
    // между строкой 4 (раздел «Орг-заголовок») и строкой 5 («Раздел Б»)
    expect(screen.getByTestId("section-boundary")).toBeInTheDocument()
  })

  it("активная строка — маркер «вы здесь», не статус", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen
      .getByText("Строка 3")
      .closest("[data-row]") as HTMLElement
    expect(within(active).getByLabelText("вы здесь")).toBeInTheDocument()
    expect(active.textContent).not.toContain("→")
  })

  // Одноимённые листовые разделы под разными родителями — кейс, ради которого
  // сравнивается ПОЛНЫЙ путь (спека §2: имена листовых уровней не уникальны).
  const SAME_LEAF_ROWS: MatchRow[] = [
    row(1, 0, "needs_review", {
      source_name: "Работа 1",
      breadcrumb: ["Топ", "Подраздел А", "Материалы"],
    }),
    row(2, 1, "needs_review", {
      source_name: "Работа 2",
      breadcrumb: ["Топ", "Подраздел Б", "Материалы"],
    }),
  ]

  // Два подраздела под одним верхнеуровневым — кейс, на котором breadcrumb[0]
  // молчал.
  const SIBLING_ROWS: MatchRow[] = [
    row(1, 0, "needs_review", {
      source_name: "Работа А1",
      breadcrumb: ["Топ", "Подраздел А"],
    }),
    row(2, 1, "needs_review", {
      source_name: "Работа Б1",
      breadcrumb: ["Топ", "Подраздел Б"],
    }),
  ]

  // Заголовок (открывашка) между разделами: next.breadcrumb ===
  // header.breadcrumb + [header.source_name] → разделитель подавлен.
  function headerRows(headerStatus: MatchStatus): MatchRow[] {
    return [
      row(1, 0, "needs_review", {
        source_name: "Работа А1",
        breadcrumb: ["Топ", "Подраздел А"],
      }),
      row(2, 1, headerStatus, {
        source_name: "Подраздел Б",
        breadcrumb: ["Топ"],
      }),
      row(3, 2, "needs_review", {
        source_name: "Работа Б1",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
    ]
  }

  it("одноимённые листовые разделы под разными родителями разделяются", () => {
    render(
      <ContextStrip
        state={initReview("x", SAME_LEAF_ROWS)}
        activeRowNumber={1}
      />
    )
    const b = screen.getByTestId("section-boundary")
    expect(b.textContent).toContain("Раздел — Материалы")
  })

  it("два подраздела под одним верхнеуровневым разделяются с подписью", () => {
    render(
      <ContextStrip state={initReview("x", SIBLING_ROWS)} activeRowNumber={1} />
    )
    expect(screen.getByTestId("section-boundary").textContent).toContain(
      "Раздел — Подраздел Б"
    )
  })

  it("строки одного раздела границы не имеют", () => {
    const rows = [
      row(1, 0, "needs_review", { breadcrumb: ["Топ", "А"] }),
      row(2, 1, "needs_review", { breadcrumb: ["Топ", "А"] }),
    ]
    render(<ContextStrip state={initReview("x", rows)} activeRowNumber={1} />)
    expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
  })

  it.each(["excluded", "needs_review"] as const)(
    "разделитель перед открывашкой подавлен (самообъявление), статус=%s",
    (st) => {
      render(
        <ContextStrip
          state={initReview("x", headerRows(st))}
          activeRowNumber={1}
        />
      )
      // граница А↔заголовок подавлена; заголовок↔Б1 — пути равны, границы нет
      expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
    }
  )

  it("открывашка склеена с детьми, вложенные сходятся", () => {
    const rows = [
      row(1, 0, "excluded", {
        source_name: "Подраздел Б",
        breadcrumb: ["Топ"],
      }),
      row(2, 1, "needs_review", {
        source_name: "Работа Б1",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
      row(3, 2, "needs_review", {
        source_name: "Работа Б2",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
    ]
    render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
    expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
    // край §4: последняя строка списка — не открывашка (next отсутствует)
    expect(
      screen.getByText("Работа Б2").closest("[data-row]")
    ).not.toHaveAttribute("data-opener")
  })

  it("две границы в одном окне ±2", () => {
    const rows = [
      row(1, 0, "needs_review", { breadcrumb: ["Топ", "А"] }),
      row(2, 1, "needs_review", { breadcrumb: ["Топ", "Б"] }),
      row(3, 2, "needs_review", { breadcrumb: ["Топ", "В"] }),
    ]
    render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
    expect(screen.getAllByTestId("section-boundary")).toHaveLength(2)
  })

  it("«путь укоротился» до корня — разделитель без подписи (пустой label)", () => {
    const rows = [
      row(1, 0, "confident", {
        source_name: "Глубокий узел",
        breadcrumb: ["А", "Б"],
      }),
      row(2, 1, "confident", { source_name: "Корневой узел", breadcrumb: [] }),
      row(3, 2, "confident", {
        source_name: "Соседний корневой",
        breadcrumb: [],
      }),
    ]
    render(<ContextStrip state={initReview("x", rows)} activeRowNumber={2} />)
    const boundary = screen.getByTestId("section-boundary")
    expect(boundary).toBeInTheDocument()
    expect(boundary.textContent).toBe("")
  })

  it("страж: семантика границы не зависит от MatchStatus", () => {
    // одна геометрия, два разных статуса заголовка → одинаковый результат
    const a = render(
      <ContextStrip
        state={initReview("x", headerRows("excluded"))}
        activeRowNumber={3}
      />
    )
    const countExcluded = a.container.querySelectorAll(
      '[data-testid="section-boundary"]'
    ).length
    a.unmount()
    const b = render(
      <ContextStrip
        state={initReview("x", headerRows("confident"))}
        activeRowNumber={3}
      />
    )
    const countWork = b.container.querySelectorAll(
      '[data-testid="section-boundary"]'
    ).length
    expect(countWork).toBe(countExcluded)
  })

  it("парный тест самообъявления: разделитель подавлен ∧ открывашка стилизована", () => {
    render(
      <ContextStrip
        state={initReview("x", headerRows("excluded"))}
        activeRowNumber={1}
      />
    )
    expect(screen.queryByTestId("section-boundary")).not.toBeInTheDocument()
    const header = screen.getByText("Подраздел Б").closest("[data-row]")!
    expect(header.className).toContain("font-medium")
    // приглушение excluded сохраняется — оси разные (спека §2)
    expect(header.className).toContain("opacity-60")
  })

  it("открывашка на краю окна (разделитель отрезан слайсом) всё равно стилизована", () => {
    const rows = [
      row(1, 0, "needs_review", {
        source_name: "Работа А1",
        breadcrumb: ["Топ", "Подраздел А"],
      }),
      row(2, 1, "excluded", {
        source_name: "Подраздел Б",
        breadcrumb: ["Топ"],
      }),
      row(3, 2, "needs_review", {
        source_name: "Работа Б1",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
      row(4, 3, "needs_review", {
        source_name: "Работа Б2",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
      row(5, 4, "needs_review", {
        source_name: "Работа Б3",
        breadcrumb: ["Топ", "Подраздел Б"],
      }),
    ]
    // активная 4 → окно [2..5]: заголовок — первая строка окна, j === 0
    render(<ContextStrip state={initReview("x", rows)} activeRowNumber={4} />)
    const header = screen.getByText("Подраздел Б").closest("[data-row]")!
    expect(header.className).toContain("font-medium")
  })

  it("подпись панели «Окружение в смете» рендерится", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    expect(screen.getByText(/Окружение в смете/i)).toBeInTheDocument()
  })

  it("контейнер полосы залит sunken-токеном и отбит воздухом снизу", () => {
    const { container } = render(
      <ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />
    )
    const root = container.firstElementChild!
    // утопленная поверхность (справка ≠ обведённые кнопки кандидатов)
    expect(root.className).toContain("bg-[var(--ds-surface-sunken)]")
    // воздух полоса↔кандидаты больше внутристрочного шага (спека §3 п.4)
    expect(root.className).toContain("mb-")
  })

  it("строки полосы не несут словаря кандидата (регресс-гвард роли)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    // неактивная строка: нет фрейма кандидата (rounded-md + border-border);
    // гвард проверяет словарь, а не подстроку «border» — Task 3 навесит
    // border-l-2 border-transparent, что этот гвард переживёт.
    const other = screen.getByText("Строка 2").closest("[data-row]")!
    expect(other.className).not.toContain("rounded")
    expect(other.className).not.toContain("border-border")
  })

  // Присвоенный сосед (confident → confirmed через initReview): справа — код
  // статьи, полное имя — только в title (спека §2 п.3, осознанный trade-off).
  const ASSIGNED_ROWS: MatchRow[] = [
    row(1, 0, "confident", {
      source_name: "Сосед",
      breadcrumb: ["Раздел"],
      matched_code: "3.2",
      matched_name: "Устройство гидроизоляции фундамента",
    }),
    row(2, 1, "needs_review", {
      source_name: "Активная",
      breadcrumb: ["Раздел"],
    }),
  ]

  it("правая часть присвоенного соседа — код, полное имя в title", () => {
    render(
      <ContextStrip
        state={initReview("x", ASSIGNED_ROWS)}
        activeRowNumber={2}
      />
    )
    const neighbor = screen
      .getByText("Сосед")
      .closest("[data-row]") as HTMLElement
    // справа код, НЕ полное имя (однородный раздел не повторяет длинный хвост)
    expect(neighbor.textContent).toContain("→ 3.2")
    expect(neighbor.textContent).not.toContain(
      "Устройство гидроизоляции фундамента"
    )
    // полное имя доступно в title
    expect(
      within(neighbor).getByTitle("3.2 Устройство гидроизоляции фундамента")
    ).toBeInTheDocument()
  })

  it("активная строка — перекрашенная кромка + тинт, маркер сохранён", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const active = screen
      .getByText("Строка 3")
      .closest("[data-row]") as HTMLElement
    expect(active.className).toContain("border-l-2")
    // тон перекрашен (не прозрачный) — twMerge схлопывает border-transparent
    expect(active.className).not.toContain("border-transparent")
    // тинт из 3.5 сохранён
    expect(active.className).toContain("bg-[color-mix")
    // маркер «вы здесь» сохранён
    expect(within(active).getByLabelText("вы здесь")).toBeInTheDocument()
  })

  it("неактивная строка несёт кромку-резерв прозрачным тоном (нет «дёрга»)", () => {
    render(<ContextStrip state={initReview("x", ROWS)} activeRowNumber={3} />)
    const other = screen.getByText("Строка 2").closest("[data-row]")!
    expect(other.className).toContain("border-l-2")
    expect(other.className).toContain("border-transparent")
  })

  it("рядовой сосед приглушён по тону, открывашка — полный тон (вторая ось)", () => {
    // headerRows: row2 «Подраздел Б» — открывашка (next.breadcrumb = [Топ,Подраздел Б]);
    // row1 «Работа А1» — рядовой сосед; active=3 → окно включает обе, обе не активны.
    render(
      <ContextStrip
        state={initReview("x", headerRows("needs_review"))}
        activeRowNumber={3}
      />
    )
    const ordinaryName = screen.getByText("Работа А1")
    const openerName = screen.getByText("Подраздел Б")
    expect(ordinaryName.className).toContain("text-[var(--ds-text-2)]")
    expect(openerName.className).not.toContain("text-[var(--ds-text-2)]")
  })
})
