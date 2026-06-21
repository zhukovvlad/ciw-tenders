import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { ArticleTable } from "@/components/articles/ArticleTable"
import { ManualAddForm } from "@/components/articles/ManualAddForm"
import { WipeCatalog } from "@/components/articles/WipeCatalog"
import { TemplateUpload } from "@/components/articles/TemplateUpload"
import { listArticles, deleteArticle } from "@/lib/api/articles"
import { ApiError } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/AuthContext"
import type { Article } from "@/lib/types"

export function ArticlesPage() {
  const { role } = useAuth()
  const isAdmin = role === "admin"
  const [articles, setArticles] = useState<Article[]>([])
  const [status, setStatus] = useState<"loading" | "error" | "ready">("loading")
  const [actionError, setActionError] = useState<string | null>(null)

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
    if (!window.confirm("Удалить статью?")) return
    setActionError(null)
    try {
      await deleteArticle(id)
      reload()
    } catch (err) {
      // никаких тихих провалов — показываем ошибку удаления
      setActionError(err instanceof ApiError ? err.message : "Не удалось удалить статью")
    }
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 font-display text-lg">Справочник СМР</h2>
      <p className="mb-4 text-sm text-muted-foreground">Эталонные статьи строительных работ.</p>

      {/* Admin-секции загрузки/добавления/очистки добавляются в Task 7-9 */}
      {isAdmin && (
        <div className="mb-6 rounded-md border border-[var(--ds-hairline)] p-4">
          <h3 className="mb-2 text-sm font-medium">Загрузить шаблон</h3>
          <TemplateUpload onApplied={() => void reload()} />
          <div className="mt-4 border-t border-[var(--ds-hairline)] pt-4">
            <h3 className="mb-2 text-sm font-medium">Добавить статью вручную</h3>
            <ManualAddForm onCreated={() => void reload()} />
          </div>
          <div className="mt-4 border-t border-[var(--ds-hairline)] pt-4">
            <h3 className="mb-2 text-sm font-medium">Опасная зона</h3>
            <WipeCatalog onWiped={() => void reload()} />
          </div>
        </div>
      )}

      {status === "loading" && <p className="text-sm text-muted-foreground">Загрузка…</p>}
      {status === "error" && (
        <div className="text-sm">
          <p className="mb-2 text-destructive">Не удалось загрузить справочник.</p>
          <Button onClick={() => void reload()}>Повторить</Button>
        </div>
      )}
      {status === "ready" && articles.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Справочник пуст{isAdmin ? " — загрузите шаблон." : "."}
        </p>
      )}
      {actionError && <p className="mb-3 text-sm text-destructive">{actionError}</p>}
      {status === "ready" && articles.length > 0 && (
        <ArticleTable articles={articles} isAdmin={isAdmin} onDelete={handleDelete} />
      )}
    </div>
  )
}

export default ArticlesPage
