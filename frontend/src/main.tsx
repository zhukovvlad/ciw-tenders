import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { I18nextProvider } from "react-i18next"

import "./index.css"
import App from "./App.tsx"
import { ThemeProvider } from "@/components/theme-provider.tsx"
import i18n from "@/lib/i18n"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nextProvider i18n={i18n}>
      <ThemeProvider defaultTheme="dark">
        <App />
      </ThemeProvider>
    </I18nextProvider>
  </StrictMode>
)
