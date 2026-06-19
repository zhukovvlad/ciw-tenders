# Дизайн: Аутентификация и авторизация (CIW)

**Дата:** 2026-06-19
**Статус:** дизайн утверждён, ожидает реализации
**Связанные файлы:** `backend/` (Clean Architecture), `backend/migrations/001_init.sql`

## Цель

Добавить в приложение аутентификацию и ролевую авторизацию:

- **Любой залогиненный пользователь** может загружать смету и получать обогащённый
  результат (эндпоинт сопоставления со справочником).
- **Только администратор** может править эталонный справочник СМР (`template_articles`).
- Чтение справочника доступно любому залогиненному пользователю.

## Что важно зафиксировать (контекст)

Сметы **нигде не хранятся**. Поток stateless: загрузил Excel → распарсили →
обогатили данными из справочника → вернули результат. «Дополнять свои сметы» = *пользоваться*
эндпоинтом обогащения, а не хранить данные. Поэтому **никакой подсистемы хранения смет
с владельцем не вводится** — задача сводится к двум ролям поверх существующих эндпоинтов.

(Отдельно, **вне этого спека**: сейчас `/estimates/match` возвращает JSON, а не Excel-файл —
это не относится к авторизации.)

## Принятые решения

| Вопрос | Решение |
|---|---|
| Механизм аутентификации | Свой email+пароль, JWT (access-токен) |
| Регистрация | Только админ заводит учётки; самостоятельной регистрации нет |
| Чтение справочника не-админом | Разрешено (чтение всем, запись — только админ) |
| Способ enforcement | App-level: ролевые зависимости FastAPI (не RLS, не сторонняя библиотека) |
| Sync vs async | Sync везде (согласовано с существующим стеком `create_engine`/`Session`) |
| Механизм миграций | Alembic (заменяет ручные `psql -f` скрипты) |

### Почему app-level, а не RLS / библиотека

- **RLS отвергнут:** защищает строки *по владельцу*, а владения нет (сметы не хранятся);
  подключение одно (`DATABASE_URL`, одна роль БД) — RLS пришлось бы кормить session-переменными.
  Сложность без выгоды.
- **`fastapi-users` отвергнут:** даёт регистрацию/сброс пароля/верификацию, которые нам не нужны
  (регистрация только админом), и навязывает свою модель пользователя поверх наших портов.
  Overkill для двух ролей.
- **App-level выбран:** единственный вариант, честно ложащийся в Clean Architecture проекта
  (порты в `domain`, реализации в `infrastructure`, сценарии в `services`).

## Матрица доступа

| Эндпоинт | Аноним | user | admin |
|---|:---:|:---:|:---:|
| `GET /health` | ✅ | ✅ | ✅ |
| `POST /auth/login` | ✅ | ✅ | ✅ |
| `GET /auth/me` | ❌ | ✅ | ✅ |
| `POST /estimates/match` | ❌ | ✅ | ✅ |
| `GET /articles*` (чтение) | ❌ | ✅ | ✅ |
| `POST/PUT/DELETE /articles*` | ❌ | ❌ | ✅ |
| `POST /auth/users` (завести юзера) | ❌ | ❌ | ✅ |

Семантика ошибок: **401** = «не знаю, кто ты» (нет/невалиден/просрочен токен, заголовок
`WWW-Authenticate: Bearer`); **403** = «знаю, но роли не хватает».

## Модель данных

Таблица `users` едет **внутрь `backend/migrations/001_init.sql`** (схема переезжает в Alembic —
см. ниже; отдельного `002` не будет, проект до запуска). Переиспользуется функция-триггер
`set_updated_at()`, уже определённая для `template_articles`.

```sql
CREATE TABLE users
(
    id            SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,           -- хранится в нижнем регистре (нормализация в коде)
    password_hash TEXT NOT NULL,                  -- argon2 (см. ниже), не сам пароль
    role          TEXT NOT NULL DEFAULT 'user'
                  CHECK (role IN ('user', 'admin')),
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,  -- мягкое отключение без удаления
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_email_is_lower CHECK (email = lower(email))  -- defense-in-depth к нормализации в коде
);
-- + триггер trg_users_updated_at на функции set_updated_at()
```

