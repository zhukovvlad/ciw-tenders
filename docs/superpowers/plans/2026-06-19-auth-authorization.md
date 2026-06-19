# Аутентификация и авторизация — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить email+пароль аутентификацию (JWT) и ролевую авторизацию (`user`/`admin`) поверх существующих эндпоинтов, плюс переезд миграций на Alembic.

**Architecture:** Clean Architecture проекта без исключений — порты в `domain/`, реализации в `infrastructure/`, сценарии в `services/`, ролевые зависимости в `api/`. App-level enforcement (не RLS, не сторонняя библиотека). Sync-стек везде.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (sync), PostgreSQL+pgvector (Neon), PyJWT, pwdlib[argon2], Alembic, pytest + httpx TestClient.

**Спек:** [docs/superpowers/specs/2026-06-19-auth-authorization-design.md](../specs/2026-06-19-auth-authorization-design.md)

## Global Constraints

- Python `>=3.11`; `from __future__ import annotations` во всех модулях; type hints обязательны.
- ruff: line-length 100, target py311; `uv run ruff check .` зелёный перед каждым коммитом.
- Зависимости — только через `uv add` (не править `pyproject.toml` руками).
- Sync везде: `create_engine`/`Session`, sync-драйвер `postgresql+psycopg://`. Никакого async.
- Секреты только в `backend/.env` (в `.gitignore`); в репозиторий — только `.env.example`.
- Роуты монтируются под `/api` (см. [main.py](../../../backend/app/main.py)) → реальные пути `/api/auth/login`, `/api/articles`, `/api/estimates/match`.
- `justfile` — Windows PowerShell 5.1: внутри рецепта команды разделяются `;`, не `&&`.
- **JWT:** `sub = str(user.id)` (PyJWT ≥2.10 валидирует `sub` как строку), при `decode` каст в `int`. Роль в токен НЕ кладём — решения по ролям только из БД-загруженного `User`.
- **Аутентификация:** `HTTPBearer(auto_error=False)` + ручной 401 (дефолт `auto_error=True` отдаёт 403). 401 = не аутентифицирован (+`WWW-Authenticate: Bearer`), 403 = роли не хватает.
- **Пароли:** argon2 через `pwdlib`; кап длины пароля ≤1024 байт в DTO (анти-DoS), независимо от алгоритма.
- БД: `template_articles` — `embedding VECTOR(768)` (значение из `embedding_dim`, но в миграции фиксируется как 768-снимок).

## Отклонения от спека (осознанные — отметить при ревью)

1. **Порт `UserRepository` — без `list_users`/`set_active`.** В спеке они перечислены, но ни один эндпоинт их не вызывает (управление юзерами = фронтенд, вне объёма). YAGNI: не плодим мёртвые абстрактные методы. Когда появится админ-UI — добавим вместе с роутами. Промоут роли в `create_admin` сделан напрямую через ORM-модель (скрипт инфраструктурного уровня), без порта.
2. **Новая зависимость `pydantic[email]`** (`EmailStr`) для валидации email в DTO — в спеке явно не упомянута, но это очевидно правильный тип для поля email; стоимость — один пакет.

## Предусловие (вне объёма этого плана)

ORM-модель `TemplateArticleModel` (`section_name`, без `parent_id`/timestamps) расходится с актуальной схемой `template_articles` в [001_init.sql](../../../backend/migrations/001_init.sql) (иерархия: `parent_id`, HNSW, триггер). Это **отложенная работа по матчингу/иерархии**, не относящаяся к авторизации. Этот план **портирует SQL как есть** в Alembic-ревизию `0001` и **не трогает** `TemplateArticleModel`/`TemplateArticle`. Новая `UserModel` будет консистентна со схемой.

## Структура файлов

**Создаются:**
- `backend/app/domain/errors.py` — доменные исключения `AuthError`, `DuplicateError`, `TokenError`.
- `backend/app/infrastructure/auth/__init__.py`
- `backend/app/infrastructure/auth/password_hasher.py` — `Argon2PasswordHasher`.
- `backend/app/infrastructure/auth/jwt_token_service.py` — `JwtTokenService`.
- `backend/app/infrastructure/db/user_repository.py` — `SqlAlchemyUserRepository`.
- `backend/app/services/auth_service.py` — `AuthService`.
- `backend/app/api/routes/auth.py` — роуты `/auth/*`.
- `backend/app/scripts/__init__.py`, `backend/app/scripts/create_admin.py` — bootstrap первого админа.
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_initial_schema.py`.
- Тесты: `backend/tests/test_password_hasher.py`, `test_auth_token.py`, `test_auth_service.py`, `test_auth_routes.py`.

**Модифицируются:**
- `backend/pyproject.toml` (через `uv add`).
- `backend/app/core/config.py` — JWT/admin настройки.
- `backend/app/domain/entities.py` — `Role`, `User`, `TokenPayload`.
- `backend/app/domain/ports.py` — `UserRepository`, `PasswordHasher`, `TokenService`.
- `backend/app/infrastructure/db/models.py` — `UserModel`.
- `backend/app/api/schemas.py` — `LoginRequest`, `TokenResponse`, `UserCreateRequest`, `UserOut`.
- `backend/app/api/deps.py` — провайдеры auth + `get_current_user`/`require_admin`.
- `backend/app/api/routes/estimates.py`, `articles.py` — навешивание зависимостей.
- `backend/app/main.py` — подключение роутера auth + обработчики исключений.
- `backend/tests/conftest.py` — `JWT_SECRET` в env.
- `backend/tests/fakes.py` — `FakeUserRepository`, `FakePasswordHasher`, `FakeTokenService`.
- `backend/tests/test_api.py` — починка под обязательную авторизацию.
- `justfile` — рецепты `migrate`/`migrate-down`/`makemigration`/`create-admin`.
- `backend/.env.example`, `README.md`/`docs/instructions/`, `CLAUDE.md`.

**Ретайрится:** `backend/migrations/001_init.sql` (содержимое переезжает в ревизию `0001`).

---

### Task 1: Зависимости, конфиг, тестовое окружение

**Files:**
- Modify: `backend/pyproject.toml` (через `uv add`)
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_config.py` (create)

