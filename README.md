# Автоматизатор строительных смет (CIW)

Веб-приложение: загружает целевую смету (Excel), отбирает строки видов работ
(«Вид раздела» = «СМР») и через RAG-подход (векторный поиск + LLM) сопоставляет
их с эталонным справочником статей СМР.

## Архитектура

- **`backend/`** — FastAPI, Clean Architecture (`api → services → domain ← infrastructure`),
  PostgreSQL + pgvector, OpenRouter `gemini-embedding-2` (эмбеддинги) + Anthropic Claude (арбитр). Зависимости — `uv`.
- **`frontend/`** — Vite + React + TypeScript + Tailwind + shadcn/ui + Lucide.
- **`justfile`** — единый task runner.
- **`.github/`** — CI (ruff/pytest + eslint/vitest).

> Без Docker. Бэкенд работает строго в `.venv` (uv). База данных — в облаке (Neon/Supabase).

## Быстрый старт

```bash
# 0. Требуется: uv (https://astral.sh/uv), Node 18+, just
just install                      # uv sync + npm install

# 1. Настроить окружение бэкенда
cp backend/.env.example backend/.env   # заполнить DATABASE_URL, ADMIN_EMAIL/ADMIN_PASSWORD и ключи API
just migrate                          # применить Alembic-миграции (alembic upgrade head)
just create-admin                     # завести первого админа из ADMIN_EMAIL/ADMIN_PASSWORD (нужен для входа)

# 2. Запуск (в двух терминалах)
just dev-back                     # FastAPI на :8260
just dev-front                    # Vite на :5173 (проксирует /api на :8260)
```

После загрузки/правки справочника посчитать эмбеддинги: `just embed-worker --once`
(нужно для RAG-сопоставления; воркер пока ручной).

## Команды

| Команда        | Действие                                  |
|----------------|-------------------------------------------|
| `just install` | Установка зависимостей фронта и бэка       |
| `just migrate` | Применить миграции к БД (`alembic upgrade head`) |
| `just migrate-down` | Откатить последнюю миграцию          |
| `just makemigration name="..."` | Сгенерировать новую ревизию |
| `just create-admin` | Создать/повысить админа из `ADMIN_EMAIL`/`ADMIN_PASSWORD` |
| `just embed-worker [--once]` | Посчитать эмбеддинги справочника (`embedding IS NULL`) |
| `just dev-back`| FastAPI с hot-reload (`uv run uvicorn`)    |
| `just dev-front`| Vite dev-сервер                          |
| `just lint`    | ruff + eslint + prettier `--check`         |
| `just fmt`     | ruff `--fix`/`format` + prettier `--write` |
| `just test`    | pytest + vitest                            |
| `just build`   | Production-сборка фронтенда                |

## Логика сопоставления (RAG)

1. Строка сметы векторизуется (`gemini-embedding-2` через OpenRouter, 768 dim).
2. В БД ищутся топ-3 ближайшие статьи (pgvector, косинусная близость).
3. `score > 0.90` → «Уверенное совпадение».
4. Иначе → топ-3 передаются Claude 3.5 Sonnet для выбора → «Требует проверки».

См. журнал работ в [`docs/devlog/`](docs/devlog/).
