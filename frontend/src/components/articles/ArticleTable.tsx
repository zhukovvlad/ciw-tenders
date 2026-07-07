import { useMemo, useState } from "react"
import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
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
  const { t } = useTranslation()
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
        aria-label={t("articles.searchAria")}
        placeholder={t("articles.searchPlaceholder")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="mb-3 max-w-sm"
      />
      <DsTable>
        <DsTableHeader>
          <DsTableRow>
            <DsTableHead>{t("articles.colCode")}</DsTableHead>
            <DsTableHead>{t("articles.colName")}</DsTableHead>
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
                        <button
                          type="button"
                          aria-label={t("articles.deleteAria")}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            {t("articles.deleteTitle")}
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            {t("articles.deleteBody", {
                              name: a.name,
                              code: a.article_code,
                            })}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>
                            {t("common.cancel")}
                          </AlertDialogCancel>
                          <AlertDialogAction onClick={() => onDelete?.(a.id)}>
                            {t("common.delete")}
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
