import { describe, expect, it, vi } from "vitest"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { EstimatesPage } from "@/pages/estimate/EstimatesPage"
import { uploadEstimate } from "@/lib/api/estimates"

vi.mock("@/lib/api/estimates", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/estimates")>(
    "@/lib/api/estimates"
  )
  return {
    ...actual,
    uploadEstimate: vi.fn(),
    listEstimates: vi.fn(async () => ({ items: [], total: 0 })),
  }
})

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="probe-path">{location.pathname}</div>
}

describe("EstimatesPage", () => {
  it("после загрузки файла уходит на /estimates/:id (без navigate-state)", async () => {
    vi.mocked(uploadEstimate).mockResolvedValue({
      id: 42,
      anomalies: [],
      outlineOverrides: 0,
    })
    render(
      <MemoryRouter initialEntries={["/estimates"]}>
        <Routes>
          <Route path="/estimates" element={<EstimatesPage />} />
          <Route path="/estimates/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    )
    const input = screen.getByLabelText(/файл сметы/)
    await userEvent.upload(input, new File(["x"], "смета.xlsx"))
    expect(await screen.findByTestId("probe-path")).toHaveTextContent(
      "/estimates/42"
    )
  })
})
