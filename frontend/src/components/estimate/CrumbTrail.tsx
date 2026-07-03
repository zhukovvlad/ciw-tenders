// Крошка иерархии со средним эллипсисом (спека этапа 2 §3b): цепочка полная
// (включая org-уровни с длинными юр.названиями), при >3 уровней видимы первый
// и два последних; полная цепочка — в title.
import { cn } from "@/lib/utils"

const SEP = " › "

interface CrumbTrailProps {
  levels: string[]
  className?: string
}

export function CrumbTrail({ levels, className }: CrumbTrailProps) {
  if (levels.length === 0) return null
  const shown =
    levels.length <= 3 ? levels : [levels[0], "…", ...levels.slice(-2)]
  return (
    <span
      title={levels.join(SEP)}
      className={cn("text-xs text-muted-foreground", className)}
    >
      {shown.join(SEP)}
    </span>
  )
}
