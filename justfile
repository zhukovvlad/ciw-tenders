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
    cd {{backend}}; uv run uvicorn app.main:app --reload --reload-exclude "*.log" --port 8260

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

# Засеять бенчмарк gold-разметки из размеченного xlsx: just benchmark-seed "temp/..."
benchmark-seed gold name="":
    cd {{backend}}; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.benchmark_seed --gold "{{justfile_directory()}}/{{gold}}" $(if ("{{name}}") {"--name"; "{{name}}"})

# Оффлайн-метрика матчинга по бенчмарку: just eval-matching [benchmark="<name>"]
eval-matching benchmark="":
    cd {{backend}}; $env:PYTHONIOENCODING="utf-8"; uv run python -m app.scripts.eval_matching $(if ("{{benchmark}}") {"--benchmark"; "{{benchmark}}"})

# Celery-воркер: матчинг смет + эмбеддинг справочника. По умолчанию solo-pool (Windows).
# Доставка задач идёт через списки LPUSH/BRPOP — права на каналы Redis не нужны. Чтобы воркер
# не падал с "NoPermissionError: No permissions to access a channel" на Redis-ACL без прав на
# каналы, ВСЕ fanout pub/sub отключены ДВУМЯ независимыми механизмами:
#   - --without-mingle/--without-gossip (ниже): startup-sync с соседями + gossip-fanout;
#   - worker_enable_remote_control=False (celery_app.py): управляющий pidbox-мейлбокс
#     (`celery inspect`/`control`) — его флаги НЕ отключают, только эта настройка.
# Прод (Linux): just celery-worker "--pool=prefork --concurrency=4 --loglevel=info" —
# переопределяет args целиком и вернёт mingle/gossip (если на прод-Redis каналы разрешены),
# НО remote-control останется off (управляется конфигом, не флагами): для `celery inspect`
# верни worker_enable_remote_control=True в celery_app.py + выдай права на каналы.
celery-worker *args="--pool=solo --loglevel=info --without-mingle --without-gossip":
    cd {{backend}}; $env:LOG_DIR="logs/celery"; uv run celery -A app.infrastructure.tasks.celery_app worker {{args}}

# MinIO (S3-хранилище оригиналов смет): API на :9000, консоль на :9001, данные в ./minio-data (gitignored).
# Учётки по умолчанию minioadmin/minioadmin — держать в согласии с S3_ACCESS_KEY/S3_SECRET_KEY в backend/.env.
minio:
    minio server minio-data --console-address ":9001"