**Interfaces:**
- Produces: `Settings.jwt_secret: str`, `Settings.jwt_algorithm: str = "HS256"`, `Settings.jwt_expire_minutes: int = 720`, `Settings.admin_email: str = ""`, `Settings.admin_password: str = ""`.

- [ ] **Step 1: Установить зависимости**

Run:
```bash
cd backend; uv add pyjwt "pwdlib[argon2]" alembic "pydantic[email]"
```
Expected: пакеты добавлены в `pyproject.toml` `[project.dependencies]`, `uv.lock` обновлён.

- [ ] **Step 2: Добавить JWT/admin поля в `Settings`**

В [config.py](../../../backend/app/core/config.py) добавить в класс `Settings` после `frontend_origin`:
```python
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720  # 12 ч

    admin_email: str = ""
    admin_password: str = ""
```

- [ ] **Step 3: Задать `JWT_SECRET` в conftest (до импорта приложения)**

В [conftest.py](../../../backend/tests/conftest.py) добавить после существующих `setdefault`:
```python
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
```

- [ ] **Step 4: Дополнить `.env.example`**

В [.env.example](../../../backend/.env.example) добавить блок:
```bash
# Аутентификация (JWT). JWT_SECRET — длинная случайная строка, сгенерировать:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET=change-me-long-random-string
JWT_EXPIRE_MINUTES=720

# Bootstrap первого администратора (используется `just create-admin`)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=change-me
```

- [ ] **Step 5: Написать падающий тест конфига**

`backend/tests/test_config.py`:
```python
from __future__ import annotations

from app.core.config import Settings


def test_jwt_defaults() -> None:
    settings = Settings(jwt_secret="x")  # type: ignore[call-arg]
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expire_minutes == 720
    assert settings.admin_email == ""
```

- [ ] **Step 6: Запустить тест**

Run: `cd backend; uv run pytest tests/test_config.py -v`
Expected: PASS (поля заданы в Step 2).

- [ ] **Step 7: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/pyproject.toml backend/uv.lock backend/app/core/config.py backend/tests/conftest.py backend/tests/test_config.py backend/.env.example
git commit -m "feat(auth): зависимости (pyjwt/pwdlib/alembic) и JWT-конфиг"
```

---

### Task 2: Домен — сущности, ошибки, порты

**Files:**
- Modify: `backend/app/domain/entities.py`
- Create: `backend/app/domain/errors.py`
- Modify: `backend/app/domain/ports.py`
- Test: `backend/tests/test_domain_auth.py` (create)

**Interfaces:**
- Produces:
  - `Role(StrEnum)` = `USER="user"`, `ADMIN="admin"`.
  - `User(email: str, password_hash: str, role: Role = Role.USER, is_active: bool = True, id: int | None = None, created_at: datetime | None = None)` — frozen dataclass.
  - `TokenPayload(user_id: int)` — frozen dataclass.
  - `AuthError(Exception)`, `DuplicateError(Exception)`, `TokenError(Exception)`.
  - Порты `UserRepository` (`get_by_email`, `get_by_id`, `add`), `PasswordHasher` (`hash`, `verify`), `TokenService` (`issue`, `decode`).

- [ ] **Step 1: Добавить сущности в `entities.py`**

В [entities.py](../../../backend/app/domain/entities.py) добавить импорт `datetime` и сущности:
```python
from datetime import datetime  # к существующим импортам


