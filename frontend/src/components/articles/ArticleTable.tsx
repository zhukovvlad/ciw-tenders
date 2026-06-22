import { useMemo, useState } from "react"
import { Trash2 } from "lucide-react"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Input } from "@/components/ui/input"
import type { Article } from "@/lib/types"

interface ArticleTableProps {
  articles: Article[]
  isAdmin: boolean
  onDelete?: (id: number) => void
}

export function ArticleTable({
  articles,
  isAdmin,
  onDelete,
}: ArticleTableProps) {
  const [query, setQuery] = useState("")
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return articles
    return articles.filter(
      (a) =>
        a.article_code.toLowerCase().includes(q) ||
        a.name.toLowerCase().includes(q)
    )
  }, [articles, query])

  return (
    <div>
      <Input
        aria-label="Поиск по коду или наименованию"
        placeholder="Поиск по коду или наименованию"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="mb-3 max-w-sm"
      />
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-[var(--ds-surface-sunken)] text-left text-xs tracking-wide text-muted-foreground uppercase">
            <th className="px-4 py-2.5 font-normal">Код</th>
            <th className="px-4 py-2.5 font-normal">Наименование</th>
            {isAdmin && <th className="w-10" />}
          </tr>
        </thead>
        <tbody>
          {filtered.map((a) => {
            const depth = a.article_code.split(".").length - 1
            return (
              <tr key={a.id} className="border-t border-[var(--ds-hairline)]">
                <td className="px-4 py-2 font-mono text-xs">
                  {a.article_code}
                </td>
                <td
                  className="px-4 py-2"
                  style={{ paddingLeft: `${1 + depth * 1.25}rem` }}
                >
                  {a.name}
                </td>
                {isAdmin && (
                  <td className="px-4 py-2">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button type="button" aria-label="Удалить">
                          <Trash2 className="size-4 text-destructive" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Удалить статью?</AlertDialogTitle>
                          <AlertDialogDescription>
                            «{a.name}» ({a.article_code}) будет удалена.
                            Действие необратимо.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Отмена</AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete?.(a.id)}>
                            Удалить
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
