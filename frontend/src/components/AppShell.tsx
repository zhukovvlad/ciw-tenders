// frontend/src/components/AppShell.tsx
import { ChevronDown, FileSpreadsheet, Library } from "lucide-react"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth/useAuth"
import { clearReview } from "@/lib/session"

interface AppShellProps {
  tab: "estimate" | "articles"
  onTab: (t: "estimate" | "articles") => void
  children: React.ReactNode
}

export function AppShell({ tab, onTab, children }: AppShellProps) {
  const { user, role, logout } = useAuth()
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-5 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-6 py-3">
        <span className="font-display text-base">
          MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
        </span>
        <Tabs
          value={tab}
          onValueChange={(v) => {
            if (v === "estimate" || v === "articles") onTab(v);
          }}
        >
          <TabsList>
            <TabsTrigger value="estimate">
              <FileSpreadsheet className="size-4" />
              Смета
            </TabsTrigger>
            <TabsTrigger value="articles">
              <Library className="size-4" />
              Справочник
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger className="ml-auto flex items-center gap-1 text-xs text-muted-foreground outline-none hover:text-foreground">
              {user.email}
              <ChevronDown className="size-3.5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {role === "admin" ? "Администратор" : "Пользователь"}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={() => {
                  clearReview()
                  logout()
                }}
              >
                Выйти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </header>
      <main>{children}</main>
    </div>
  )
}
