# Фронтенд — CIW

Vite + React + TypeScript + Tailwind v4 + shadcn/ui. UI «Автоматизатора строительных смет»:
аутентификация (реальный JWT), справочник СМР (admin: загрузка шаблона, добавление, очистка) и
поток смет (пока на моках). Запускается из корня репозитория через `just` (см. корневой README).

## Структура

- `src/lib/api/` — тонкий слой над `fetch`: `client.ts` (единый `ApiError`, Bearer-токен из
  `sessionStorage`, `onUnauthorized`, multipart) + модули `auth`, `articles`.
- `src/lib/auth/` — `AuthContext` (JWT в `sessionStorage`, ключ `ciw.auth.token`) и хук `useAuth`
  (в отдельном `useAuth.ts` ради `react-refresh`).
- `src/pages/ArticlesPage.tsx` + `src/components/articles/*` — справочник СМР (реальный бэкенд).
- `src/pages/estimate/` + `src/lib/mock/` — поток смет на **моках** (не трогать при работе со справочником).
- `src/components/ui/` — вендорные shadcn-компоненты, **не править**.

## Команды (из `frontend/`)

```bash
npm run dev           # Vite dev-сервер (:5173, проксирует /api → :8260)
npm run typecheck     # tsc -b --noEmit (реальная проверка типов по references)
npm run lint          # eslint
npm run format:check  # prettier --check
npm run format        # prettier --write
npm run test          # vitest
npm run build         # tsc -b + vite build
```

Обычно запускают из корня: `just dev-front`, `just lint` (eslint + prettier), `just test`, `just fmt`.

## Конвенции

- Импорты через alias `@/`. Иконки — `lucide-react`.
- Prettier: `printWidth 80`, `endOfLine lf` (`.gitattributes` форсит LF). TypeScript strict +
  `erasableSyntaxOnly` (без parameter properties/enum).
- Тесты — vitest + React Testing Library; API/`fetch` мокаются (`vi.spyOn`/`vi.stubGlobal`), без реальной сети.

## Добавить shadcn-компонент

```bash
npx shadcn@latest add button   # попадёт в src/components/ui/
```
