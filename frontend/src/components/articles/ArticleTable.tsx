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
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "@/components/common/ds-table"
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
      <DsTable>
        <DsTableHeader>
          <DsTableRow>
            <DsTableHead>Код</DsTableHead>
            <DsTableHead>Наименование</DsTableHead>
            {isAdmin && <DsTableHead className="w-10" />}
          </DsTableRow>
        </DsTableHeader>
        <DsTableBody>
          {filtered.map((a) => {
            const depth = a.article_code.split(".").length - 1
            return (
              <DsTableRow key={a.id}>
                <DsTableCell className="font-mono text-xs">
                  {a.article_code}
                </DsTableCell>
                <DsTableCell style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
                  {a.name}
                </DsTableCell>
                {isAdmin && (
                  <DsTableCell>
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
                  </DsTableCell>
                )}
              </DsTableRow>
            )
          })}
        </DsTableBody>
      </DsTable>
    </div>
  )
}
