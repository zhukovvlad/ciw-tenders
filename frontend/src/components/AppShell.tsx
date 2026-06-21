// frontend/src/components/AppShell.tsx
import { FileSpreadsheet, Library } from "lucide-react"
import { useAuth } from "@/lib/auth/useAuth"
import { clearReview } from "@/lib/session"

interface AppShellProps {
  tab: "estimate" | "articles"
  onTab: (t: "estimate" | "articles") => void
  children: React.ReactNode
}

export function AppShell({ tab, onTab, children }: AppShellProps) {
  const { user, role, logout } = useAuth()
  const link = (
    key: "estimate" | "articles",
    label: string,
    Icon: typeof FileSpreadsheet
  ) => (
    <button
      onClick={() => onTab(key)}
      className={
        "flex items-center gap-1.5 border-b-2 pb-2 text-sm " +
        (tab === key
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground")
      }
    >
      <Icon className="size-4" />
      {label}
    </button>
  )
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-5 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-6 py-3">
        <span className="font-display text-base">
          MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
        </span>
        <nav className="flex gap-4">
          {link("estimate", "Смета", FileSpreadsheet)}
          {link("articles", "Справочник", Library)}
        </nav>
        <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
          {user && (
            <span>
              {user.email} · {role === "admin" ? "админ" : "пользователь"}
            </span>
          )}
          <button
            onClick={() => {
              clearReview()
              logout()
            }}
            className="hover:text-foreground"
          >
            Выйти
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  )
}
