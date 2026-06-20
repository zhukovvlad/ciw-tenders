// frontend/src/App.tsx
import { useState } from "react"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"

export function App() {
  const [tab, setTab] = useState<"estimate" | "articles">("estimate")
  return (
    <AuthGate>
      <AppShell tab={tab} onTab={setTab}>
        {tab === "estimate" ? <EstimateFlow /> : <ArticlesPage />}
      </AppShell>
    </AuthGate>
  )
}

export default App
