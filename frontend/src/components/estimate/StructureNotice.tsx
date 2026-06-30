import { useState } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { StructuralAnomaly } from "@/lib/types"

// Блок «Структура сметы» — транзиентная справка по результату загрузки.
// Показывается на фазе review над ReviewScreen, не персистируется в session:
// при перезагрузке страницы данные теряются (осознанное ограничение Task 7).

export interface StructureNoticeProps {
  anomalies: StructuralAnomaly[]
  outlineOverrides: number
}

const KIND_LABELS: Record<string, string> = {
  duplicate_code: "Дубль кода",
  parent_below: "Родитель ниже",
  parent_missing: "Нет родителя",
  depth_jump: "Скачок глубины",
}

function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind
}

function pluralizeZamechanie(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return `${n} замечание`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20))
    return `${n} замечания`
  return `${n} замечаний`
}

export function StructureNotice({
  anomalies,
  outlineOverrides,
}: StructureNoticeProps) {
  const [open, setOpen] = useState(false)

  if (anomalies.length === 0 && outlineOverrides === 0) return null

  // Когда построчных аномалий нет (только агрегат outline) — не показываем «0 замечаний».
  const title =
    anomalies.length > 0
      ? `Структура сметы: ${pluralizeZamechanie(anomalies.length)}`
      : "Структура сметы"

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
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Тип</TableHead>
                <TableHead>Код</TableHead>
                <TableHead>Наименование</TableHead>
                <TableHead>Детали</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {anomalies.map((a) => (
                <TableRow key={`${a.sourceIndex}-${a.kind}`}>
                  <TableCell className="text-xs whitespace-nowrap">
                    {kindLabel(a.kind)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{a.code}</TableCell>
                  <TableCell className="text-xs">{a.name}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {a.detail}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}

        {outlineOverrides > 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">
            В {outlineOverrides} строк(ах) вложенность взята из группировки
          </p>
        )}
      </CollapsibleContent>
    </Collapsible>
  )
}
