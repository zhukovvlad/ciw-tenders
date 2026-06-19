import { Building2, FileSpreadsheet, Library } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { ArticlesPage } from "@/pages/ArticlesPage"
import { EstimatePage } from "@/pages/EstimatePage"

type Tab = "articles" | "estimate"

export function App() {
  const [tab, setTab] = useState<Tab>("estimate")

  return (
    <div className="min-h-svh bg-background">
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-2 font-semibold">
            <Building2 className="size-5" />
            Автоматизатор строительных смет
          </div>
          <nav className="flex gap-2">
            <Button
              variant={tab === "estimate" ? "default" : "ghost"}
              onClick={() => setTab("estimate")}
            >
              <FileSpreadsheet className="size-4" />
              Загрузка сметы
            </Button>
            <Button
              variant={tab === "articles" ? "default" : "ghost"}
              onClick={() => setTab("articles")}
            >
              <Library className="size-4" />
              Справочник
            </Button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        {tab === "estimate" ? <EstimatePage /> : <ArticlesPage />}
      </main>
    </div>
  )
}

export default App
