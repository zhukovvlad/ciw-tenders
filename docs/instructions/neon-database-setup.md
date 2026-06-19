# Настройка базы данных на Neon (PostgreSQL + pgvector)

Инструкция по созданию облачной БД для проекта «Автоматизатор строительных смет»:
основная база + отдельная тестовая. Без Docker, всё в облаке Neon.

---

## 1. Создать проект и основную БД

1. Зарегистрируйтесь / войдите на [console.neon.tech](https://console.neon.tech).
2. **Create project**:
   - **Name**: `ciw` (любое).
   - **Postgres version**: 16 или новее.
   - **Region**: ближайший (например, `Europe (Frankfurt)` — `eu-central-1`).
3. После создания Neon сам заведёт:
   - ветку `main` (production),
   - базу `neondb`,
   - роль (пользователя) с паролем.

> В Neon одна **ветка** = независимая копия данных. Это пригодится для тестовой БД (см. §5).

---

## 2. Включить расширение pgvector

Расширение `vector` включается автоматически первой Alembic-ревизией (`0001`) при `just migrate`.
Ручная команда не нужна — шаг оставлен для справки:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Neon поддерживает `pgvector` из коробки — отдельная установка не нужна.

---

## 3. Получить строку подключения (DATABASE_URL)

1. В консоли Neon: **Dashboard → Connect** (или **Connection Details**).
2. Скопируйте строку вида:
   ```
   postgresql://<user>:<password>@<endpoint>.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```
3. **Важно:** проект использует драйвер **psycopg v3**, поэтому замените схему
   `postgresql://` → `postgresql+psycopg://`:
   ```
   postgresql+psycopg://<user>:<password>@<endpoint>.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```
4. Вставьте результат в `backend/.env`:
   ```dotenv
   DATABASE_URL=postgresql+psycopg://<user>:<password>@<endpoint>.eu-central-1.aws.neon.tech/neondb?sslmode=require
   ```

> Используйте **direct** (не pooled) подключение для миграций. Pooled-строку (`-pooler`
> в хосте) можно использовать для приложения, если нужно много соединений.

---

## 4. Применить миграции (создать таблицы)

Миграции управляются через **Alembic**. Убедитесь, что `DATABASE_URL` прописан в `backend/.env`,
затем выполните из корня проекта:

```bash
just migrate
# или напрямую: cd backend; uv run alembic upgrade head
```

Ожидаемый вывод: `Running upgrade  -> 0001, initial schema: template_articles + users`

> Используйте **direct** (не pooled) строку подключения для миграций.

Проверка:
```sql
SELECT count(*) FROM template_articles;   -- должно вернуть 0
SELECT count(*) FROM users;               -- должно вернуть 0
\d template_articles                       -- столбец embedding типа vector(768)
```

Для отката последней миграции: `just migrate-down`

---

## 5. Тестовая БД

Тестовая база нужна для будущих **интеграционных** тестов (текущие unit-тесты её не
требуют — они используют фейки и не ходят в реальную БД). Два варианта:

### Вариант А (рекомендуется) — отдельная ветка Neon

Ветка — мгновенная изолированная копия, её не жалко пересоздавать.

1. Консоль Neon → **Branches → Create branch**.
2. **Name**: `test`, родитель — `main`.
3. На вкладке **Connect** выберите ветку `test` и скопируйте её строку подключения.
4. Выполните на ветке `test`:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   и примените миграции (см. §4), указав строку ветки `test`.
5. Добавьте в `backend/.env` отдельную переменную:
   ```dotenv
   TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@<endpoint-ветки-test>.../neondb?sslmode=require
   ```

### Вариант Б — отдельная база в той же ветке

1. В **SQL Editor** (ветка `main`) выполните:
   ```sql
   CREATE DATABASE ciw_test;
   ```
2. Переключитесь на базу `ciw_test`, включите расширение и примените миграцию:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   -- затем содержимое 001_init.sql
   ```
3. В `TEST_DATABASE_URL` укажите ту же строку, но с именем БД `ciw_test`:
   ```dotenv
   TEST_DATABASE_URL=postgresql+psycopg://<user>:<password>@<endpoint>.../ciw_test?sslmode=require
   ```

> При добавлении интеграционных тестов прочитайте `TEST_DATABASE_URL` в
> `backend/tests/conftest.py` и создавайте сессию на ней. Ветка `test` чище:
> её можно сбрасывать (reset from parent) перед прогоном.

---

## 6. Чек-лист

- [ ] Проект Neon создан, регион выбран.
- [ ] `CREATE EXTENSION vector` выполнен на основной ветке.
- [ ] `DATABASE_URL` в `backend/.env` со схемой `postgresql+psycopg://` и `?sslmode=require`.
- [ ] `just migrate` выполнен (`alembic upgrade head`), таблицы `template_articles` и `users` созданы.
- [ ] (Опционально) Ветка/база `test` создана, `TEST_DATABASE_URL` прописан.
- [ ] `just dev-back` поднимается, `GET /health` → `{"status":"ok"}`.

---

## Частые проблемы

| Симптом | Причина / решение |
|---|---|
| `password authentication failed` | Скопирована не вся строка или старый пароль. Сгенерируйте новый в **Connect → Reset password**. |
| `SSL connection required` | Нет `?sslmode=require` в конце строки. |
| `could not translate host name` | Endpoint «уснул» (free tier) — первый запрос будит, повторите. |
| `type "vector" does not exist` | Не выполнен `CREATE EXTENSION vector` на нужной ветке/базе. |
| `ModuleNotFoundError: psycopg` | Схема осталась `postgresql://` без `+psycopg`, либо не сделан `uv sync`. |
