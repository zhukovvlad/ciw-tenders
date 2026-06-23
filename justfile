# Task runner для «Автоматизатор строительных смет».
# Бэкенд работает строго в .venv через `uv run`. Docker не используется.
#
# Используется Windows PowerShell 5.1, который НЕ поддерживает оператор `&&`,
# поэтому команды внутри одной строки разделяются `;` (каждая строка рецепта
# выполняется в отдельном вызове оболочки, cwd сбрасывается на корень проекта).

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

backend := "backend"
frontend := "frontend"

# Список доступных команд.
default:
    @just --list

# Установка зависимостей бэкенда (.venv через uv) и фронтенда.
install:
    cd {{backend}}; uv sync
    cd {{frontend}}; npm install

# Применить миграции к БД (alembic upgrade head). Требует DATABASE_URL в backend/.env.
migrate:
    cd {{backend}}; uv run alembic upgrade head

# Откатить последнюю миграцию.
migrate-down:
    cd {{backend}}; uv run alembic downgrade -1

# Сгенерировать новую ревизию из ORM-моделей: just makemigration name="add x"
makemigration name:
    cd {{backend}}; uv run alembic revision --autogenerate -m "{{name}}"

# Запуск FastAPI (hot-reload) в виртуальном окружении.
dev-back:
    cd {{backend}}; uv run uvicorn app.main:app --reload --port 8260

# Запуск Vite dev-сервера.
dev-front:
    cd {{frontend}}; npm run dev

# Линтинг бэкенда (ruff) и фронтенда (eslint + prettier --check).
lint:
    cd {{backend}}; uv run ruff check .
    cd {{frontend}}; npm run lint
    cd {{frontend}}; npm run format:check

# Автоформатирование/исправление.
fmt:
    cd {{backend}}; uv run ruff check --fix .; uv run ruff format .
    cd {{frontend}}; npm run format

# Тесты бэкенда (pytest) и фронтенда (vitest).
test:
    cd {{backend}}; uv run pytest
    cd {{frontend}}; npm run test

# Production-сборка фронтенда.
build:
    cd {{frontend}}; npm run build

# Создать/повысить первого администратора из ADMIN_EMAIL/ADMIN_PASSWORD (backend/.env).
create-admin:
    cd {{backend}}; uv run python -m app.scripts.create_admin

# Celery-воркер: матчинг смет + эмбеддинг справочника (dev: solo-pool для Windows).
celery-worker:
    cd {{backend}}; uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo --loglevel=info
