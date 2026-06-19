# Автоматизатор строительных смет (CIW)

Веб-приложение: загружает целевую смету (Excel), отбирает строки видов работ
(«Вид раздела» = «СМР») и через RAG-подход (векторный поиск + LLM) сопоставляет
их с эталонным справочником статей СМР.

## Архитектура

- **`backend/`** — FastAPI, Clean Architecture (`api → services → domain ← infrastructure`),
  PostgreSQL + pgvector, Gemini (эмбеддинги) + Anthropic Claude (арбитр). Зависимости — `uv`.
- **`frontend/`** — Vite + React + TypeScript + Tailwind + shadcn/ui + Lucide.
- **`justfile`** — единый task runner.
- **`.github/`** — CI (ruff/pytest + eslint/vitest).

> Без Docker. Бэкенд работает строго в `.venv` (uv). База данных — в облаке (Neon/Supabase).

## Быстрый старт

```bash
# 0. Требуется: uv (https://astral.sh/uv), Node 18+, just
just install                      # uv sync + npm install

# 1. Настроить окружение бэкенда
cp backend/.env.example backend/.env   # заполнить DATABASE_URL и ключи API
psql "$DATABASE_URL" -f backend/migrations/001_init.sql

# 2. Запуск (в двух терминалах)
just dev-back                     # FastAPI на :8260
just dev-front                    # Vite на :5173 (проксирует /api на :8260)
```

## Команды

| Команда        | Действие                                  |
|----------------|-------------------------------------------|
| `just install` | Установка зависимостей фронта и бэка       |
| `just dev-back`| FastAPI с hot-reload (`uv run uvicorn`)    |
| `just dev-front`| Vite dev-сервер                          |
| `just lint`    | ruff + eslint                              |
| `just test`    | pytest + vitest                            |
| `just build`   | Production-сборка фронтенда                |

## Логика сопоставления (RAG)

1. Строка сметы векторизуется (Gemini `text-embedding-004`, 768 dim).
2. В БД ищутся топ-3 ближайшие статьи (pgvector, косинусная близость).
3. `score > 0.90` → «Уверенное совпадение».
4. Иначе → топ-3 передаются Claude 3.5 Sonnet для выбора → «Требует проверки».

См. журнал работ в [`docs/devlog/`](docs/devlog/).
