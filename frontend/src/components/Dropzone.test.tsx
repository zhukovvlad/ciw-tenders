import { describe, expect, it, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Dropzone } from "./Dropzone"

describe("Dropzone", () => {
  it("выбор файла через клик вызывает onFile", async () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    await userEvent.upload(
      screen.getByLabelText(/файл/i),
      new File(["x"], "doc.xlsx")
    )
    expect(onFile).toHaveBeenCalledTimes(1)
    expect(onFile.mock.calls[0][0].name).toBe("doc.xlsx")
  })

  it("drop файла вызывает onFile", () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    const zone = screen.getByText(/перетащите/i).closest("label")!
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "doc.xlsx")] },
    })
    expect(onFile).toHaveBeenCalledTimes(1)
  })

  it("drop файла с неподходящим расширением игнорируется", () => {
    const onFile = vi.fn()
    render(<Dropzone onFile={onFile} accept=".xlsx" id="f" ariaLabel="файл" />)
    const zone = screen.getByText(/перетащите/i).closest("label")!
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "doc.pdf")] },
    })
    expect(onFile).not.toHaveBeenCalled()
  })

  it("disabled блокирует выбор файла", async () => {
    const onFile = vi.fn()
    render(
      <Dropzone
        onFile={onFile}
        accept=".xlsx"
        id="f"
        ariaLabel="файл"
        disabled
      />
    )
    const input = screen.getByLabelText(/файл/i)
    expect(input).toBeDisabled()
    await userEvent.upload(input, new File(["x"], "doc.xlsx"))
    expect(onFile).not.toHaveBeenCalled()
  })
})
