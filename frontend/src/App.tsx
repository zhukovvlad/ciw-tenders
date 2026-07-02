import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"
import { AuthGate } from "@/components/auth/AuthGate"
import { AppShell } from "@/components/AppShell"
import { AuthProvider } from "@/lib/auth/AuthContext"
import { EstimateFlow } from "@/pages/estimate/EstimateFlow"
import { ArticlesPage } from "@/pages/ArticlesPage"
import { Toaster } from "@/components/ui/sonner"

export function App() {
  return (
    <AuthProvider>
      <AuthGate>
        <BrowserRouter>
          <AppShell>
            <Routes>
              <Route path="/" element={<Navigate to="/estimates" replace />} />
              <Route path="/estimates" element={<EstimateFlow />} />
              <Route path="/articles" element={<ArticlesPage />} />
              <Route path="*" element={<Navigate to="/estimates" replace />} />
            </Routes>
          </AppShell>
        </BrowserRouter>
      </AuthGate>
      <Toaster />
    </AuthProvider>
  )
}

export default App