class Role(StrEnum):
    """Роль пользователя."""

    USER = "user"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class User:
    """Учётная запись пользователя."""

    email: str
    password_hash: str
    role: Role = Role.USER
    is_active: bool = True
    id: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Полезная нагрузка JWT (без роли — роль читается из БД)."""

    user_id: int
```

- [ ] **Step 2: Создать `errors.py`**

`backend/app/domain/errors.py`:
```python
"""Доменные исключения авторизации (без зависимостей от фреймворков)."""

from __future__ import annotations


class AuthError(Exception):
    """Аутентификация не удалась (неверные данные / отключённая учётка)."""


class DuplicateError(Exception):
    """Нарушение уникальности (например, email уже существует)."""


class TokenError(Exception):
    """Токен невалиден, повреждён или просрочен."""
```

- [ ] **Step 3: Добавить порты в `ports.py`**

В [ports.py](../../../backend/app/domain/ports.py) расширить импорт сущностей и добавить порты:
```python
from app.domain.entities import ArticleCandidate, TemplateArticle, TokenPayload, User


class UserRepository(ABC):
    """Хранилище пользователей."""

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def add(self, user: User) -> User: ...


class PasswordHasher(ABC):
    """Хеширование и проверка паролей."""

    @abstractmethod
    def hash(self, plain: str) -> str: ...

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool: ...


class TokenService(ABC):
    """Выпуск и разбор JWT."""

    @abstractmethod
    def issue(self, user: User) -> str: ...

    @abstractmethod
    def decode(self, token: str) -> TokenPayload: ...
```

- [ ] **Step 4: Написать падающий тест**

`backend/tests/test_domain_auth.py`:
```python
from __future__ import annotations

from app.domain.entities import Role, TokenPayload, User


def test_user_defaults() -> None:
    user = User(email="a@b.c", password_hash="h")
    assert user.role is Role.USER
    assert user.is_active is True
    assert user.id is None


def test_role_values() -> None:
    assert Role.ADMIN.value == "admin"
    assert Role.USER.value == "user"


def test_token_payload() -> None:
    assert TokenPayload(user_id=7).user_id == 7
```

- [ ] **Step 5: Запустить тест**

Run: `cd backend; uv run pytest tests/test_domain_auth.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/domain/ backend/tests/test_domain_auth.py
git commit -m "feat(auth): доменные сущности (Role/User/TokenPayload), ошибки, порты"
```

---

### Task 3: Argon2 PasswordHasher

**Files:**
- Create: `backend/app/infrastructure/auth/__init__.py`
- Create: `backend/app/infrastructure/auth/password_hasher.py`
- Test: `backend/tests/test_password_hasher.py`

**Interfaces:**
- Consumes: `PasswordHasher` (Task 2).
- Produces: `Argon2PasswordHasher()` реализует `hash(plain) -> str`, `verify(plain, hashed) -> bool`.

- [ ] **Step 1: Написать падающий тест**

`backend/tests/test_password_hasher.py`:
```python
from __future__ import annotations

from app.infrastructure.auth.password_hasher import Argon2PasswordHasher


def test_hash_is_not_plaintext_and_verifies() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("Пароль-123")
    assert hashed != "Пароль-123"
    assert hasher.verify("Пароль-123", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct")
    assert hasher.verify("wrong", hashed) is False
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd backend; uv run pytest tests/test_password_hasher.py -v`
Expected: FAIL (`ModuleNotFoundError: app.infrastructure.auth.password_hasher`).

- [ ] **Step 3: Реализовать**

`backend/app/infrastructure/auth/__init__.py`: пустой файл.

`backend/app/infrastructure/auth/password_hasher.py`:
```python
"""Реализация PasswordHasher на argon2 (pwdlib). За портом — выбор алгоритма обратим."""

from __future__ import annotations

from pwdlib import PasswordHash

from app.domain.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def hash(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        return self._hasher.verify(plain, hashed)
```

- [ ] **Step 4: Запустить — PASS**

Run: `cd backend; uv run pytest tests/test_password_hasher.py -v`
Expected: PASS.

- [ ] **Step 5: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/infrastructure/auth/ backend/tests/test_password_hasher.py
git commit -m "feat(auth): Argon2PasswordHasher"
```

---

### Task 4: JwtTokenService

**Files:**
- Create: `backend/app/infrastructure/auth/jwt_token_service.py`
- Test: `backend/tests/test_auth_token.py`

**Interfaces:**
- Consumes: `TokenService`, `User`, `TokenPayload`, `TokenError` (Task 2).
- Produces: `JwtTokenService(secret: str, algorithm: str, expire_minutes: int)` → `issue(user) -> str`, `decode(token) -> TokenPayload` (raises `TokenError`).

- [ ] **Step 1: Написать падающий тест**

`backend/tests/test_auth_token.py`:
```python
from __future__ import annotations

import jwt
import pytest

from app.domain.entities import User
from app.domain.errors import TokenError
from app.infrastructure.auth.jwt_token_service import JwtTokenService


def _service(expire_minutes: int = 720) -> JwtTokenService:
    return JwtTokenService(secret="s", algorithm="HS256", expire_minutes=expire_minutes)


def test_roundtrip_returns_user_id() -> None:
    service = _service()
    token = service.issue(User(id=42, email="a@b.c", password_hash="h"))
    assert service.decode(token).user_id == 42


def test_sub_is_string_in_raw_token() -> None:
    service = _service()
    token = service.issue(User(id=42, email="a@b.c", password_hash="h"))
    raw = jwt.decode(token, "s", algorithms=["HS256"])
    assert raw["sub"] == "42"  # строка, не int (PyJWT >= 2.10)


def test_expired_token_raises_token_error() -> None:
    service = _service(expire_minutes=-1)  # уже просрочен
    token = service.issue(User(id=1, email="a@b.c", password_hash="h"))
    with pytest.raises(TokenError):
        service.decode(token)


def test_tampered_token_raises_token_error() -> None:
    service = _service()
    with pytest.raises(TokenError):
        service.decode("not.a.valid.token")
```

- [ ] **Step 2: Запустить — FAIL**

Run: `cd backend; uv run pytest tests/test_auth_token.py -v`
Expected: FAIL (модуль не найден).

- [ ] **Step 3: Реализовать**

`backend/app/infrastructure/auth/jwt_token_service.py`:
```python
"""Реализация TokenService на PyJWT (HS256)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.domain.entities import TokenPayload, User
from app.domain.errors import TokenError
from app.domain.ports import TokenService


