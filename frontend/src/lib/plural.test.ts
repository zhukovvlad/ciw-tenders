import { describe, expect, it } from "vitest"
import { pluralizeRu } from "./plural"

const FORMS: [string, string, string] = ["замечание", "замечания", "замечаний"]

describe("pluralizeRu", () => {
  it.each([
    [1, "замечание"],
    [21, "замечание"],
    [101, "замечание"],
    [2, "замечания"],
    [4, "замечания"],
    [22, "замечания"],
    [5, "замечаний"],
    [11, "замечаний"],
    [12, "замечаний"],
    [14, "замечаний"],
    [111, "замечаний"],
    [0, "замечаний"],
  ])("%i → %s", (n, expected) => {
    expect(pluralizeRu(n, FORMS)).toBe(expected)
  })
})
