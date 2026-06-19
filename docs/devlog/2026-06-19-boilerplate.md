# 2026-06-19 — Бойлерплейт проекта

## Что сделано

Создана базовая структура веб-приложения по ТЗ: бэкенд (Clean Architecture),
фронтенд (Vite+React+shadcn), task runner и CI.

### Бэкенд (`/backend`) — Clean Architecture

Направление зависимостей: `api → services → domain ← infrastructure`.

- **domain/** — чистое ядро без внешних зависимостей:
  - `entities.py` — `TemplateArticle`, `EstimateRow`, `ArticleCandidate`, `MatchResult`, `MatchStatus`.
  - `ports.py` — абстракции (DIP): `ArticleRepository`, `Embedder`, `LLMMatcher`.
- **services/** — слой приложения (use cases):
  - `excel_parser.py` — фильтрация строк сметы по `Вид раздела == 'СМР'` (Pandas/openpyxl).
  - `matching_service.py` — RAG-ядро: эмбеддинг → топ-3 → порог 0.90 → арбитраж LLM.
  - `article_service.py` — CRUD справочника с векторизацией при создании.
- **infrastructure/** — адаптеры портов:
  - `db/` — SQLAlchemy 2.0, ORM-модель с `Vector(768)`, репозиторий с поиском по `cosine_distance`.
  - `ai/` — `GeminiEmbedder` (text-embedding-004), `AnthropicLLMMatcher` (claude-3-5-sonnet).
- **api/** — FastAPI: `schemas.py` (DTO), `deps.py` (composition root / DI), роуты `articles`, `estimates`, `main.py` с CORS.
- **migrations/001_init.sql** — `CREATE EXTENSION vector` + таблица `template_articles` + IVFFlat-индекс.
- **tests/** — pytest: фейки портов, тесты парсера, matching-логики и API (httpx/TestClient).
- Зависимости — через `uv` (`pyproject.toml`), переменные окружения — `.env` (см. `.env.example`).

### Фронтенд (`/frontend`)

- Развёрнут официальным CLI: `npx shadcn@latest init -t vite -n frontend -y --no-monorepo --base radix --preset nova`.
- Добавляются компоненты shadcn: button, table, badge, card, input.
- Прикладные файлы: `lib/api.ts` (клиент REST), страницы «Справочник» и «Загрузка сметы».

### Инфраструктура

- `justfile` — команды install/dev-back/dev-front/lint/test через `uv run` и `npm`.
- `.github/workflows/main.yml` — CI на PR в main: ruff+pytest (uv) и eslint+vitest (Node).

## Верификация (выполнена)

- **Бэкенд:** `uv sync` ✓, `uv run ruff check .` → All checks passed ✓, `uv run pytest` → 7 passed ✓.
- **Фронтенд:** `npm run lint` ✓, `npm run typecheck` ✓, `npm run test` → 1 passed ✓.
- `just --list` — все рецепты валидны ✓.

## Решения и нюансы

- **Без Docker**, всё локально; бэкенд строго в `.venv` через `uv` (поставлен инсталлятором Astral).
- БД облачная (Neon/Supabase), драйвер `psycopg` v3 → схема `postgresql+psycopg://`.
- Для порога «похожести» 0.90 используется косинусная мера (`<=>`), `score = 1 - cosine_distance`.
- `npx shadcn init` интерактивен: флаги `--no-monorepo` и `--preset nova` обязательны в headless-режиме.
- Вложенный `.git`, созданный vite-скаффолдом в `frontend/`, удалён (монорепо — один корневой repo).
- Тесты бэка не требуют реальной БД/ключей: `tests/conftest.py` задаёт фиктивные env до импорта,
  логика покрыта фейками портов и `dependency_overrides`.

## Расхождения со стеком ТЗ (из-за официального CLI shadcn)

CLI `shadcn init -t vite` поставил более свежие версии, чем в ТЗ:
- React **19** (в ТЗ — 18), Tailwind **v4** (в ТЗ — v3, без `tailwind.config.js`/postcss),
  Vite **8**, TypeScript **6**, ESLint **10**, style `radix-nova`.
- Vitest настроен вручную (CLI его не ставит); вынесен отдельный `vitest.config.ts`,
  т.к. Vite 8 (rolldown) конфликтует по типам с vite внутри vitest.
- Бэкенд-`.venv` собран на системном CPython **3.14** (колёса всех пакетов нашлись).

## Осталось / TODO

- Заполнить `backend/.env` реальными `DATABASE_URL` и ключами, применить `migrations/001_init.sql`.
- Реальная проверка векторного поиска требует развёрнутой БД с `pgvector` и ключей API.
- При необходимости — пагинация справочника, экспорт результатов сопоставления в Excel.
