// frontend/src/components/AppShell.tsx
import { ChevronDown, FileSpreadsheet, Library } from "lucide-react"
import { Link, useLocation, useNavigate } from "react-router-dom"
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

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, role, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const tab = location.pathname.startsWith("/articles")
    ? "articles"
    : "estimate"
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-5 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-6 py-3">
        <Link to="/estimates" className="font-display text-base">
          MR <span className="text-[var(--ds-accent-hover)]">·</span> Сметы
        </Link>
        <Tabs
          value={tab}
          onValueChange={(v) =>
            navigate(v === "articles" ? "/articles" : "/estimates")
          }
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
            <DropdownMenuTrigger className="ml-auto flex items-center gap-1 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
              {user.email}
              <ChevronDown className="size-3.5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {role === "admin" ? "Администратор" : "Пользователь"}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => logout()}>
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
