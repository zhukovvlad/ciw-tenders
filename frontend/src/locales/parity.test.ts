import { describe, expect, it } from "vitest"

import ru from "./ru.json"
import tr from "./tr.json"

type Json = { [k: string]: string | Json }

function leafPaths(obj: Json, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k
    return typeof v === "string" ? [path] : leafPaths(v, path)
  })
}

function leafValue(obj: Json, path: string): string {
  return path.split(".").reduce<Json | string>((acc, k) => {
    return (acc as Json)[k]
  }, obj) as string
}

function placeholders(s: string): string[] {
  return [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort()
}

describe("словари ru/tr", () => {
  it("имеют идентичные множества ключей", () => {
    expect(leafPaths(tr as Json).sort()).toEqual(leafPaths(ru as Json).sort())
  })

  it("имеют совпадающие интерполяции в парных строках", () => {
    for (const path of leafPaths(ru as Json)) {
      expect(placeholders(leafValue(tr as Json, path))).toEqual(
        placeholders(leafValue(ru as Json, path))
      )
    }
  })
})
