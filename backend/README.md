# CIW Backend

Бэкенд «Автоматизатора строительных смет»: FastAPI + Clean Architecture.

RAG-сопоставление строк сметы с эталонным справочником СМР: векторный поиск
(PostgreSQL + pgvector) → порог уверенности → арбитраж LLM.

## Стек
- Python 3.11+, FastAPI, Uvicorn, Pandas, openpyxl
- SQLAlchemy 2.0 + pgvector (облачный PostgreSQL: Neon / Supabase)
- Gemini `text-embedding-004` (эмбеддинги), Anthropic `claude-3-5-sonnet` (арбитр)
- Управление зависимостями: `uv` (строго `.venv`)

## Слои (направление зависимостей `api → services → domain ← infrastructure`)
- `app/domain` — сущности и порты (абстракции), без внешних зависимостей
- `app/services` — сценарии (парсинг Excel, сопоставление, CRUD)
- `app/infrastructure` — адаптеры портов (БД, Gemini, Anthropic)
- `app/api` — FastAPI: роуты, схемы (DTO), DI (composition root)

## Запуск
```bash
uv sync                         # создаёт .venv и ставит зависимости
cp .env.example .env            # заполнить DATABASE_URL и ключи API
psql "$DATABASE_URL" -f migrations/001_init.sql
uv run uvicorn app.main:app --reload --port 8000
```

## Проверки
```bash
uv run ruff check .
uv run pytest
```
