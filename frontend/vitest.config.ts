import path from "path"
import { defineConfig } from "vitest/config"

// Отдельный конфиг для тестов: vite-плагины здесь не нужны (esbuild трансформирует
// JSX/TSX), а их подключение конфликтует по типам с версией vite внутри vitest.
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
})
