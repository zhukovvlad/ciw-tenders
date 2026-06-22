import { afterEach, describe, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { toast } from "sonner"
import type { ImportReport } from "@/lib/types"
import { ApiError } from "@/lib/api/client"
import * as articlesApi from "@/lib/api/articles"
import { TemplateUpload } from "./TemplateUpload"

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
  Toaster: () => null,
}))

function report(over: Partial<ImportReport> = {}): ImportReport {
  return {
    created: 0,
    updated: 0,
    deleted: 0,
    unchanged: 0,
    skipped: [],
    pending_embeddings: 0,
    dry_run: true,
    force_required: false,
    ...over,
  }
}

function pick(name = "Шаблон.xlsx") {
  return userEvent.upload(
    screen.getByLabelText(/файл шаблона/i),
    new File(["x"], name)
  )
}

afterEach(() => vi.restoreAllMocks())

describe("TemplateUpload", () => {
  it("превью (dry_run) затем применение (dry_run=false)", async () => {
    const spy = vi
      .spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ created: 362, pending_embeddings: 362 }))
      .mockResolvedValueOnce(
        report({ created: 362, dry_run: false, pending_embeddings: 362 })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    expect(await screen.findByText(/создано/i)).toBeInTheDocument()
    expect(spy.mock.calls[0][1]).toEqual({ dryRun: true, force: false })
    await userEvent.click(screen.getByRole("button", { name: /применить/i }))
    await waitFor(() =>
      expect(spy.mock.calls[1][1]).toEqual({ dryRun: false, force: false })
    )
  })

  it("force_required: «Применить» заблокирована до чекбокса, затем шлёт force:true", async () => {
    vi.spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ deleted: 5, force_required: true }))
      .mockResolvedValueOnce(
        report({ deleted: 5, dry_run: false, force_required: true })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    await screen.findByText(/удалит/i)
    const apply = screen.getByRole("button", { name: /применить/i })
    expect(apply).toBeDisabled()
    await userEvent.click(screen.getByRole("checkbox"))
    expect(apply).toBeEnabled()
    await userEvent.click(apply)
    await waitFor(() =>
      expect(
        (
          articlesApi.importTemplate as unknown as {
            mock: { calls: unknown[][] }
          }
        ).mock.calls[1][1]
      ).toEqual({ dryRun: false, force: true })
    )
  })

  it("на 409-дрейф поднимает чекбокс force, затем шлёт force:true", async () => {
    vi.spyOn(articlesApi, "importTemplate")
      .mockResolvedValueOnce(report({ force_required: false }))
      .mockRejectedValueOnce(new ApiError(409, "состояние изменилось"))
      .mockResolvedValueOnce(
        report({ deleted: 3, dry_run: false, force_required: false })
      )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    const apply = await screen.findByRole("button", { name: /применить/i })
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
    await userEvent.click(apply)
    expect(await screen.findByText(/принудительный режим/i)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /применить/i })).toBeDisabled()
    await userEvent.click(screen.getByRole("checkbox"))
    await userEvent.click(screen.getByRole("button", { name: /применить/i }))
    await waitFor(() =>
      expect(
        (
          articlesApi.importTemplate as unknown as {
            mock: { calls: unknown[][] }
          }
        ).mock.calls[2][1]
      ).toEqual({ dryRun: false, force: true })
    )
  })

  it("смена файла сбрасывает согласие и заново снимает превью", async () => {
    vi.spyOn(articlesApi, "importTemplate").mockResolvedValue(
      report({ deleted: 5, force_required: true })
    )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick("a.xlsx")
    await screen.findByText(/удалит/i)
    await userEvent.click(screen.getByRole("checkbox"))
    expect(screen.getByRole("checkbox")).toBeChecked()
    await pick("b.xlsx")
    await screen.findByText(/удалит/i)
    expect(screen.getByRole("checkbox")).not.toBeChecked()
    expect(articlesApi.importTemplate).toHaveBeenCalledTimes(2)
  })

  it("на 400-ошибке файла шлёт тост", async () => {
    vi.spyOn(articlesApi, "importTemplate").mockRejectedValue(
      new ApiError(400, "плохой файл")
    )
    render(<TemplateUpload onApplied={vi.fn()} />)
    await pick()
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/плохой файл/i)
      )
    )
  })
})
