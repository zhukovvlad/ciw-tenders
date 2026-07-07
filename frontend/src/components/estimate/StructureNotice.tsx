import { useState } from "react"
import { useTranslation } from "react-i18next"
import { ChevronDown, ChevronRight } from "lucide-react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  DsTable,
  DsTableBody,
  DsTableCell,
  DsTableHead,
  DsTableHeader,
  DsTableRow,
} from "@/components/common/ds-table"
import type { StructuralAnomaly } from "@/lib/types"

// Блок «Структура сметы» — справка по результату парсинга. Аномалии
// персистятся на бэке (estimates.structure_anomalies) и приходят в
// GET /estimates/{id} — переживают F5 и прямую ссылку (этап 3 UX).

export interface StructureNoticeProps {
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

const KIND_KEYS: Record<string, string> = {
  duplicate_code: "structure.kindDuplicate",
  parent_below: "structure.kindParentBelow",
  parent_missing: "structure.kindParentMissing",
  depth_jump: "structure.kindDepthJump",
}

// Возвращает ключ словаря для известных kind; для неизвестных — сырой kind
// (t() на несуществующем ключе просто возвращает его же строкой — fallback
// срабатывает сам собой).
function kindLabel(kind: string): string {
  return KIND_KEYS[kind] ?? kind
}

export function StructureNotice({
  anomalies,
  outlineOverrides,
}: StructureNoticeProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  if (anomalies.length === 0 && outlineOverrides === 0) return null

  // Когда построчных аномалий нет (только агрегат outline) — не показываем «0 замечаний».
  const title =
    anomalies.length > 0
      ? t("structure.title", { count: anomalies.length })
      : t("structure.titlePlain")

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="mb-4">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-md border bg-muted/50 px-3 py-2 text-sm font-medium hover:bg-muted"
        >
          {open ? (
            <ChevronDown className="size-4 shrink-0" />
          ) : (
            <ChevronRight className="size-4 shrink-0" />
          )}
          {title}
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent className="mt-1 rounded-md border bg-background">
        {anomalies.length > 0 && (
          <DsTable>
            <DsTableHeader>
              <DsTableRow>
                <DsTableHead>{t("structure.colType")}</DsTableHead>
                <DsTableHead>{t("structure.colCode")}</DsTableHead>
                <DsTableHead>{t("structure.colName")}</DsTableHead>
                <DsTableHead>{t("structure.colDetails")}</DsTableHead>
              </DsTableRow>
            </DsTableHeader>
            <DsTableBody>
              {anomalies.map((a) => (
                <DsTableRow key={`${a.sourceIndex}-${a.kind}`}>
                  <DsTableCell className="text-xs whitespace-nowrap">
                    {t(kindLabel(a.kind))}
                  </DsTableCell>
                  <DsTableCell className="font-mono text-xs">
                    {a.code}
                  </DsTableCell>
                  <DsTableCell className="text-xs">{a.name}</DsTableCell>
                  <DsTableCell className="text-xs text-muted-foreground">
                    {a.detail}
                  </DsTableCell>
                </DsTableRow>
              ))}
            </DsTableBody>
          </DsTable>
        )}

        {outlineOverrides > 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            {t("structure.outlineNote", { count: outlineOverrides })}
          </p>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