Обоснования:

- **`role` — TEXT + CHECK**, не отдельная таблица ролей и не Postgres ENUM. Ролей две, YAGNI;
  CHECK проще эволюционировать, чем ENUM.
- **`is_active`** — админ отключает юзера без удаления. Проверяется на **каждом** запросе
  (см. поток ниже), поэтому отключение действует мгновенно даже при живом токене — дешёвый
  аналог отзыва токена.
- **`email` в нижнем регистре** — почта регистронезависима; нормализуем в сервисе перед
  вставкой/поиском, чтобы `UNIQUE` не пропускал `Ivan@` и `ivan@`. Без CITEXT-расширения.
  Подстраховка на уровне БД — `CHECK (email = lower(email))`: `UNIQUE` ловит дубли регистра
  только пока *каждый* путь записи нормализует, а CHECK гарантирует инвариант независимо от кода.
- **`password_hash`** никогда не уходит в API-ответы (DTO `UserOut` его не содержит).

## Механизм миграций: Alembic

Заменяет ручные `psql -f *.sql`. Даёт `upgrade()/downgrade()`, версионирование, автогенерацию.

**Раскладка:**
```
backend/
  alembic.ini                  # конфиг; DATABASE_URL НЕ хардкодим здесь
  alembic/
    env.py                     # URL из app.core.config.get_settings(); target_metadata = Base.metadata
    script.py.mako
    versions/
      0001_initial_schema.py   # вся схема: template_articles + users, одной ревизией
```

- Старый `backend/migrations/001_init.sql` **ретайрится** — его содержимое переезжает в
  `upgrade()` ревизии `0001` (один источник правды).
- **Одна начальная ревизия** (до запуска «initial schema» = всё, что должно быть в чистой БД):
  создаёт и `template_articles`, и `users`. Дробить на ревизии — со следующего изменения схемы.
- **`env.py`:** URL берётся из `get_settings().database_url` (один источник, секрет в `.env`);
  `target_metadata = Base.metadata` из `app.infrastructure.db.session` — для будущего `--autogenerate`.
- **Грабля автогенерации (на будущее):** `--autogenerate` некорректно интроспектит HNSW-индекс
  и тип `Vector`, поэтому при следующих `makemigration` начнёт генерить ложные diff'ы
  (drop/create индекса). Лечится фильтром `include_object`/`include_name` в `env.py`. Точный
  фильтр не фиксируем здесь — уточним при первой реальной автогенерации; для `0001` неактуально
  (ревизия пишется руками).
- **Начальная ревизия пишется руками** (autogenerate не справится с):
  `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`; колонка `embedding` типа
  `pgvector.sqlalchemy.Vector(768)`; HNSW-индекс (`op.execute` с `USING hnsw (embedding vector_cosine_ops)`);
  plpgsql-функция `set_updated_at()` + триггеры. `downgrade()` симметрично всё дропает
  (триггеры → функция → таблицы → расширение).
- **Sync-режим** Alembic (миграция — разовый последовательный батч-джоб, конкурентности нет;
  согласовано с sync-стеком приложения).

**Сопутствующие правки:**
- `pyproject.toml`: `uv add alembic` (драйвер уже есть). Проверить sync-формат `DATABASE_URL`
  (`postgresql+psycopg://…`).
- `justfile`: `just migrate` (`alembic upgrade head`), `just migrate-down` (`downgrade -1`),
  `just makemigration name=…` (`revision --autogenerate -m`).
- `README` и `docs/instructions/`: команда запуска меняется с `psql -f …` на `alembic upgrade head`.
- **CLAUDE.md**: раздел «БД» («Схема SQL — `migrations/001_init.sql`, держать синхронно с ORM»)
  обновить — источником правды становится Alembic + ORM-модели.

## Слои бэкенда (Clean Architecture)

### `domain/` (чистый Python, без SDK)
- `entities.py`:
  - `Role(StrEnum)` = `{USER="user", ADMIN="admin"}` (стиль существующего `MatchStatus`).
  - `User` (frozen dataclass): `id, email, password_hash, role, is_active, created_at`.
  - `TokenPayload` (frozen dataclass): `user_id: int`. **Без `role`** — роль для решений
    читается из БД-загруженного `User`, не из токена (см. поток логина, иначе stale-role).
