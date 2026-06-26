# CIW Backend

Бэкенд «Автоматизатора строительных смет»: FastAPI + Clean Architecture.

RAG-сопоставление строк сметы с эталонным справочником СМР: векторный поиск
(PostgreSQL + pgvector) → порог уверенности → арбитраж LLM.

## Стек
- Python 3.11+, FastAPI, Uvicorn, Pandas, openpyxl
- SQLAlchemy 2.0 + pgvector (облачный PostgreSQL: Neon / Supabase)
- OpenRouter `google/gemini-embedding-2` (эмбеддинги, 768 dim), Anthropic `claude-3-5-sonnet` (арбитр)
- Управление зависимостями: `uv` (строго `.venv`)

## Слои (направление зависимостей `api → services → domain ← infrastructure`)
- `app/domain` — сущности и порты (абстракции), без внешних зависимостей
- `app/services` — сценарии (парсинг Excel, сопоставление, CRUD)
- `app/infrastructure` — адаптеры портов (БД, OpenRouter, Anthropic)
- `app/api` — FastAPI: роуты, схемы (DTO), DI (composition root)

## Запуск
```bash
uv sync                         # создаёт .venv и ставит зависимости
cp .env.example .env            # заполнить DATABASE_URL и ключи API
uv run alembic upgrade head     # применить миграции (Alembic)
uv run uvicorn app.main:app --reload --port 8260
```

## Проверки
```bash
uv run ruff check .
uv run pytest
```

## Логирование
Централизованное логирование на stdlib `logging` (`app/core/logging_config.py`, `setup_logging()`):
консоль (stdout) + ротируемые файлы `logs/app.log` (DEBUG) и `logs/errors.log` (WARNING+).
Сквозная корреляция `request_id → task_id` (web-middleware → заголовок Celery) попадает в каждую
строку лога. AI-вызовы пишут summary (провайдер/модель/латентность/попытки).

Конфиг — через env (не `Settings`):
- `LOG_LEVEL` — уровень консоли (default `INFO`; файлы фиксированы: app=DEBUG, errors=WARNING).
- `LOG_TO_FILE` — `1` (default) пишет файлы; `0` — только консоль (прод-агрегатор / Celery prefork).
- `LOG_DIR` — каталог логов (default `backend/logs`, в `.gitignore`).

В коде: `logger = logging.getLogger(__name__)` — не `print`. Подробности и правила для агентов —
в [CLAUDE.md](../CLAUDE.md#логирование-backend).