class JwtTokenService(TokenService):
    def __init__(self, secret: str, algorithm: str, expire_minutes: int) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def issue(self, user: User) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),  # PyJWT >= 2.10 требует строку
            "iat": now,
            "exp": now + timedelta(minutes=self._expire_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise TokenError(str(exc)) from exc
        return TokenPayload(user_id=int(data["sub"]))
```

- [ ] **Step 4: Запустить — PASS**

Run: `cd backend; uv run pytest tests/test_auth_token.py -v`
Expected: PASS (все 4).

- [ ] **Step 5: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/infrastructure/auth/jwt_token_service.py backend/tests/test_auth_token.py
git commit -m "feat(auth): JwtTokenService (sub как строка, TokenError на ошибки)"
```

---

### Task 5: AuthService + фейки портов

**Files:**
- Create: `backend/app/services/auth_service.py`
- Modify: `backend/tests/fakes.py`
- Test: `backend/tests/test_auth_service.py`

**Interfaces:**
- Consumes: `UserRepository`, `PasswordHasher`, `TokenService`, `User`, `Role`, `AuthError`, `DuplicateError` (Tasks 2–4).
- Produces:
  - `AuthService(users, hasher, tokens)` → `login(email, password) -> str`, `create_user(email, password, role=Role.USER) -> User`.
  - Фейки: `FakeUserRepository(users=None)`, `FakePasswordHasher()`, `FakeTokenService()`.

- [ ] **Step 1: Добавить фейки в `fakes.py`**

В [fakes.py](../../../backend/tests/fakes.py) добавить импорты и классы:
```python
from datetime import datetime, timezone

from app.domain.entities import Role, TokenPayload, User
from app.domain.errors import TokenError
from app.domain.ports import PasswordHasher, TokenService, UserRepository


class FakePasswordHasher(PasswordHasher):
    def hash(self, plain: str) -> str:
        return f"hashed::{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed::{plain}"


class FakeTokenService(TokenService):
    def issue(self, user: User) -> str:
        return f"token::{user.id}"

    def decode(self, token: str) -> TokenPayload:
        if not token.startswith("token::"):
            raise TokenError("bad token")
        return TokenPayload(user_id=int(token.removeprefix("token::")))


class FakeUserRepository(UserRepository):
    def __init__(self, users: list[User] | None = None) -> None:
        self._store: list[User] = list(users or [])

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._store if u.email == email), None)

    def get_by_id(self, user_id: int) -> User | None:
        return next((u for u in self._store if u.id == user_id), None)

    def add(self, user: User) -> User:
        stored = User(
            id=len(self._store) + 1,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self._store.append(stored)
        return stored
```

- [ ] **Step 2: Написать падающий тест**

`backend/tests/test_auth_service.py`:
```python
from __future__ import annotations

import pytest

from app.domain.entities import Role, User
from app.domain.errors import AuthError, DuplicateError
from app.services.auth_service import AuthService
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository


def _service(users: list[User] | None = None) -> AuthService:
    return AuthService(
        users=FakeUserRepository(users),
        hasher=FakePasswordHasher(),
        tokens=FakeTokenService(),
    )


def _user(**kw: object) -> User:
    base = {"id": 1, "email": "ivan@mr.kz", "password_hash": "hashed::secret"}
    base.update(kw)
    return User(**base)  # type: ignore[arg-type]


def test_login_success_returns_token() -> None:
    service = _service([_user()])
    assert service.login("ivan@mr.kz", "secret") == "token::1"


def test_login_normalizes_email_case() -> None:
    service = _service([_user()])
    assert service.login("  IVAN@MR.KZ ", "secret") == "token::1"


def test_login_wrong_password_raises_auth_error() -> None:
    service = _service([_user()])
    with pytest.raises(AuthError):
        service.login("ivan@mr.kz", "nope")


def test_login_unknown_email_raises_same_auth_error() -> None:
    service = _service([])
    with pytest.raises(AuthError):
        service.login("ghost@mr.kz", "whatever")


def test_login_inactive_user_raises_auth_error() -> None:
    service = _service([_user(is_active=False)])
    with pytest.raises(AuthError):
        service.login("ivan@mr.kz", "secret")


def test_create_user_persists_lowercased_email() -> None:
    service = _service([])
    user = service.create_user("NEW@mr.kz", "password123", Role.ADMIN)
    assert user.email == "new@mr.kz"
    assert user.role is Role.ADMIN
    assert user.id is not None


def test_create_user_duplicate_raises() -> None:
    service = _service([_user()])
    with pytest.raises(DuplicateError):
        service.create_user("ivan@mr.kz", "password123")
```

- [ ] **Step 3: Запустить — FAIL**

Run: `cd backend; uv run pytest tests/test_auth_service.py -v`
Expected: FAIL (модуль `auth_service` не найден).

- [ ] **Step 4: Реализовать `AuthService`**

`backend/app/services/auth_service.py`:
```python
"""Сценарии аутентификации: логин и создание пользователя. Зависит только от портов."""

from __future__ import annotations

from app.domain.entities import Role, User
from app.domain.errors import AuthError, DuplicateError
from app.domain.ports import PasswordHasher, TokenService, UserRepository

_TIMING_PASSWORD = "timing-equalizer-not-a-real-password"


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        # dummy-хэш теми же параметрами, что и боевые, — для выравнивания тайминга.
        self._dummy_hash = hasher.hash(_TIMING_PASSWORD)

    def login(self, email: str, password: str) -> str:
        email = email.strip().lower()
        user = self._users.get_by_email(email)
        if user is None:
            # Прогоняем verify против dummy-хэша, чтобы время ответа не выдавало
            # отсутствие email (защита от тайминг-перечисления).
            self._hasher.verify(password, self._dummy_hash)
            raise AuthError("Неверный email или пароль")
        if not self._hasher.verify(password, user.password_hash):
            raise AuthError("Неверный email или пароль")
        if not user.is_active:
            raise AuthError("Учётная запись отключена")
        return self._tokens.issue(user)

    def create_user(self, email: str, password: str, role: Role = Role.USER) -> User:
        email = email.strip().lower()
        if self._users.get_by_email(email) is not None:
            raise DuplicateError("Пользователь с таким email уже существует")
        user = User(
            email=email,
            password_hash=self._hasher.hash(password),
            role=role,
        )
        return self._users.add(user)
```

- [ ] **Step 5: Запустить — PASS**

Run: `cd backend; uv run pytest tests/test_auth_service.py -v`
Expected: PASS (все 7).

- [ ] **Step 6: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/services/auth_service.py backend/tests/fakes.py backend/tests/test_auth_service.py
git commit -m "feat(auth): AuthService (логин с выравниванием тайминга, create_user) + фейки портов"
```

---

### Task 6: UserModel + SqlAlchemyUserRepository

**Files:**
- Modify: `backend/app/infrastructure/db/models.py`
- Create: `backend/app/infrastructure/db/user_repository.py`
- Test: `backend/tests/test_user_repository_mapping.py`

**Interfaces:**
- Consumes: `User`, `Role`, `UserRepository` (Task 2), `Base` ([session.py](../../../backend/app/infrastructure/db/session.py)).
- Produces:
  - `UserModel` (таблица `users`).
  - `SqlAlchemyUserRepository(session)` реализует `UserRepository`; статические `_to_entity(model) -> User` для маппинга.

> Примечание: репозиторий ходит в БД, поэтому юнит-тестом покрываем только чистый маппинг `_to_entity` (как и в проекте нет DB-тестов репозиториев). Поведение в БД проверяется интеграционно в Task 9/10.

- [ ] **Step 1: Добавить `UserModel`**

В [models.py](../../../backend/app/infrastructure/db/models.py) добавить импорты и модель:
```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Написать падающий тест маппинга**

`backend/tests/test_user_repository_mapping.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities import Role
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.user_repository import SqlAlchemyUserRepository


def test_to_entity_maps_fields() -> None:
    model = UserModel(
        id=5,
        email="ivan@mr.kz",
        password_hash="h",
        role="admin",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    entity = SqlAlchemyUserRepository._to_entity(model)
    assert entity.id == 5
    assert entity.email == "ivan@mr.kz"
    assert entity.role is Role.ADMIN
    assert entity.is_active is True
```

- [ ] **Step 3: Запустить — FAIL**

Run: `cd backend; uv run pytest tests/test_user_repository_mapping.py -v`
Expected: FAIL (модуль `user_repository` не найден).

- [ ] **Step 4: Реализовать репозиторий**

`backend/app/infrastructure/db/user_repository.py`:
```python
"""Адаптер UserRepository на SQLAlchemy. Маппинг ORM-модель ↔ доменная сущность."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import Role, User
from app.domain.ports import UserRepository
from app.infrastructure.db.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            role=Role(model.role),
            is_active=model.is_active,
            created_at=model.created_at,
        )

    def get_by_email(self, email: str) -> User | None:
        model = self._session.scalar(select(UserModel).where(UserModel.email == email))
        return self._to_entity(model) if model else None

    def get_by_id(self, user_id: int) -> User | None:
        model = self._session.get(UserModel, user_id)
        return self._to_entity(model) if model else None

    def add(self, user: User) -> User:
        model = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)
```

- [ ] **Step 5: Запустить — PASS**

Run: `cd backend; uv run pytest tests/test_user_repository_mapping.py -v`
Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/infrastructure/db/models.py backend/app/infrastructure/db/user_repository.py backend/tests/test_user_repository_mapping.py
git commit -m "feat(auth): UserModel + SqlAlchemyUserRepository"
```

---

### Task 7: API — схемы, DI, роуты, обработчики ошибок

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/deps.py`
- Create: `backend/app/api/routes/auth.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `AuthService`, `UserRepository`, `PasswordHasher`, `TokenService`, `User`, `Role`, ошибки (Tasks 2–6).
- Produces:
  - DTO: `LoginRequest`, `TokenResponse`, `UserCreateRequest`, `UserOut`.
  - DI: `get_user_repository`, `get_password_hasher`, `get_token_service`, `get_auth_service`, `get_current_user() -> User`, `require_admin() -> User`.
  - Роуты: `POST /api/auth/login`, `POST /api/auth/users` (admin), `GET /api/auth/me`.

- [ ] **Step 1: Добавить DTO в `schemas.py`**

В [schemas.py](../../../backend/app/api/schemas.py) добавить импорты и схемы:
```python
from datetime import datetime

from pydantic import EmailStr

from app.domain.entities import Role, User


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=1024)
    role: Role = Role.USER


