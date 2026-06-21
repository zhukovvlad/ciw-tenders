import { useState } from "react"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"

export function App() {
  const [tab, setTab] = useState<"estimate" | "articles">("estimate")
  return (
    <AuthProvider>
      <AuthGate>
        <AppShell tab={tab} onTab={setTab}>
          {tab === "estimate" ? <EstimateFlow /> : <ArticlesPage />}
        </AppShell>
      </AuthGate>
    </AuthProvider>
  )
}

export default App
