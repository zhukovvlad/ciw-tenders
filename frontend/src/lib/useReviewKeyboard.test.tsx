import { describe, expect, it, vi } from "vitest"
import { render } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useReviewKeyboard } from "@/lib/useReviewKeyboard"

function Harness(props: Parameters<typeof useReviewKeyboard>[0]) {
  useReviewKeyboard(props)
  return <input aria-label="вне-лупа" />
}

describe("useReviewKeyboard", () => {
  it("цифры выбирают кандидата, Enter подтверждает, n — следующая", async () => {
    const onPick = vi.fn(),
      onConfirm = vi.fn(),
      onNext = vi.fn()
    render(
      <Harness
        enabled
        candidateCount={3}
        onPick={onPick}
        onConfirm={onConfirm}
        onNext={onNext}
      />
    )
    await userEvent.keyboard("2")
    expect(onPick).toHaveBeenCalledWith(1)
    await userEvent.keyboard("{Enter}")
    expect(onConfirm).toHaveBeenCalled()
    await userEvent.keyboard("n")
    expect(onNext).toHaveBeenCalled()
  })

  it("игнорирует ввод в поле и при enabled=false", async () => {
    const onPick = vi.fn()
    const { rerender } = render(
      <Harness
        enabled={false}
        candidateCount={3}
        onPick={onPick}
        onConfirm={vi.fn()}
        onNext={vi.fn()}
      />
    )
    await userEvent.keyboard("1")
    expect(onPick).not.toHaveBeenCalled()
    rerender(
      <Harness
        enabled
        candidateCount={3}
        onPick={onPick}
        onConfirm={vi.fn()}
        onNext={vi.fn()}
      />
    )
    const input = document.querySelector("input")!
    input.focus()
    await userEvent.keyboard("1")
    expect(onPick).not.toHaveBeenCalled()
  })

  it("0 зовёт onReject, ArrowLeft — onUndo", async () => {
    const onReject = vi.fn(),
      onUndo = vi.fn()
    render(
      <Harness
        enabled
        candidateCount={0}
        onPick={vi.fn()}
        onConfirm={vi.fn()}
        onNext={vi.fn()}
        onReject={onReject}
        onUndo={onUndo}
      />
    )
    await userEvent.keyboard("0")
    expect(onReject).toHaveBeenCalled()
    await userEvent.keyboard("{ArrowLeft}")
    expect(onUndo).toHaveBeenCalled()
  })

  it("canConfirm=false: Enter не зовёт onConfirm (error/no_match без рекомендации)", async () => {
    const onConfirm = vi.fn()
    render(
      <Harness
        enabled
        candidateCount={0}
        canConfirm={false}
        onPick={vi.fn()}
        onConfirm={onConfirm}
        onNext={vi.fn()}
      />
    )
    await userEvent.keyboard("{Enter}")
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it("глушится, когда открыт диалог (role=alertdialog data-state=open)", async () => {
    const onNext = vi.fn()
    render(
      <>
        <Harness
          enabled
          candidateCount={0}
          onPick={vi.fn()}
          onConfirm={vi.fn()}
          onNext={onNext}
        />
        <div role="alertdialog" data-state="open" />
      </>
    )
    await userEvent.keyboard("n")
    expect(onNext).not.toHaveBeenCalled()
  })
})