class UserOut(BaseModel):
    id: int
    email: str
    role: Role
    is_active: bool
    created_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> UserOut:
        return cls(
            id=user.id or 0,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,  # type: ignore[arg-type]
        )
```

- [ ] **Step 2: Добавить DI и гварды в `deps.py`**

В [deps.py](../../../backend/app/api/deps.py) добавить импорты и провайдеры:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.entities import Role, User
from app.domain.errors import TokenError
from app.domain.ports import PasswordHasher, TokenService, UserRepository
from app.infrastructure.auth.jwt_token_service import JwtTokenService
from app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from app.infrastructure.db.user_repository import SqlAlchemyUserRepository
from app.services.auth_service import AuthService

_bearer = HTTPBearer(auto_error=False)


def get_user_repository(session: Session = Depends(get_session)) -> UserRepository:
    return SqlAlchemyUserRepository(session)


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_token_service() -> TokenService:
    settings = get_settings()
    return JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_expire_minutes,
    )


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: TokenService = Depends(get_token_service),
) -> AuthService:
    return AuthService(users=users, hasher=hasher, tokens=tokens)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    users: UserRepository = Depends(get_user_repository),
    tokens: TokenService = Depends(get_token_service),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не аутентифицирован",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = tokens.decode(creds.credentials)
    except TokenError as exc:
        raise unauthorized from exc
    user = users.get_by_id(payload.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role is not Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user
```

- [ ] **Step 3: Создать роутер `auth.py`**

`backend/app/api/routes/auth.py`:
```python
"""Роуты аутентификации: логин, заведение пользователя (admin), текущий профиль."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user, require_admin
from app.api.schemas import LoginRequest, TokenResponse, UserCreateRequest, UserOut
from app.domain.entities import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    token = service.login(email=payload.email, password=payload.password)
    return TokenResponse(access_token=token)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_user(
    payload: UserCreateRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = service.create_user(
        email=payload.email, password=payload.password, role=payload.role
    )
    return UserOut.from_entity(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_entity(user)
```

