// frontend/src/components/AppShell.tsx
import { ChevronDown, CircleUser, FileSpreadsheet, Library } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useAuth } from "@/lib/auth/useAuth"

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, role, logout } = useAuth()
  const { t, i18n } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const tab = location.pathname.startsWith("/articles")
    ? "articles"
    : "estimate"
  const [brandLeft, brandRight] = t("nav.brand").split(" · ")
  return (
    <div className="min-h-svh bg-background">
      <header className="flex items-center gap-3 border-b border-[var(--ds-hairline)] bg-[var(--ds-surface-sunken)] px-3 py-3 md:gap-5 md:px-6">
        <Link to="/estimates" className="font-display text-base">
          {brandLeft} <span className="text-[var(--ds-accent-hover)]">·</span>{" "}
          {brandRight}
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
              {t("nav.tabEstimate")}
            </TabsTrigger>
            <TabsTrigger value="articles">
              <Library className="size-4" />
              {t("nav.tabArticles")}
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label={user.email}
              className="ml-auto flex items-center gap-1 rounded-sm text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <CircleUser aria-hidden="true" className="size-4 md:hidden" />
              <span className="hidden md:inline">{user.email}</span>
              <ChevronDown className="size-3.5" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {role === "admin" ? t("nav.roleAdmin") : t("nav.roleUser")}
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuRadioGroup
                value={i18n.language.startsWith("tr") ? "tr" : "ru"}
                onValueChange={(lng) => void i18n.changeLanguage(lng)}
              >
                <DropdownMenuRadioItem value="ru">
                  {t("nav.langRu")}
                </DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="tr">
                  {t("nav.langTr")}
                </DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => logout()}>
                {t("nav.logout")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </header>
      <main>{children}</main>
    </div>
  )
}
