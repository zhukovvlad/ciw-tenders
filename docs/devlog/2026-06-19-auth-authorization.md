# 2026-06-19 — Аутентификация и авторизация + переезд на Alembic

## Что сделано

Добавлены email+пароль аутентификация (JWT) и ролевая авторизация (`user`/`admin`)
поверх существующих эндпоинтов; механизм миграций переведён с ручного `psql -f` на Alembic.

Спек: [docs/superpowers/specs/2026-06-19-auth-authorization-design.md](../superpowers/specs/2026-06-19-auth-authorization-design.md).
План: [docs/superpowers/plans/2026-06-19-auth-authorization.md](../superpowers/plans/2026-06-19-auth-authorization.md).

### Модель доступа

| Эндпоинт | Аноним | user | admin |
|---|:---:|:---:|:---:|
| `GET /health`, `POST /api/auth/login` | ✅ | ✅ | ✅ |
| `GET /api/auth/me` | ❌ | ✅ | ✅ |
| `POST /api/estimates/match` | ❌ | ✅ | ✅ |
| `GET /api/articles*` | ❌ | ✅ | ✅ |
| `POST/PUT/DELETE /api/articles*`, `POST /api/auth/users` | ❌ | ❌ | ✅ |

401 = не аутентифицирован (`WWW-Authenticate: Bearer`), 403 = роли не хватает.

### Бэкенд (по слоям Clean Architecture)

- **domain/** — `Role`, `User`, `TokenPayload` ([entities.py](../../backend/app/domain/entities.py));
  ошибки `AuthError`/`DuplicateError`/`TokenError` ([errors.py](../../backend/app/domain/errors.py));
  порты `UserRepository`/`PasswordHasher`/`TokenService` ([ports.py](../../backend/app/domain/ports.py)).
- **services/** — `AuthService` ([auth_service.py](../../backend/app/services/auth_service.py)):
  `login` (нормализация email, проверка пароля → активность → выдача JWT) и `create_user`.
- **infrastructure/auth/** — `Argon2PasswordHasher` (pwdlib), `JwtTokenService` (PyJWT, HS256).
- **infrastructure/db/** — `UserModel` + `SqlAlchemyUserRepository`.
- **api/** — DTO (`LoginRequest`/`TokenResponse`/`UserCreateRequest`/`UserOut`), DI-гварды
  `get_current_user`/`require_admin` в [deps.py](../../backend/app/api/deps.py), роуты
  [auth.py](../../backend/app/api/routes/auth.py); обработчики `AuthError→401`/`DuplicateError→409`
  в [main.py](../../backend/app/main.py). Гварды навешены на `estimates`/`articles`.
- **scripts/create_admin.py** — разовый идемпотентный bootstrap первого админа
  (`just create-admin`): email есть → повысить роль (пароль не ротируется), нет → создать.

### Миграции — Alembic

- `backend/alembic/` (`env.py` берёт URL из `get_settings()`, `target_metadata = Base.metadata`),
  начальная ревизия `0001` написана вручную (pgvector/HNSW/триггеры) — создаёт `template_articles`
  и `users`. Ручной `backend/migrations/001_init.sql` ретайрен.
- `justfile`: `just migrate` / `migrate-down` / `makemigration name="..."`.

## Верификация (выполнена)

- `uv run pytest` → **37 passed** (фейки портов + `dependency_overrides`, без реальной БД/AI).
- `uv run ruff check .` → All checks passed.
- Alembic проверен **офлайн**: `alembic upgrade head --sql` рендерит ожидаемый DDL без подключения к БД.

## Решения и нюансы

- **JWT:** `sub = str(user.id)` (PyJWT ≥ 2.10 требует строку), при `decode` каст в `int`.
  Роль в токен НЕ кладётся — решения по ролям всегда из БД-загруженного `User` (мгновенный эффект
  смены роли / `is_active`, нет stale-role).
- **`HTTPBearer(auto_error=False)`** + ручной 401 (дефолт `auto_error=True` отдаёт 403 на
  отсутствие заголовка) — закрыто тестом «нет токена → 401, а не 403».
- **Пароли — argon2** (а не bcrypt: тот молча режет на 72 байтах, что критично для кириллицы);
  кап длины пароля ≤1024 байт в DTO (анти-DoS).
- **Анти-enumeration:** единое сообщение для «нет email» и «неверный пароль» + `verify` против
  dummy-хэша (кэш `@lru_cache` по hasher, argon2 раз на процесс) для выравнивания тайминга.
- **`decode` всегда бросает `TokenError`** (включая `KeyError`/`ValueError` на битый `sub`) — на
  границе auth не утекает 500 вместо 401.
- **ORM ↔ ревизия `0001` синхронны** для `users` (именованные CHECK `users_role_check`,
  `users_email_is_lower`; `server_default`). `CHECK (email = lower(email))` — defense-in-depth
  к нормализации в коде.
- Процесс: брейншторм → спек → план (2 раунда ревью) → subagent-driven реализация (10 задач,
  ревью после каждой + финальное ревью всей ветки, модель под сложность задачи).

## Осталось / TODO

- **Применить к БД (вручную, не делалось — общая Neon):** добавить реальный `JWT_SECRET` в
  `backend/.env` (без него приложение не стартует — by design), `just migrate` (на пустой БД или
  ветке Neon; если в dev-БД уже есть `template_articles` от старого SQL — `alembic stamp` или свежая БД),
  затем `just create-admin` (нужны `ADMIN_EMAIL`/`ADMIN_PASSWORD`).
- **Отложенная работа по матчингу:** `TemplateArticleModel` (ORM) ещё на `section_name` и расходится
  с иерархией (`parent_id`) ревизии `0001` — реконсилировать вместе с переработкой матчинга.
- **Вне объёма (сознательно):** refresh-токены, logout/блэклист, rate-limit на `/login`,
  сброс пароля, фронтенд (страница логина/хранение токена/гварды роутов).
- **Полировка (бэклог из финального ревью):** тесты на инвалид-токен→401 для `/me` и
  `WWW-Authenticate` в анонимном тесте `/auth/users`; `FakeUserRepository.add` без проверки дублей.