- [ ] **Step 4: Подключить роутер и обработчики ошибок в `main.py`**

В [main.py](../../../backend/app/main.py) добавить импорты, обработчики и подключение роутера:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import articles, auth, estimates
from app.domain.errors import AuthError, DuplicateError
```
Внутри `create_app()` после `app.add_middleware(...)`:
```python
    @app.exception_handler(AuthError)
    def _on_auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(DuplicateError)
    def _on_duplicate(_: Request, exc: DuplicateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(auth.router, prefix="/api")
```

- [ ] **Step 5: Написать падающий тест роутов**

`backend/tests/test_auth_routes.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_password_hasher, get_token_service, get_user_repository
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository

_ADMIN = User(id=1, email="admin@mr.kz", password_hash="hashed::adminpw", role=Role.ADMIN)
_USER = User(id=2, email="user@mr.kz", password_hash="hashed::userpw", role=Role.USER)


def _wire_fakes() -> None:
    repo = FakeUserRepository([_ADMIN, _USER])
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_password_hasher] = FakePasswordHasher
    app.dependency_overrides[get_token_service] = FakeTokenService


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_login_returns_token() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"email": "admin@mr.kz", "password": "adminpw"})
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "token::1"


def test_login_bad_credentials_401() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"email": "admin@mr.kz", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_without_token_is_401_not_403() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401  # HTTPBearer(auto_error=False) → 401, не 403
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_token() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer token::2"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@mr.kz"


def test_create_user_as_admin_201() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post(
        "/api/auth/users",
        headers={"Authorization": "Bearer token::1"},
        json={"email": "new@mr.kz", "password": "password123", "role": "user"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@mr.kz"


def test_create_user_as_non_admin_403() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post(
        "/api/auth/users",
        headers={"Authorization": "Bearer token::2"},
        json={"email": "new@mr.kz", "password": "password123"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 6: Запустить — FAIL, затем (после Steps 1–4 уже сделаны) PASS**

Run: `cd backend; uv run pytest tests/test_auth_routes.py -v`
Expected: PASS (все 6). Если падает `EmailStr` — проверить, что в Task 1 установлен `pydantic[email]`.

- [ ] **Step 7: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/api/ backend/app/main.py backend/tests/test_auth_routes.py
git commit -m "feat(auth): DTO, DI-гварды (get_current_user/require_admin), роуты /auth/*"
```

---

### Task 8: Навесить авторизацию на существующие эндпоинты

**Files:**
- Modify: `backend/app/api/routes/estimates.py`
- Modify: `backend/app/api/routes/articles.py`
- Modify: `backend/tests/test_api.py`
- Test: `backend/tests/test_authz_matrix.py` (create)

**Interfaces:**
- Consumes: `get_current_user`, `require_admin` (Task 7).

- [ ] **Step 1: Защитить `/estimates`**

В [estimates.py](../../../backend/app/api/routes/estimates.py) изменить создание роутера на уровне-роутера зависимость:
```python
from app.api.deps import get_current_user, get_matching_service, get_parser

router = APIRouter(
    prefix="/estimates", tags=["estimates"], dependencies=[Depends(get_current_user)]
)
```
(добавить импорт `Depends` уже есть; `get_current_user` — новый.)

- [ ] **Step 2: Защитить `/articles` (чтение — любой, запись — admin)**

В [articles.py](../../../backend/app/api/routes/articles.py):
```python
from app.api.deps import get_article_service, get_current_user, require_admin

router = APIRouter(
    prefix="/articles", tags=["articles"], dependencies=[Depends(get_current_user)]
)
```
Добавить `require_admin` точечно на пишущие роуты:
```python
@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
...
@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(require_admin)])
```

- [ ] **Step 3: Починить существующий `test_api.py` (регрессия)**

`test_match_endpoint` теперь требует аутентификацию. В [test_api.py](../../../backend/tests/test_api.py) добавить override `get_current_user`:
```python
from app.api.deps import get_current_user, get_matching_service, get_parser
from app.domain.entities import Role, User


def _fake_admin() -> User:
    return User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)
```
В `test_match_endpoint` перед запросом добавить:
```python
    app.dependency_overrides[get_current_user] = _fake_admin
```
(уже есть `app.dependency_overrides.clear()` после запроса — оставить.)

- [ ] **Step 4: Написать тест матрицы доступа**

`backend/tests/test_authz_matrix.py`:
```python
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import (
    get_article_service,
    get_password_hasher,
    get_token_service,
    get_user_repository,
)
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import (
    FakeEmbedder,
    FakePasswordHasher,
    FakeRepository,
    FakeTokenService,
    FakeUserRepository,
)
from app.services.article_service import ArticleService

_ADMIN = User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)
_USER = User(id=2, email="user@mr.kz", password_hash="h", role=Role.USER)


def _wire() -> None:
    repo = FakeUserRepository([_ADMIN, _USER])
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_token_service] = FakeTokenService
    app.dependency_overrides[get_password_hasher] = FakePasswordHasher
    app.dependency_overrides[get_article_service] = lambda: ArticleService(
        repository=FakeRepository(), embedder=FakeEmbedder()
    )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_articles_read_requires_auth() -> None:
    _wire()
    client = TestClient(app)
    assert client.get("/api/articles").status_code == 401


def test_articles_read_allowed_for_user() -> None:
    _wire()
    client = TestClient(app)
    resp = client.get("/api/articles", headers={"Authorization": "Bearer token::2"})
    assert resp.status_code == 200


