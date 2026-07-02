# CLAUDE.md

Указания для агентов, работающих в этом репозитории. Держи файл кратким и актуальным.

## Обзор

«Автоматизатор строительных смет» (CIW). Загружает Excel-смету, отбирает строки
видов работ («Вид раздела» = `СМР`) и через RAG (векторный поиск pgvector + LLM)
сопоставляет их с эталонным справочником статей СМР.

Поток: загрузил → распарсили → обогатили из справочника → ревью → выгрузка .xlsx.
Персистентны: справочник (`template_articles`), сметы (`estimates`/`estimate_rows` +
оригинал в MinIO) и золотой фонд решений (`decision_fund` — exact-match кэш
подтверждённых оператором сопоставлений, применяется перед RAG).

- `backend/` — FastAPI, Clean Architecture, Python 3.11+, управляется `uv`.
- `frontend/` — Vite + React + TypeScript + Tailwind v4 + shadcn/ui.
- `justfile` — единый task runner (корень проекта).

## Команды (из корня)

| Команда | Действие |
|---|---|
| `just install` | `uv sync` (бэк) + `npm install` (фронт) |
| `just dev-back` | FastAPI на `:8260` (hot-reload) |
| `just dev-front` | Vite на `:5173` (проксирует `/api` → `:8260`) |
| `just migrate` | `alembic upgrade head` (откат — `just migrate-down`) |
| `just create-admin` | создать/повысить админа из `ADMIN_EMAIL`/`ADMIN_PASSWORD` (`backend/.env`) |
| `just embed-worker [--once]` | посчитать эмбеддинги справочника (строки с `embedding IS NULL`) |
| `just lint` | ruff + eslint + prettier `--check` |
| `just fmt` | ruff `--fix`/`format` + prettier `--write` |
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
  OpenRouter (эмбеддинги, `gemini-embedding-2` через `httpx`), Anthropic (LLM-арбитр), JWT/argon2 (auth).
  Здесь живут все внешние SDK/HTTP.
- [backend/app/api/](backend/app/api/) — FastAPI: роуты, DTO-схемы, DI в [deps.py](backend/app/api/deps.py)
  (composition root). DTO ≠ доменные сущности — не смешивать.

**Правила:**
- Новая зависимость от внешнего сервиса → сначала порт в `domain/ports.py`, потом реализация в `infrastructure/`.
- Бизнес-логику не писать в роутах и репозиториях — её место в `services/`.
- Сопоставление: сначала фонд решений (`_apply_fund`, exact-match по нормализованной крошке,
  до эмбеддинга; хит ⇒ статус `matched_fund`, см.
  [decision_fund_service.py](backend/app/services/decision_fund_service.py)); промахи → RAG:
  эмбеддинг → топ-3 (pgvector) → `score > 0.90` ⇒ «Уверенное совпадение», иначе LLM-арбитр
  (Claude) выбирает из топ-3 ⇒ «Требует проверки». См.
  [matching_service.py](backend/app/services/matching_service.py).
- **Auth-слой:** порты `UserRepository` / `PasswordHasher` / `TokenService` в `domain/ports.py`;
  роли `user` / `admin`; enforcement через `get_current_user` / `require_admin` в `api/deps.py`.
- **Эмбеддинги справочника — асинхронно:** при импорте/добавлении статья получает `embedding_input`
  и `embedding=NULL`; вектор дозаполняет воркер `just embed-worker` (CAS по `embedding_input`).
  Поиск исключает строки с `embedding IS NULL`. Воркер пока ручной — см. [docs/TECH_DEBT.md](docs/TECH_DEBT.md).

## Фронтенд

- Реальный API-слой — `frontend/src/lib/api/`: `client.ts` (единый `ApiError`, Bearer-токен из
  `sessionStorage` по ключу `ciw.auth.token`, колбэк `onUnauthorized`, multipart-загрузка) + модули
  `auth` / `articles`. `client.ts` — единственный, кто читает токен из стораджа.
- Аутентификация — `lib/auth/AuthContext` (JWT в `sessionStorage`, **не** localStorage); хук `useAuth`
  вынесен в отдельный `lib/auth/useAuth.ts` (требование `react-refresh`). Гейтинг по роли на клиенте —
  косметика; реальный enforcement на бэке (`require_admin`).
- Справочник СМР (`pages/ArticlesPage` + `components/articles/*`: таблица, ручное добавление, загрузка
  шаблона, полная очистка) ходит в **реальный** бэкенд. Поток смет (`pages/estimate/`) пока на **моках**
  (`lib/mock/`) — не трогать его и `Candidate`/`MOCK_*` при работе со справочником.

## БД

- Облачный PostgreSQL (Neon) + pgvector. Подключение только через `DATABASE_URL` в `backend/.env`.
- Источник правды — Alembic-ревизии ([backend/alembic/versions/](backend/alembic/versions/)) +
  ORM-модели ([models.py](backend/app/infrastructure/db/models.py)). Начальная ревизия `0001`
  написана вручную (pgvector/HNSW/триггеры не поддерживаются автогенерацией корректно).
  При изменении схемы: `just makemigration name="..."` (автогенерация) или ручная ревизия,
  затем `just migrate`. ORM-модели держать синхронными с ревизиями.
