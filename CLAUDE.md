# CLAUDE.md

Указания для агентов, работающих в этом репозитории. Держи файл кратким и актуальным.

## Обзор

«Автоматизатор строительных смет» (CIW). Загружает Excel-смету, отбирает строки
видов работ («Вид раздела» = `СМР`) и через RAG (векторный поиск pgvector + LLM)
сопоставляет их с эталонным справочником статей СМР.

- `backend/` — FastAPI, Clean Architecture, Python 3.11+, управляется `uv`.
- `frontend/` — Vite + React + TypeScript + Tailwind v4 + shadcn/ui.
- `justfile` — единый task runner (корень проекта).

## Команды (из корня)

| Команда | Действие |
|---|---|
| `just install` | `uv sync` (бэк) + `npm install` (фронт) |
| `just dev-back` | FastAPI на `:8260` (hot-reload) |
| `just dev-front` | Vite на `:5173` (проксирует `/api` → `:8260`) |
| `just lint` | ruff + eslint |
| `just test` | pytest + vitest |
| `just build` | production-сборка фронта |

Точечно: `cd backend && uv run pytest tests/test_api.py`, `cd frontend && npm run typecheck`.

## Архитектура бэкенда (Clean Architecture)

Направление зависимостей строгое: **`api → services → domain ← infrastructure`**.
Доменный слой не зависит ни от чего; внешние слои зависят от абстракций.

- [backend/app/domain/](backend/app/domain/) — сущности ([entities.py](backend/app/domain/entities.py)) и
  порты-абстракции ([ports.py](backend/app/domain/ports.py): `ArticleRepository`, `Embedder`, `LLMMatcher`).
  **Без** импортов FastAPI/SQLAlchemy/SDK.
- [backend/app/services/](backend/app/services/) — сценарии (use cases): парсинг Excel, сопоставление, CRUD.
  Зависят только от портов.
- [backend/app/infrastructure/](backend/app/infrastructure/) — адаптеры портов: БД (SQLAlchemy+pgvector),
  Gemini, Anthropic. Здесь живут все внешние SDK.
- [backend/app/api/](backend/app/api/) — FastAPI: роуты, DTO-схемы, DI в [deps.py](backend/app/api/deps.py)
  (composition root). DTO ≠ доменные сущности — не смешивать.

**Правила:**
- Новая зависимость от внешнего сервиса → сначала порт в `domain/ports.py`, потом реализация в `infrastructure/`.
- Бизнес-логику не писать в роутах и репозиториях — её место в `services/`.
- Сопоставление: эмбеддинг → топ-3 (pgvector) → `score > 0.90` ⇒ «Уверенное совпадение»,
  иначе LLM-арбитр (Claude) выбирает из топ-3 ⇒ «Требует проверки». См.
  [matching_service.py](backend/app/services/matching_service.py).

## БД

- Облачный PostgreSQL (Neon) + pgvector. Подключение только через `DATABASE_URL` в `backend/.env`.
- Схема SQL — [backend/migrations/001_init.sql](backend/migrations/001_init.sql), ORM-модель —
  [models.py](backend/app/infrastructure/db/models.py). **Держать синхронными** при изменении структуры.
- Поиск — косинусная близость: `score = 1 - cosine_distance` (порог 0.90 — это similarity).

## Тесты

- Бэк: pytest + httpx `TestClient`. Юнит-тесты **не ходят в реальную БД/AI** — используют
  фейки портов ([tests/fakes.py](backend/tests/fakes.py)) и `app.dependency_overrides`.
- [tests/conftest.py](backend/tests/conftest.py) задаёт фиктивные env до импорта приложения
  (иначе обязательный `DATABASE_URL` уронит импорт).
- Фронт: vitest + React Testing Library. Конфиг — `vitest.config.ts` (отдельно от `vite.config.ts`).

## Конвенции

- **Бэкенд:** ruff (line-length 100, `target py311`), type hints обязательны, `from __future__ import annotations`.
  Запускать `uv run ruff check .` перед коммитом.
- **Фронтенд:** eslint строгий. shadcn-компоненты в `src/components/ui/` — вендорные, не править.
  Импорты через alias `@/`. Иконки — `lucide-react`.
- Зависимости бэка — только через `uv add` (не редактировать `pyproject.toml` руками без нужды).

## Критические ограничения

- **Без Docker.** Всё запускается локально.
- Бэкенд работает **строго в `.venv`** через `uv run` (не вызывать системный `python`/`pip`).
- Секреты — только в `backend/.env` (в `.gitignore`). Не коммитить ключи и строки подключения.

## Подводные камни (Windows / окружение)

- `justfile` использует **Windows PowerShell 5.1** — оператор `&&` не работает, в рецептах `;`.
- `uv` установлен в `~/.local/bin` — если `uv: command not found`, перезапустить терминал (PATH).
- Кириллица в stdout Python падает с `UnicodeEncodeError` (cp1252) — ставить `PYTHONIOENCODING=utf-8`.
- Бэкенд на порту **8260** (не 8000 — машина общая, 8000 занят другим пользователем).
- `google.generativeai` выдаёт `FutureWarning` (deprecated) — пакет из ТЗ, оставлен намеренно.

## Документация

- Журнал работ — [docs/devlog/](docs/devlog/) (отчёт по каждой задаче).
- Инструкции (настройка Neon и т.п.) — [docs/instructions/](docs/instructions/).