def test_articles_write_forbidden_for_user() -> None:
    _wire()
    client = TestClient(app)
    resp = client.post(
        "/api/articles",
        headers={"Authorization": "Bearer token::2"},
        json={"article_code": "X", "name": "n", "section_name": "s"},
    )
    assert resp.status_code == 403


def test_articles_write_allowed_for_admin() -> None:
    _wire()
    client = TestClient(app)
    resp = client.post(
        "/api/articles",
        headers={"Authorization": "Bearer token::1"},
        json={"article_code": "X", "name": "n", "section_name": "s"},
    )
    assert resp.status_code == 201
```

- [ ] **Step 5: Запустить весь набор**

Run: `cd backend; uv run pytest -v`
Expected: PASS (включая починенный `test_api.py` и новый `test_authz_matrix.py`).

- [ ] **Step 6: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/api/routes/estimates.py backend/app/api/routes/articles.py backend/tests/test_api.py backend/tests/test_authz_matrix.py
git commit -m "feat(auth): ролевые гварды на /estimates и /articles + тест матрицы доступа"
```

---

### Task 9: Alembic — механизм миграций и начальная ревизия

**Files:**
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/0001_initial_schema.py`
- Delete: `backend/migrations/001_init.sql`
- Modify: `justfile`, `README.md`, `docs/instructions/` (если есть инструкция по БД), `CLAUDE.md`

**Interfaces:**
- Consumes: `Base.metadata`, `get_settings().database_url`, `UserModel` (для регистрации в metadata).

> Верификация требует доступа к dev-БД (Neon) через `DATABASE_URL` в `backend/.env`. Шаги Step 7–8 мутируют схему dev-БД (создают `template_articles`/`users`) — это ожидаемо.

- [ ] **Step 1: `alembic.ini` (минимальный, URL берётся из env.py)**

`backend/alembic.ini`:
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: `env.py` (sync, URL из Settings, регистрация моделей)**

`backend/alembic/env.py`:
```python
"""Alembic env: sync-режим, URL из app.core.config, target_metadata из ORM Base."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.infrastructure.db.models  # noqa: F401  — регистрирует модели в Base.metadata
from app.core.config import get_settings
from app.infrastructure.db.session import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

> **Грабля автогенерации (на будущее):** `--autogenerate` некорректно интроспектит HNSW-индекс и тип `Vector` и начнёт генерить ложные diff'ы. Когда дойдём до первой реальной автогенерации — добавить `include_object`/`include_name`-фильтр в `context.configure(...)`. Для `0001` неактуально (пишется руками).

- [ ] **Step 3: `script.py.mako` (стандартный шаблон Alembic)**

`backend/alembic/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Начальная ревизия `0001_initial_schema.py`**

`backend/alembic/versions/0001_initial_schema.py` (портирует [001_init.sql](../../../backend/migrations/001_init.sql) + добавляет `users`):
```python
"""initial schema: template_articles + users