- `ports.py` — три новых порта:
  - `UserRepository`: `get_by_email`, `get_by_id`, `add`, `list_users`, `set_active`.
  - `PasswordHasher`: `hash(plain) -> str`, `verify(plain, hash) -> bool`.
  - `TokenService`: `issue(user) -> str`, `decode(token) -> TokenPayload` (бросает при невалидном/просроченном).

### `services/`
- `auth_service.py` → `AuthService` (зависит только от портов):
  - `login(email, password) -> str` — нормализует email в lower, грузит юзера, `verify` хэша,
    проверяет `is_active`, отдаёт JWT. При любой осечке — доменное `AuthError` с **единым**
    сообщением (не различать «нет email» vs «неверный пароль», чтобы не раскрывать существование email).
    Против **тайминг-перечисления**: если юзер не найден, всё равно прогнать `verify` против
    **dummy-хэша, сгенерированного тем же `PasswordHasher`** (захэшировать throwaway-пароль один
    раз на старте) — параметры argon2 тогда гарантированно совпадают с боевыми. Хардкод-строка с
    чужими cost/memory дала бы другое время проверки и вернула бы тайминг-сигнал, просто тише.
  - `create_user(email, password, role=Role.USER) -> User` — нормализует, проверяет дубль,
    хэширует, сохраняет.

### `infrastructure/` (здесь живут SDK)
- `db/models.py`: `UserModel`.
- `db/user_repository.py`: `SqlAlchemyUserRepository`.
- `auth/password_hasher.py`: реализация `PasswordHasher`. **По умолчанию — argon2 через `pwdlib`**.
  Причина: `bcrypt` молча усекает пароль на **72 байтах**, а у нас кириллица (UTF-8 = 2 байта/символ),
  то есть фактический лимит ~36 символов и два разных длинных пароля с общим префиксом стали бы
  эквивалентны. argon2 этой ловушки не имеет. Либа скрыта за портом — решение обратимо; если
  всё же `bcrypt`, обязательна валидация длины пароля в байтах (≤72) в `UserCreateRequest`/`LoginRequest`.
  **Независимо от алгоритма** — общий кап длины пароля (≤1024 байт) в этих же схемах: argon2 не
  усекает, но хэширование гигантского пароля — дешёвый DoS (CPU/память на каждый логин).
- `auth/jwt_token_service.py`: `JwtTokenService` на `pyjwt`, HS256, секрет и TTL из `Settings`.

### `api/`
- `schemas.py`: `LoginRequest{email, password}`, `TokenResponse{access_token, token_type="bearer"}`,
  `UserCreateRequest{email, password, role}`, `UserOut{id, email, role, is_active, created_at}`
  (**без** `password_hash`).
- `routes/auth.py`: `POST /auth/login` (открытый), `POST /auth/users` (админ), `GET /auth/me` (текущий юзер).
- `deps.py`: `get_auth_service`, `get_current_user`, `require_admin`.

## Поток логина (последовательность)

```
POST /auth/login {email, password}
  → AuthService.login: get_by_email → verify(пароль, hash) → is_active? → TokenService.issue
                       (не найден → verify против dummy-хэша → AuthError)
  ← 200 {access_token, token_type: "bearer"}          (401 + AuthError при осечке)

Клиент шлёт на защищённые запросы: Authorization: Bearer <token>
  → get_current_user: парс Bearer → TokenService.decode → get_by_id → is_active? → User
  → (для записи в /articles) require_admin: User.role == admin? иначе 403
```

JWT несёт `sub=str(user.id)`, `exp`, `iat`. **`sub` — строка** (PyJWT ≥ 2.10.0, ноя-2024,
валидирует `sub` как строку и иначе бросает `InvalidSubjectError`; зависимость ставится без пина,
приедет свежая) — при `decode` приводим обратно к `int`. **Роль в токен не кладём:** решения по
ролям всегда берутся из БД-загруженного `User` (через `get_by_id`), иначе разжалованный админ
оставался бы админом до `exp` (stale-role). Проверка `is_active` и роли идёт **запросом в БД на
каждом обращении** — поэтому отключение и смена роли действуют мгновенно.

