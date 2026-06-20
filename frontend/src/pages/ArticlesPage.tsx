// frontend/src/pages/ArticlesPage.tsx
import { useState } from "react"
import { Plus, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { Candidate } from "@/lib/types"
import { MOCK_ARTICLES } from "@/lib/mock/fixtures"

const EMPTY = { article_code: "", name: "", section_name: "" }

export function ArticlesPage() {
  const [articles, setArticles] = useState<Candidate[]>(MOCK_ARTICLES)
  const [form, setForm] = useState(EMPTY)

  function add(e: React.FormEvent) {
    e.preventDefault()
    if (!form.article_code || !form.name) return
    setArticles((a) => [{ ...form, score: 0 }, ...a])
    setForm(EMPTY)
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">Новая статья справочника</h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Эталонные статьи СМР. (Мок: добавление локальное, без сети.)
      </p>
      <form
        onSubmit={add}
        className="mb-6 grid gap-3 sm:grid-cols-[160px_1fr_1fr_auto]"
      >
        <Input
          placeholder="Код (СМР-01-001)"
          value={form.article_code}
          onChange={(e) => setForm({ ...form, article_code: e.target.value })}
        />
        <Input
          placeholder="Наименование"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />
        <Input
          placeholder="Раздел"
          value={form.section_name}
          onChange={(e) => setForm({ ...form, section_name: e.target.value })}
        />
        <Button type="submit">
          <Plus className="size-4" />
          Добавить
        </Button>
      </form>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs tracking-wide text-muted-foreground uppercase">
            <th className="px-4 py-2.5 font-normal">Код</th>
            <th className="px-4 py-2.5 font-normal">Наименование</th>
            <th className="px-4 py-2.5 font-normal">Раздел</th>
            <th className="w-10" />
          </tr>
        </thead>
        <tbody>
          {articles.map((a) => (
            <tr
              key={a.article_code}
              className="border-t border-[var(--ds-hairline)]"
            >
              <td className="px-4 py-2 font-mono text-xs">{a.article_code}</td>
              <td className="px-4 py-2">{a.name}</td>
              <td className="px-4 py-2 text-muted-foreground">
                {a.section_name}
              </td>
              <td className="px-4 py-2">
                <button
                  aria-label="Удалить"
                  onClick={() =>
                    setArticles((arr) =>
                      arr.filter((x) => x.article_code !== a.article_code)
                    )
                  }
                >
                  <Trash2 className="size-4 text-destructive" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ArticlesPage
