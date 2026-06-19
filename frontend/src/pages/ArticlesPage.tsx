import { Loader2, Plus, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, type Article, type ArticleCreate } from "@/lib/api"

const EMPTY: ArticleCreate = { article_code: "", name: "", section_name: "" }

export function ArticlesPage() {
  const [articles, setArticles] = useState<Article[]>([])
  const [form, setForm] = useState<ArticleCreate>(EMPTY)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    setLoading(true)
    setError(null)
    try {
      setArticles(await api.listArticles())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Первичная загрузка справочника при монтировании.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh()
  }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.createArticle(form)
      setForm(EMPTY)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteArticle(id)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Новая статья справочника</CardTitle>
          <CardDescription>
            Эталонные статьи СМР. При создании строка автоматически векторизуется (Gemini).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-[160px_1fr_1fr_auto]">
            <Input
              placeholder="Код (СМР-01-001)"
              value={form.article_code}
              onChange={(e) => setForm({ ...form, article_code: e.target.value })}
              required
            />
            <Input
              placeholder="Наименование работы"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Input
              placeholder="Раздел"
              value={form.section_name}
              onChange={(e) => setForm({ ...form, section_name: e.target.value })}
              required
            />
            <Button type="submit" disabled={saving}>
              {saving ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
              Добавить
            </Button>
          </form>
          {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Справочник
            <Badge variant="secondary">{articles.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Загрузка…
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[140px]">Код</TableHead>
                  <TableHead>Наименование</TableHead>
                  <TableHead>Раздел</TableHead>
                  <TableHead className="w-[60px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {articles.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground">
                      Справочник пуст
                    </TableCell>
                  </TableRow>
                ) : (
                  articles.map((a) => (
                    <TableRow key={a.id}>
                      <TableCell className="font-mono text-xs">{a.article_code}</TableCell>
                      <TableCell>{a.name}</TableCell>
                      <TableCell className="text-muted-foreground">{a.section_name}</TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(a.id)}
                          aria-label="Удалить"
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default ArticlesPage