## Enforcement на эндпоинтах

- `get_current_user` — достаёт `Authorization: Bearer` через **`HTTPBearer(auto_error=False)`**,
  декодирует токен, грузит юзера, проверяет `is_active`. Нет/протух/невалиден → **401**
  (`WWW-Authenticate: Bearer`). Важно: `auto_error=True` (дефолт) при *отсутствии* заголовка
  отдаёт **403** без `WWW-Authenticate` — известная особенность FastAPI; поэтому ставим
  `auto_error=False` и кидаем 401 вручную, иначе тест «401 без токена» вернёт 403.
- `require_admin(user = Depends(get_current_user))` — если `role != admin` → **403**.
- Роутеры чтения (`/articles` GET, `/estimates`) получают `get_current_user` на уровне роутера
  (`APIRouter(dependencies=[...])`); админские пишущие операции — точечно `require_admin`.
- Доменное `AuthError` маппится в **401** одним обработчиком исключений в `main.py`.
- `GET /health` и `POST /auth/login` остаются открытыми.

## Bootstrap первого админа

Курица и яйцо: юзеров заводит только админ, первого админа заводить некому. Решение — разовый
seed-скрипт:

- `backend/app/scripts/create_admin.py`, запуск `uv run python -m app.scripts.create_admin`
  (рецепт `just create-admin`). Читает `ADMIN_EMAIL` / `ADMIN_PASSWORD` из `.env`, идемпотентно:
  email есть → только повышает роль до `admin`, **пароль НЕ ротирует** (повторный запуск
  безопасен и не перезатирает существующий пароль); email нет → создаёт с хэшем пароля.
- Заметка по секрету: `ADMIN_PASSWORD` остаётся в `.env` открытым текстом после bootstrap
  (приемлемо для разработки). Как опция — интерактивный ввод пароля вместо чтения из env.

## Конфиг и секреты

`core/config.py`:
- `jwt_secret: str` — **без дефолта**, падаем на старте, если не задан (как `DATABASE_URL`).
- `jwt_algorithm: str = "HS256"`.
- `jwt_expire_minutes: int = 720` (12 ч — рабочий день с запасом).

`.env.example` (значения только в `backend/.env`, в `.gitignore`):
- `JWT_SECRET=` — длинная случайная строка (приложить команду генерации).
- `JWT_EXPIRE_MINUTES=720`, `ADMIN_EMAIL=`, `ADMIN_PASSWORD=`.

**Зависимости:** `uv add pyjwt "pwdlib[argon2]" alembic`.

## Тесты

- **Фейки** в `tests/fakes.py`: `FakeUserRepository`, `FakePasswordHasher` (тривиальный, без крипто),
  `FakeTokenService`. Юнит-тесты не ходят в реальную БД/крипту — через `app.dependency_overrides`.
- **Покрытие:** `AuthService.login` (успех / неверный пароль / **неизвестный email — тот же
  `AuthError`** / неактивный юзер), `create_user` (дубль email), round-trip токена
  (`issue`→`decode`, в т.ч. `sub` приходит строкой и кастится в `int`), матрица доступа на роутах
  (**401 без токена** — проверяет, что `auto_error=False` отрабатывает, а не отдаёт 403;
  403 у `user` на запись в `/articles`; 200 у `admin`).
- `conftest.py` добавляет `JWT_SECRET` в фиктивные env (до импорта приложения).

## Вне объёма (явно не делаем сейчас)

- Refresh-токены, logout / блэклист токенов (пока access-only + `is_active`).
- **Rate-limit / лок-аут на `/auth/login`** — осознанно отложено (закрытая регистрация, две роли).
  `is_active` от перебора паролей не защищает; вернёмся, если появится потребность.
- Сброс и смена пароля.
- Самостоятельная регистрация пользователей.
- Фронтенд: страница логина, хранение токена, гварды роутов. Бэкенд даёт под это готовый API —
  отдельная задача.
- Перевод `/estimates/match` на отдачу Excel-файла (не связано с авторизацией).
- Перевод обогащения смет в фоновые задачи (актуально, только если брошенные дорогие LLM-запросы
  станут реальной проблемой).