Revision ID: 0001
Revises:
Create Date: 2026-06-19
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE template_articles (
            id           SERIAL PRIMARY KEY,
            parent_id    INTEGER REFERENCES template_articles (id) ON DELETE CASCADE,
            article_code VARCHAR(64) UNIQUE NOT NULL,
            name         TEXT NOT NULL,
            embedding    VECTOR(768),
            created_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_template_articles_embedding "
        "ON template_articles USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX idx_template_articles_parent_id ON template_articles (parent_id)"
    )

    op.execute(
        """
        CREATE TABLE users (
            id            SERIAL PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            is_active     BOOLEAN NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT users_email_is_lower CHECK (email = lower(email))
        )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER trg_template_articles_updated_at BEFORE UPDATE ON template_articles "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.execute("DROP TRIGGER IF EXISTS trg_template_articles_updated_at ON template_articles")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS template_articles")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

- [ ] **Step 5: Удалить ретайренный raw-SQL**

```bash
git rm backend/migrations/001_init.sql
```
(каталог `backend/migrations/` можно удалить, если он пуст.)

- [ ] **Step 6: Обновить `justfile`**

В [justfile](../../../justfile) заменить рецепт `migrate` и добавить новые:
```just
# Применить миграции к БД (alembic upgrade head). Требует DATABASE_URL в backend/.env.
migrate:
    cd {{backend}}; uv run alembic upgrade head

# Откатить последнюю миграцию.
migrate-down:
    cd {{backend}}; uv run alembic downgrade -1

# Сгенерировать новую ревизию из ORM-моделей: just makemigration name="add x"
makemigration name:
    cd {{backend}}; uv run alembic revision --autogenerate -m "{{name}}"
```

- [ ] **Step 7: Проверить upgrade на dev-БД**

Run: `cd backend; uv run alembic upgrade head`
Expected: `Running upgrade  -> 0001, initial schema...`; в БД появляются таблицы `template_articles`, `users`, функция `set_updated_at`, оба триггера.

- [ ] **Step 8: Проверить обратимость (downgrade → upgrade)**

Run:
```bash
cd backend; uv run alembic downgrade base
cd backend; uv run alembic upgrade head
```
Expected: downgrade дропает обе таблицы/функцию/расширение без ошибок; повторный upgrade восстанавливает. Это подтверждает симметрию.

- [ ] **Step 9: Обновить документацию**

- В [README.md](../../../README.md) и инструкции по БД в `docs/instructions/`: заменить `psql "$DATABASE_URL" -f migrations/001_init.sql` на `just migrate` (или `cd backend; uv run alembic upgrade head`).
- В [CLAUDE.md](../../../CLAUDE.md) раздел «БД»: заменить «Схема SQL — `backend/migrations/001_init.sql` … держать синхронными» на формулировку, что источник правды — Alembic-ревизии (`backend/alembic/versions/`) + ORM-модели; начальная ревизия `0001` пишется руками из-за pgvector/HNSW/триггеров.
- В [CLAUDE.md](../../../CLAUDE.md) добавить в раздел архитектуры строку про auth-слой: порты `UserRepository`/`PasswordHasher`/`TokenService`, роли `user`/`admin`, enforcement через `get_current_user`/`require_admin` в `api/deps.py`.

- [ ] **Step 10: Прогнать юнит-тесты (не должны зависеть от Alembic) и закоммитить**

Run: `cd backend; uv run pytest -q; uv run ruff check .`
Expected: PASS.
```bash
git add backend/alembic.ini backend/alembic/ justfile README.md docs/ CLAUDE.md
git rm backend/migrations/001_init.sql
git commit -m "feat(db): переезд миграций на Alembic; начальная ревизия 0001 (template_articles + users)"
```

---

### Task 10: Bootstrap первого админа

**Files:**
- Create: `backend/app/scripts/__init__.py`, `backend/app/scripts/create_admin.py`
- Modify: `justfile`

**Interfaces:**
- Consumes: `get_settings()`, `Argon2PasswordHasher`, `UserModel`, `SessionLocal`, `Role`.

> Верификация требует прогнанной миграции (Task 9) и `ADMIN_EMAIL`/`ADMIN_PASSWORD` в `backend/.env`.

- [ ] **Step 1: Создать скрипт**

`backend/app/scripts/__init__.py`: пустой файл.

`backend/app/scripts/create_admin.py`:
```python
"""Разовый bootstrap первого администратора.

Идемпотентно: если email уже есть — только повышает роль до admin (пароль НЕ
ротирует); если нет — создаёт. Запуск: `uv run python -m app.scripts.create_admin`.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.domain.entities import Role
from app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import SessionLocal


def main() -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        raise SystemExit("Задайте ADMIN_EMAIL и ADMIN_PASSWORD в backend/.env")

    email = settings.admin_email.strip().lower()
    session = SessionLocal()
    try:
        existing = (
            session.query(UserModel).filter(UserModel.email == email).one_or_none()
        )
        if existing is not None:
            if existing.role != Role.ADMIN.value:
                existing.role = Role.ADMIN.value
                session.commit()
                print(f"Роль пользователя {email} повышена до admin (пароль не изменён).")
            else:
                print(f"Админ {email} уже существует — изменений нет.")
            return

        hasher = Argon2PasswordHasher()
        session.add(
            UserModel(
                email=email,
                password_hash=hasher.hash(settings.admin_password),
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
        session.commit()
        print(f"Создан администратор {email}.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Добавить рецепт в `justfile`**

```just
# Создать/повысить первого администратора из ADMIN_EMAIL/ADMIN_PASSWORD (backend/.env).
create-admin:
    cd {{backend}}; uv run python -m app.scripts.create_admin
```

- [ ] **Step 3: Проверить на dev-БД (после `just migrate`)**

Run: `just create-admin`
Expected (первый запуск): `Создан администратор <email>.`
Run повторно: `just create-admin`
Expected: `Админ <email> уже существует — изменений нет.` (идемпотентность, пароль не тронут).

- [ ] **Step 4: Smoke-проверка логина (опционально, требует запущенный backend)**

Run: `just dev-back` (в отдельном терминале), затем:
```bash
curl -s -X POST http://localhost:8260/api/auth/login -H "Content-Type: application/json" -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}'
```
Expected: JSON с `access_token` и `"token_type":"bearer"`.

- [ ] **Step 5: Lint + commit**

```bash
cd backend; uv run ruff check .
git add backend/app/scripts/ justfile
git commit -m "feat(auth): bootstrap-скрипт create_admin + рецепт just create-admin"
```

---

## Self-Review

**1. Покрытие спека:**
- Email+пароль, JWT — Tasks 4, 7. ✅
- Роли user/admin, матрица доступа — Tasks 7, 8. ✅
- Регистрация только админом (`POST /auth/users` под `require_admin`) — Task 7. ✅
- Чтение справочника всем, запись — admin — Task 8. ✅
- `users` (TEXT+CHECK role, is_active, email lower + CHECK) — Tasks 6, 9. ✅
- Alembic (env из Settings, ревизия руками, downgrade, justfile, docs/CLAUDE) — Task 9. ✅
- `sub` строкой + каст, роль не в токене — Tasks 4, 7. ✅
- `HTTPBearer(auto_error=False)` + 401-тест — Task 7. ✅
- argon2 (pwdlib), кап длины ≤1024 — Tasks 3, 7. ✅
- Тайминг: dummy-verify + тест на unknown email — Task 5. ✅
- Bootstrap (идемпотентность, пароль не ротируется) — Task 10. ✅
- Конфиг/секреты (jwt_secret без дефолта, .env.example) — Task 1. ✅
- Вне объёма (refresh, rate-limit, сброс пароля, фронтенд) — не планируется. ✅

**2. Плейсхолдеры:** нет TBD/«добавить обработку ошибок» — весь код приведён дословно.

**3. Согласованность типов:** `User`/`TokenPayload`/`Role` определены в Task 2 и используются единообразно; сигнатуры `AuthService.login/create_user`, `TokenService.issue/decode`, `PasswordHasher.hash/verify`, `UserRepository.get_by_email/get_by_id/add` совпадают между задачами; фейки (Task 5) реализуют те же порты, что и боевые адаптеры (Tasks 3, 4, 6).

**Известное отклонение зафиксировано:** порт `UserRepository` без `list_users`/`set_active` (YAGNI); `pydantic[email]` добавлен для `EmailStr`; `TemplateArticleModel` намеренно не трогаем (отложенная иерархия).
