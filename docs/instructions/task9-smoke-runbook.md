# Task 9 — End-to-end смоук импорта справочника

> **Статус: PASSED против TEST_DATABASE_URL (2026-06-21).** Интеграционный слой
> (миграция `0002`, SQL-адаптеры `import_repository`/`embedding_queue_repository`,
> сортировка по коду, CAS воркера, pgvector `VECTOR(768)`, реальный OpenRouter
> `gemini-embedding-2`@768) верифицирован на чистой тест-ветке Neon. Результаты:
> import created=362/pending=362 → воркер записал 362 вектора (4 прохода) →
> total 362, pending 0, roots 21 → повторный импорт unchanged=362, pending=0 (идемпотентно).
>
> Этот же runbook используй для **осознанного засева боевой БД** (DATABASE_URL): тот же
> прогон без переопределения env. Скрипт `smoke_import.py` оставлен в репозитории как
> ops-инструмент засева (отклонение от плана, который предлагал его удалить — обосновано
> ongoing-потребностью засеять прод отдельным шагом деплоя).
>
> ПРЕДУСЛОВИЕ для прода (важно): убедись, что боевая БД НЕ имеет применённой
> до-переписанной ревизии `0001` (на TEST это была чистая greenfield-ветка — ОК).

Проверяет то, что не покрыто юнит-тестами: миграцию `0002`, SQL-адаптеры, сортировку по
коду, CAS воркера и реальный вызов OpenRouter (768-мерный вектор → `VECTOR(768)`).

## Предусловие (критично)

Убедись, что `TEST_DATABASE_URL` указывает на **отдельную БД/ветку Neon**, а не на алиас
прода. Если отдельной тест-БД нет — заведи ветку в Neon под это. Без подтверждённой
изоляции прогон засеет боевую БД.

Стоимость реального эмбеддинга: ~362 строки × ~$0.0000065 ≈ **$0.0024** (четверть цента).
Эмбеддер НЕ мокать — весь смысл смоука в том, чтобы живой ответ OpenRouter доехал в схему.

## Прогон (Windows PowerShell, из корня проекта)

```powershell
# 1. Нацелиться на ТЕСТОВУЮ БД на время сессии (env-var перекрывает .env).
#    Подставь строку подключения из TEST_DATABASE_URL (backend/.env).
$env:DATABASE_URL = "<значение TEST_DATABASE_URL>"
$env:PYTHONIOENCODING = "utf-8"

# 2. Применить миграции к тест-БД и проверить, что head = 0002.
just migrate
cd backend; uv run alembic current   # ожидается: 0002 (head)

# 3. Проверить autogenerate-чистоту ORM (шум на Vector/HNSW — известный долг, не падать).
uv run alembic check

# 4. Импорт реального файла (ожидается created=362, pending_embeddings=362).
uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx
cd ..

# 5. Прогнать воркер по проходам, пока не выведет "Записано векторов: 0" (≈4 прохода по 100).
just embed-worker --once --batch-size 100
just embed-worker --once --batch-size 100
just embed-worker --once --batch-size 100
just embed-worker --once --batch-size 100

# 6. Проверить состояние БД: ожидается total 362, pending 0, roots 21.
cd backend; uv run python -c "from app.infrastructure.db.session import SessionLocal; from sqlalchemy import text; s=SessionLocal(); print('total', s.execute(text('select count(*) from template_articles')).scalar()); print('pending', s.execute(text('select count(*) from template_articles where embedding is null')).scalar()); print('roots', s.execute(text('select count(*) from template_articles where parent_id is null')).scalar()); s.close()"
cd ..

# 7. Идемпотентность повторного импорта: created=0, updated=0, unchanged=362, pending=0.
cd backend; uv run python -m app.scripts.smoke_import ../temp/Шаблон.xlsx
cd ..
```

## После успешного прогона

```powershell
git rm backend/app/scripts/smoke_import.py
git commit -m "chore: end-to-end смоук импорта пройден (362 строки, эмбеддинги наполнены)"
```

Затем закрой сессию PowerShell, чтобы `$env:DATABASE_URL` сбросился (вернётся боевой из `.env`).

## Если что-то разошлось (Шаги 4–7)

НЕ удаляй `smoke_import.py`. Заведи дефект и почини соответствующий SQL-адаптер до
зелёного: число строк ≠ 362 → парсер/`apply_plan`; `roots` ≠ 21 → резолв `parent_id`;
`pending` не падает до 0 → CAS воркера или формат вектора OpenRouter.
