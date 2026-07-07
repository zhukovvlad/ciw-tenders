import { useCallback, useEffect, useState } from "react"
import { AlertCircle } from "lucide-react"
import { toast } from "sonner"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { ArticleTable } from "@/components/articles/ArticleTable"
import { ManualAddForm } from "@/components/articles/ManualAddForm"
import { WipeCatalog } from "@/components/articles/WipeCatalog"
import { TemplateUpload } from "@/components/articles/TemplateUpload"
import { listArticles, deleteArticle } from "@/lib/api/articles"
import { apiErrorText } from "@/lib/api/errorText"
import { useAuth } from "@/lib/auth/useAuth"
import type { Article } from "@/lib/types"

export function ArticlesPage() {
  const { t } = useTranslation()
  const { role } = useAuth()
  const isAdmin = role === "admin"
  const [articles, setArticles] = useState<Article[]>([])
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading")

  const [reloadKey, setReloadKey] = useState(0)
  const reload = useCallback(() => {
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
    try {
      await deleteArticle(id)
      toast.success(t("articles.deleted"))
      reload()
    } catch (err) {
      toast.error(apiErrorText(err, t, "articles.deleteFailed"))
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">{t("articles.title")}</h2>
      <p className="mb-4 text-sm text-muted-foreground">
        {t("articles.subtitle")}
      </p>

      {isAdmin && (
        <div className="mb-6 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                {t("articles.uploadTemplate")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TemplateUpload onApplied={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                {t("articles.addManual")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ManualAddForm onCreated={() => void reload()} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">
                {t("articles.dangerZone")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <WipeCatalog onWiped={() => void reload()} />
            </CardContent>
          </Card>
        </div>
      )}

      {status === "loading" && (
        <div className="space-y-2" aria-label={t("articles.loadingAria")}>
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}
      {status === "error" && (
        <div>
          <Alert variant="destructive" className="mb-3">
            <AlertCircle className="size-4" />
            <AlertTitle>{t("articles.loadFailed")}</AlertTitle>
          </Alert>
          <Button onClick={() => void reload()}>{t("common.retry")}</Button>
        </div>
      )}
      {status === "ready" && articles.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {isAdmin ? t("articles.emptyAdmin") : t("articles.empty")}
        </p>
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
