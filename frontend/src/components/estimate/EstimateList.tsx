import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
import { toast } from "sonner"
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
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "@/components/common/ds-table"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiError } from "@/lib/api/client"
import {
  deleteEstimate,
  listEstimates,
  type EstimateListItem,
} from "@/lib/api/estimates"

export interface EstimateListProps {
  onOpen: (item: EstimateListItem) => void
}

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

// eslint-disable-next-line react-refresh/only-export-components -- STATUS_META is a tested public API consumed by parent screens
export const STATUS_META: Record<
  string,
  { label: string; variant: BadgeVariant; clickable: boolean }
> = {
  ready: { label: "Готово", variant: "default", clickable: true },
  partial_error: {
    label: "Готово с ошибками",
    variant: "outline",
    clickable: true,
  },
  pending: { label: "В обработке", variant: "secondary", clickable: true },
  running: { label: "В обработке", variant: "secondary", clickable: true },
  blocked: { label: "Отклонено", variant: "destructive", clickable: false },
}

function metaFor(status: string) {
  return (
    STATUS_META[status] ?? {
      label: status,
      variant: "secondary" as BadgeVariant,
      clickable: false,
    }
  )
}

const dateFmt = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : dateFmt.format(d)
}

const PAGE = 50

export function EstimateList({ onOpen }: EstimateListProps) {
  const [items, setItems] = useState<EstimateListItem[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [loadingMore, setLoadingMore] = useState(false)

  const triggerReload = useCallback(() => {
    setError(null)
    setItems(null)
    setTotal(0)
    setReloadKey((k) => k + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    listEstimates({ limit: PAGE, offset: 0 })
      .then((data) => {
        if (!cancelled) {
          setItems(data.items)
          setTotal(data.total)
        }
      })
      .catch((err) => {
        if (!cancelled)
          setError(
            err instanceof ApiError ? err.message : "Не удалось загрузить сметы"
          )
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  async function loadMore() {
    if (items === null || loadingMore) return
    setLoadingMore(true)
    try {
      const r = await listEstimates({ limit: PAGE, offset: items.length })
      setItems((prev) => [...(prev ?? []), ...r.items])
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось загрузить сметы"
      )
    } finally {
      setLoadingMore(false)
    }
  }

  async function remove(id: number) {
    try {
      await deleteEstimate(id)
      toast.success("Смета удалена")
      triggerReload()
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Не удалось удалить смету"
      )
    }
  }

  if (error) {
    return (
      <p className="text-sm text-destructive" role="alert">
        {error}
      </p>
    )
  }

  if (items === null) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Пока нет разобранных смет — загрузите файл выше.
      </p>
    )
  }

  return (
    <>
      <DsTable>
        <DsTableHeader>
          <DsTableRow>
            <DsTableHead>Файл</DsTableHead>
            <DsTableHead>Статус</DsTableHead>
            <DsTableHead>Проверка</DsTableHead>
            <DsTableHead className="text-right">Узлов</DsTableHead>
            <DsTableHead>Дата</DsTableHead>
            <DsTableHead className="w-10" />
          </DsTableRow>
        </DsTableHeader>
        <DsTableBody>
          {items.map((item) => {
            const meta = metaFor(item.status)
            return (
              <DsTableRow key={item.id} interactive={meta.clickable}>
                <DsTableCell>
                  {meta.clickable ? (
                    <button
                      type="button"
                      className="text-left font-medium hover:underline"
                      onClick={() => onOpen(item)}
                    >
                      {item.filename}
                    </button>
                  ) : (
                    <span className="font-medium text-muted-foreground">
                      {item.filename}
                    </span>
                  )}
                </DsTableCell>
                <DsTableCell>
                  <Badge variant={meta.variant}>{meta.label}</Badge>
                </DsTableCell>
                <DsTableCell className="text-muted-foreground tabular-nums">
                  {item.completedAt !== null ? (
                    <Badge>Завершена</Badge>
                  ) : item.totalReviewable > 0 ? (
                    `${item.reviewedCount} из ${item.totalReviewable}`
                  ) : (
                    "—"
                  )}
                </DsTableCell>
                <DsTableCell className="text-right tabular-nums">
                  {item.nodesCount}
                </DsTableCell>
                <DsTableCell className="text-muted-foreground">
                  {formatDate(item.createdAt)}
                </DsTableCell>
                <DsTableCell>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <button
                        type="button"
                        aria-label={`Удалить ${item.filename}`}
                        className="rounded-sm p-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Удалить смету?</AlertDialogTitle>
                        <AlertDialogDescription>
                          «{item.filename}» будет удалена безвозвратно.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Отмена</AlertDialogCancel>
                        <AlertDialogAction onClick={() => void remove(item.id)}>
                          Удалить
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </DsTableCell>
              </DsTableRow>
            )
          })}
        </DsTableBody>
      </DsTable>
      {items.length < total && (
        <div className="pt-3">
          <Button
            variant="outline"
            size="sm"
            disabled={loadingMore}
            onClick={() => void loadMore()}
          >
            Показать ещё
          </Button>
        </div>
      )}
    </>
  )
}
