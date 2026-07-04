// Единственный источник табличного стиля MR DS (спека этапа 3 §3):
// обёртки над shadcn-примитивами (ui/table.tsx — вендорный, не правится)
// + классы-константы для поверхностей, которые не могут быть <table>
// (виртуализированный ReviewGrid, ContextStrip).
import * as React from "react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

/** Ячейка шапки. h-auto гасит вендорный h-10, font-normal — font-medium. */
export const dsHeadCellClass =
  "h-auto px-4 py-2.5 text-xs font-normal tracking-wide uppercase text-muted-foreground"
/** Ячейка тела. whitespace-normal гасит вендорный nowrap (длинные наименования). */
export const dsCellClass = "px-4 py-2 text-sm whitespace-normal"
/** Цвет границ табличного семейства. */
export const dsHairline = "border-[var(--ds-hairline)]"
/** Фон ряда шапки. */
export const dsHeadRowClass = "bg-[var(--ds-surface-sunken)]"

export const DsTable = Table
export const DsTableBody = TableBody

export function DsTableHeader({
  className,
  ...props
}: React.ComponentProps<typeof TableHeader>) {
  return <TableHeader className={cn(dsHeadRowClass, className)} {...props} />
}

export function DsTableHead({
  className,
  ...props
}: React.ComponentProps<typeof TableHead>) {
  return <TableHead className={cn(dsHeadCellClass, className)} {...props} />
}

interface DsTableRowProps extends React.ComponentProps<typeof TableRow> {
  /**
   * Кликабельность КОНКРЕТНОЙ строки, не поверхности (спека §2): hover —
   * только там, где клик что-то делает. Вендорный TableRow несёт
   * hover:bg-muted/50 всегда; tailwind-merge заменяет конфликтующие классы,
   * но не удаляет — неинтерактивный вариант гасит его hover:bg-transparent.
   */
  interactive?: boolean
}

export function DsTableRow({
  className,
  interactive = false,
  ...props
}: DsTableRowProps) {
  return (
    <TableRow
      className={cn(
        dsHairline,
        interactive ? "cursor-pointer" : "hover:bg-transparent",
        className
      )}
      {...props}
    />
  )
}

export function DsTableCell({
  className,
  ...props
}: React.ComponentProps<typeof TableCell>) {
  return <TableCell className={cn(dsCellClass, className)} {...props} />
}