- Применение миграций: `just migrate` (`alembic upgrade head`). Откат: `just migrate-down`.
- Поиск — косинусная близость: `score = 1 - cosine_distance` (порог 0.90 — это similarity).

## Логирование (backend)

Своя централизованная система на stdlib `logging` (без structlog/loguru) — **не изобретать заново
и не использовать `print` для диагностики**. В любом модуле: `logger = logging.getLogger(__name__)`.

- **Ядро** — [app/core/logging_config.py](backend/app/core/logging_config.py): `setup_logging()`
  (консоль на stdout + ротируемые `backend/logs/{app.log,errors.log}`; `root=DEBUG`, фильтрация
  по уровням хендлеров). Идемпотентно; вызывается в точках входа: `create_app()`, сигналы Celery,
  CLI-скрипты. Конфиг из env (`LOG_LEVEL`/`LOG_TO_FILE`/`LOG_DIR`), **не** из `Settings` (логи не
  должны зависеть от валидации `DATABASE_URL`/`JWT_SECRET`). `backend/logs/` — в `.gitignore`.
- **Сквозная корреляция `request_id → task_id`** через `ContextVar` + `RequestIdFilter` (стоит на
  каждой записи, дефолт `-`). Web: `RequestIdMiddleware` ([api/middleware.py](backend/app/api/middleware.py))
  генерит/принимает `X-Request-ID` и кладёт в ответ. Celery: сигналы `task_prerun`/`task_postrun`
  ([infrastructure/tasks/celery_app.py](backend/app/infrastructure/tasks/celery_app.py)) восстанавливают
  request_id из заголовка задачи (`enqueue_match` его пробрасывает). Не плодить свой контекст —
  использовать `bind_request_id`/`bind_task_id`/`reset_correlation`.
- **`extra={...}` — только неймспейснутые ключи** (`provider`, `latency_ms`, `attempts`, `outcome`,
  `estimate_id`…), НИКОГДА зарезервированные (`name`, `message`, `args`) → `KeyError: Attempt to overwrite`.
- **AI-вызовы инструментируются через `instrumented_call`**
  ([infrastructure/ai/_instrumented.py](backend/app/infrastructure/ai/_instrumented.py)): один
  summary на вызов (provider/model/latency_ms/attempts/outcome, ре-рейз на сбое). Новый AI-адаптер
  оборачивает `retry_transient` через него, а не зовёт голый retry.
- **`print` vs `logger`:** диагностика/статус → `logger`; фактический вывод программы (отчёт скрипта
  в stdout) → остаётся `print`.
- Прод под Celery prefork (`--concurrency>1`): `RotatingFileHandler` не multiprocess-safe →
  `LOG_TO_FILE=0` (ротация снаружи). Дев — solo-pool, дефолт `LOG_TO_FILE=1`. См. [docs/TECH_DEBT.md](docs/TECH_DEBT.md).

## Тесты

- Бэк: pytest + httpx `TestClient`. Юнит-тесты **не ходят в реальную БД/AI** — используют
  фейки портов ([tests/fakes.py](backend/tests/fakes.py)) и `app.dependency_overrides`.
- [tests/conftest.py](backend/tests/conftest.py) задаёт фиктивные env до импорта приложения
  (иначе обязательный `DATABASE_URL` уронит импорт).
- Фронт: vitest + React Testing Library. Конфиг — `vitest.config.ts` (отдельно от `vite.config.ts`).

## Конвенции

- **Бэкенд:** ruff (line-length 100, `target py311`), type hints обязательны, `from __future__ import annotations`.
  Запускать `uv run ruff check .` перед коммитом.
- **Фронтенд:** eslint строгий + Prettier (`printWidth 80`, `endOfLine lf`) — `just lint` гоняет
  `prettier --check`, `just fmt` форматирует. shadcn-компоненты в `src/components/ui/` — вендорные, не править.
  Импорты через alias `@/`. Иконки — `lucide-react`. TypeScript strict; `npm run typecheck` = `tsc -b`
  (корневой `tsconfig.json` — solution-файл со ссылками на `tsconfig.app.json`/`tsconfig.node.json`;
  `tsc --noEmit` без `-b` ничего не проверит). `erasableSyntaxOnly` включён — без parameter properties/enum.
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
- Переводы строк: `.gitattributes` форсит **LF** (перекрывает `core.autocrlf=true` на Windows) —
  согласовано с `.prettierrc` (`endOfLine: lf`). Держать файлы в LF.

## Документация

- Журнал работ — [docs/devlog/](docs/devlog/) (отчёт по каждой задаче).
- Инструкции (настройка Neon и т.п.) — [docs/instructions/](docs/instructions/).
- Технический долг — [docs/TECH_DEBT.md](docs/TECH_DEBT.md) (отложенные задачи, полировка, план на будущее).
