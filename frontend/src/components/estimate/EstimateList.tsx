import { useCallback, useEffect, useState } from "react"
import { Trash2 } from "lucide-react"
import { toast } from "sonner"
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
import { Alert, AlertTitle } from "@/components/ui/alert"
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
import { apiErrorText } from "@/lib/api/errorText"
import { formatDate } from "@/lib/formatDate"
import {
  deleteEstimate,
  listEstimates,
  type EstimateListItem,
} from "@/lib/api/estimates"

export interface EstimateListProps {
  onOpen: (item: EstimateListItem) => void
}

type BadgeVariant = "default" | "secondary" | "outline" | "destructive"

interface StatusMeta {
  labelKey: string | undefined
  variant: BadgeVariant
  clickable: boolean
}

// eslint-disable-next-line react-refresh/only-export-components -- STATUS_META is a tested public API consumed by parent screens
export const STATUS_META: Record<string, StatusMeta> = {
  ready: { labelKey: "statuses.ready", variant: "default", clickable: true },
  partial_error: {
    labelKey: "statuses.partialError",
    variant: "outline",
    clickable: true,
  },
  pending: {
    labelKey: "statuses.processing",
    variant: "secondary",
    clickable: true,
  },
  running: {
    labelKey: "statuses.processing",
    variant: "secondary",
    clickable: true,
  },
  blocked: {
    labelKey: "statuses.blocked",
    variant: "destructive",
    clickable: false,
  },
}

function metaFor(status: string) {
  return (
    STATUS_META[status] ?? {
      labelKey: undefined,
      variant: "secondary" as BadgeVariant,
      clickable: false,
    }
  )
}

const PAGE = 50

export function EstimateList({ onOpen }: EstimateListProps) {
  const { t, i18n } = useTranslation()
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
        if (!cancelled) setError(apiErrorText(err, t, "estimates.loadFailed"))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t/apiErrorText stable enough; reloadKey drives refetch
  }, [reloadKey])

  async function loadMore() {
    if (items === null || loadingMore) return
    setLoadingMore(true)
    try {
      const r = await listEstimates({ limit: PAGE, offset: items.length })
      setItems((prev) => [...(prev ?? []), ...r.items])
    } catch (err) {
      toast.error(apiErrorText(err, t, "estimates.loadFailed"))
    } finally {
      setLoadingMore(false)
    }
  }

  async function remove(id: number) {
    try {
      await deleteEstimate(id)
      toast.success(t("estimates.deleted"))
      triggerReload()
    } catch (err) {
      toast.error(apiErrorText(err, t, "estimates.deleteFailed"))
    }
  }

  if (error) {
    return (
      <Alert variant="destructive" role="alert">
        <AlertTitle>{error}</AlertTitle>
      </Alert>
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
      <p className="text-sm text-muted-foreground">{t("estimates.empty")}</p>
    )
  }

  return (
    <>
      <DsTable>
        <DsTableHeader>
          <DsTableRow>
            <DsTableHead>{t("estimates.colFile")}</DsTableHead>
            <DsTableHead>{t("estimates.colStatus")}</DsTableHead>
            <DsTableHead>{t("estimates.colReview")}</DsTableHead>
            <DsTableHead className="text-right">
              {t("estimates.colNodes")}
            </DsTableHead>
            <DsTableHead>{t("estimates.colDate")}</DsTableHead>
            <DsTableHead className="w-10" />
          </DsTableRow>
        </DsTableHeader>
        <DsTableBody>
          {items.map((item) => {
            const meta = metaFor(item.status)
            return (
              <DsTableRow
                key={item.id}
                interactive={meta.clickable}
                onClick={meta.clickable ? () => onOpen(item) : undefined}
              >
                <DsTableCell>
                  {meta.clickable ? (
                    <button
                      type="button"
                      className="font-medium hover:underline"
                      onClick={(event) => {
                        event.stopPropagation()
                        onOpen(item)
                      }}
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
                  <Badge variant={meta.variant}>
                    {meta.labelKey ? t(meta.labelKey) : item.status}
                  </Badge>
                </DsTableCell>
                <DsTableCell className="text-muted-foreground tabular-nums">
                  {item.completedAt !== null ? (
                    <Badge>{t("estimates.completed")}</Badge>
                  ) : item.totalReviewable > 0 ? (
                    t("estimates.reviewedOf", {
                      reviewed: item.reviewedCount,
                      total: item.totalReviewable,
                    })
                  ) : (
                    "—"
                  )}
                </DsTableCell>
                <DsTableCell className="text-right tabular-nums">
                  {item.nodesCount}
                </DsTableCell>
                <DsTableCell className="text-muted-foreground">
                  {formatDate(item.createdAt, i18n.language)}
                </DsTableCell>
                <DsTableCell>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <button
                        type="button"
                        aria-label={t("estimates.deleteAria", {
                          filename: item.filename,
                        })}
                        className="rounded-sm p-1 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                        onClick={(event) => event.stopPropagation()}
                      >
                        <Trash2 className="size-4 text-destructive" />
                      </button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          {t("estimates.deleteTitle")}
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          {t("estimates.deleteBody", {
                            filename: item.filename,
                          })}
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          {t("common.cancel")}
                        </AlertDialogCancel>
                        <AlertDialogAction onClick={() => void remove(item.id)}>
                          {t("common.delete")}
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
            {t("estimates.showMore")}
          </Button>
        </div>
      )}
    </>
  )
}
