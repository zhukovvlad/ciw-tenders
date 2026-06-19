# Task runner для «Автоматизатор строительных смет».
# Бэкенд работает строго в .venv через `uv run`. Docker не используется.

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

backend := "backend"
frontend := "frontend"

# Список доступных команд.
default:
    @just --list

# Установка зависимостей бэкенда (.venv через uv) и фронтенда.
install:
    cd {{backend}} && uv sync
    cd {{frontend}} && npm install

# Применить SQL-миграции к облачной БД (требует $DATABASE_URL).
migrate:
    cd {{backend}} && uv run python -c "import os; print('Run: psql $DATABASE_URL -f migrations/001_init.sql')"

# Запуск FastAPI (hot-reload) в виртуальном окружении.
dev-back:
    cd {{backend}} && uv run uvicorn app.main:app --reload --port 8000

# Запуск Vite dev-сервера.
dev-front:
    cd {{frontend}} && npm run dev

# Линтинг бэкенда (ruff) и фронтенда (eslint).
lint:
    cd {{backend}} && uv run ruff check .
    cd {{frontend}} && npm run lint

# Автоформатирование/исправление.
fmt:
    cd {{backend}} && uv run ruff check --fix . && uv run ruff format .
    cd {{frontend}} && npm run format

# Тесты бэкенда (pytest) и фронтенда (vitest).
test:
    cd {{backend}} && uv run pytest
    cd {{frontend}} && npm run test

# Production-сборка фронтенда.
build:
    cd {{frontend}} && npm run build
