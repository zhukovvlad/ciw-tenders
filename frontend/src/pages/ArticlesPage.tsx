import { useCallback, useEffect, useState } from "react"
import { AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { ArticleTable } from "@/components/articles/ArticleTable"
import { ManualAddForm } from "@/components/articles/ManualAddForm"
import { WipeCatalog } from "@/components/articles/WipeCatalog"
import { TemplateUpload } from "@/components/articles/TemplateUpload"
import { listArticles, deleteArticle } from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/useAuth"
import type { Article } from "@/lib/types"

export function ArticlesPage() {
  const { role } = useAuth()
  const isAdmin = role === "admin"
  const [articles, setArticles] = useState<Article[]>([])
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading")
  const [actionError, setActionError] = useState<string | null>(null)

  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => {
    setActionError(null)
    setStatus("loading")
    setReloadKey((k) => k + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    listArticles()
      .then((data) => {
        if (!cancelled) {
          setArticles(data)
          setStatus("ready")
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("error")
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  async function handleDelete(id: number) {
    if (!window.confirm("Удалить статью?")) return
    setActionError(null)
    try {
      await deleteArticle(id)
      reload()
    } catch (err) {
      // никаких тихих провалов — показываем ошибку удаления
      setActionError(
        err instanceof ApiError ? err.message : "Не удалось удалить статью"
      )
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">Справочник СМР</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        Эталонные статьи строительных работ.
      </p>

      {isAdmin && (
        <div className="mb-6 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Загрузить шаблон
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TemplateUpload onApplied={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                Добавить статью вручную
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ManualAddForm onCreated={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">Опасная зона</CardTitle>
            </CardHeader>
            <CardContent>
              <WipeCatalog onWiped={() => void reload()} />
            </CardContent>
          </Card>
        </div>
      )}

      {status === "loading" && (
        <div className="space-y-2" aria-label="Загрузка">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
      {status === "error" && (
        <div>
          <Alert variant="destructive" className="mb-3">
            <AlertCircle className="size-4" />
            <AlertTitle>Не удалось загрузить справочник.</AlertTitle>
          </Alert>
          <Button onClick={() => void reload()}>Повторить</Button>
        </div>
      )}
      {status === "ready" && articles.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Справочник пуст{isAdmin ? " — загрузите шаблон." : "."}
        </p>
      )}
      {actionError && (
        <p className="mb-3 text-sm text-destructive">{actionError}</p>
      )}
      {status === "ready" && articles.length > 0 && (
        <ArticleTable
          articles={articles}
          isAdmin={isAdmin}
          onDelete={handleDelete}
        />
      )}
    </div>
  )
}

export default ArticlesPage
