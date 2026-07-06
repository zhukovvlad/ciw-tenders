# Этап 4, PR-1: Машинные коды ошибок бэкенда — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Каждая пользовательская ошибка и статус матчинга несут стабильный машинный код в теле ответа (`{"detail": <русский текст как раньше>, "code": "<snake_case>"}`), персистируемые статусы получают колонку `estimates.status_code`.

**Architecture:** Базовый `DomainError` с атрибутом `code` (дефолт на классе, переопределение в точке `raise`); `ApiError(HTTPException)` + общие хендлеры рендерят единую форму тела; `LookupError`-точки заменяются доменными `EstimateNotFoundError`/`EstimateRowNotFoundError`. Спека: [2026-07-06-ux-stage4-i18n-design.md](../specs/2026-07-06-ux-stage4-i18n-design.md), §3 (таблица кодов — §3.4, контракт).

**Tech Stack:** FastAPI, pydantic v2, SQLAlchemy + Alembic, pytest + httpx TestClient (фейки портов, без реальной БД/AI).

**Модели исполнения:** реализация — субагенты Sonnet; ревью каждой задачи — Opus.

## Global Constraints

- **Инвариант совместимости (спека §2):** `detail` в каждом ответе остаётся прежним русским текстом; `code` — строго добавка. Существующие тесты на тексты НЕ должны потребовать правок, кроме двух явно названных в Task 4/5.
- Ветка PR-1: `feat/i18n-backend-error-codes` (от `main`). Все команды бэка: `cd backend; uv run ...` (PowerShell 5.1 — разделитель `;`, не `&&`).
- ruff: line-length 100, `target py311`; `from __future__ import annotations` в каждом модуле; type hints обязательны.
- Кириллица в stdout: перед pytest выставить `$env:PYTHONIOENCODING = "utf-8"`.
- Юнит-тесты не ходят в БД/AI: фейки портов ([backend/tests/fakes.py](../../backend/tests/fakes.py)) + `app.dependency_overrides` (паттерны — [backend/tests/conftest.py](../../backend/tests/conftest.py)).
- Номенклатура кодов — таблица §3.4 спеки, копировать имена оттуда посимвольно.
- Миграцию БД не применять к облачной БД в рамках задачи (`just migrate` гоняет владелец) — задача ограничивается файлом ревизии + ORM-моделью + тестом схемы.

---

### Task 1: `DomainError` — базовый класс с кодами

**Files:**
- Modify: `backend/app/domain/errors.py` (полная перезапись)
- Test: `backend/tests/test_domain_error_codes.py` (новый)

**Interfaces:**
- Produces: `DomainError(message: str = "", *, code: str | None = None)` с атрибутом `code: str`; новые классы `EstimateNotFoundError` (code `estimate_not_found`), `EstimateRowNotFoundError` (code `estimate_row_not_found`); у всех 13 существующих классов — дефолтные коды (см. код ниже). Task 2–6 читают `exc.code`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_domain_error_codes.py
"""Контракт кодов доменных ошибок (спека этапа 4, §3.4)."""

from __future__ import annotations

import pytest

from app.domain import errors as de


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (de.AuthError, "invalid_credentials"),
        (de.TokenError, "not_authenticated"),
        (de.DuplicateError, "user_email_exists"),
        (de.StorageError, "storage_unavailable"),
        (de.DeletionGuardError, "template_deletion_guard"),
        (de.DictionaryNotReadyError, "matching_blocked_dictionary"),
        (de.RowNotMatchedError, "row_not_matched"),
        (de.RowNotReviewableError, "row_not_reviewable"),
        (de.InvalidReviewActionError, "review_unknown_action"),
        (de.EstimateNotCompletableError, "estimate_not_completable"),
        (de.EstimateCompletedError, "estimate_completed_readonly"),
        (de.EstimateNotFoundError, "estimate_not_found"),
        (de.EstimateRowNotFoundError, "estimate_row_not_found"),
    ],
)
def test_default_codes(cls: type[de.DomainError], code: str) -> None:
    assert issubclass(cls, de.DomainError)
    assert cls.code == code


def test_ctor_overrides_code() -> None:
    exc = de.AuthError("Учётная запись отключена", code="account_disabled")
    assert exc.code == "account_disabled"
    assert str(exc) == "Учётная запись отключена"


def test_ctor_without_code_keeps_class_default() -> None:
    exc = de.RowNotMatchedError("Строка ещё не сматчена")
    assert exc.code == "row_not_matched"


def test_deletion_guard_keeps_payload_attrs() -> None:
    exc = de.DeletionGuardError(deleted=7, roots_deleted=2)
    assert exc.deleted == 7
    assert exc.roots_deleted == 2
    assert exc.code == "template_deletion_guard"
    assert "Импорт удалит 7 строк" in str(exc)


def test_dictionary_not_ready_keeps_payload_attrs() -> None:
    exc = de.DictionaryNotReadyError(total=10, pending=3)
    assert (exc.total, exc.pending) == (10, 3)
    assert str(exc) == "справочник не готов: total=10 pending=3"


def test_template_validation_requires_explicit_code() -> None:
    # multi-причинный класс: дефолт — базовый "error", код обязателен в точке raise
    exc = de.TemplateValidationError("x", code="template_duplicate_code")
    assert exc.code == "template_duplicate_code"
    assert de.TemplateValidationError.code == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_domain_error_codes.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'DomainError'` / `EstimateNotFoundError`.

- [ ] **Step 3: Write implementation — полная перезапись `backend/app/domain/errors.py`**

```python
"""Доменные исключения (без зависимостей от фреймворков).

Каждое пользовательское исключение несёт машинный код `code` — стабильный
идентификатор семантики для маппинга на локализованный текст на фронте
(этап 4 UX, спека 2026-07-06). Русские тексты сообщений остаются как
человекочитаемый fallback. Правило: код задаётся классовым атрибутом
(типовой случай) или аргументом конструктора (многопричинные классы —
код уточняется в точке raise).
"""

from __future__ import annotations


class DomainError(Exception):
    """Базовый класс доменных ошибок: несёт машинный код для API-контракта."""

    code: str = "error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AuthError(DomainError):
    """Аутентификация не удалась (неверные данные / отключённая учётка)."""

    code = "invalid_credentials"


class DuplicateError(DomainError):
    """Нарушение уникальности (например, email уже существует)."""

    code = "user_email_exists"


class TokenError(DomainError):
    """Токен невалиден, повреждён или просрочен."""

    code = "not_authenticated"


class TemplateValidationError(DomainError):
    """Файл-шаблон структурно некорректен (дубликат кода, сирота-родитель).

    Многопричинный класс: код ОБЯЗАТЕЛЕН в точке raise
    (article_code_not_numeric / article_code_would_be_ancestor /
    article_parent_not_found / template_duplicate_code / template_orphan_parent).
    """


class StorageError(DomainError):
    """Сбой объектного хранилища (MinIO/S3 недоступно или ошибка операции)."""

    code = "storage_unavailable"


class DeletionGuardError(DomainError):
    """Импорт удалил бы слишком много (порог) без явного force."""

    code = "template_deletion_guard"

    def __init__(self, deleted: int, roots_deleted: int) -> None:
        self.deleted = deleted
        self.roots_deleted = roots_deleted
        super().__init__(
            f"Импорт удалит {deleted} строк (из них корней: {roots_deleted}). "
            "Повторите с force=true, если это намеренно."
        )


class TransientError(DomainError):
    """Транзиентный сбой внешнего вызова (сеть/429/таймаут) — исчерпан инлайн-бюджет ретраев.

    Внутренний (гасится retry-обвязкой), до пользователя не доезжает — код не нужен.
    """


class DictionaryNotReadyError(DomainError):
    """Справочник не полностью заэмбежен — матчинг производить нельзя (gate)."""

    code = "matching_blocked_dictionary"

    def __init__(self, total: int, pending: int) -> None:
        self.total = total
        self.pending = pending
        super().__init__(f"справочник не готов: total={total} pending={pending}")


class RowNotMatchedError(DomainError):
    """Строка ещё не сматчена (status=pending) — ревью невозможно. → 409."""

    code = "row_not_matched"


class RowNotReviewableError(DomainError):
    """Строка-контекст (excluded) не решается в ревью. → 409."""

    code = "row_not_reviewable"


class InvalidReviewActionError(DomainError):
    """Действие не применимо к строке (confirm без matched_*, статья не найдена). → 422.

    Многопричинный: дефолт — review_unknown_action; прочие причины уточняют
    код в точке raise (см. спеку §3.4).
    """

    code = "review_unknown_action"


class EstimateNotCompletableError(DomainError):
    """Завершить можно только смету в терминально-успешном статусе (ready/partial_error)."""

    code = "estimate_not_completable"


class EstimateCompletedError(DomainError):
    """Смета завершена (completed_at) — решения ревью read-only до возобновления."""

    code = "estimate_completed_readonly"


class EstimateNotFoundError(DomainError):
    """Смета не существует или недоступна запрашивающему. → 404."""

    code = "estimate_not_found"


class EstimateRowNotFoundError(DomainError):
    """Строка сметы не найдена. → 404."""

    code = "estimate_row_not_found"
```

Примечание: старый docstring модуля («исключения авторизации») устарел ещё до этой задачи — новый отражает фактическое содержимое.

- [ ] **Step 4: Run tests to verify they pass + ничего не сломано**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_domain_error_codes.py -v; uv run pytest -q`
Expected: новый файл PASS; полный прогон зелёный (наследование от `DomainError` поведения `Exception` не меняет).

- [ ] **Step 5: Lint + commit**

```powershell
cd backend; uv run ruff check .; uv run ruff format --check .
git add backend/app/domain/errors.py backend/tests/test_domain_error_codes.py
git commit -m "feat(errors): базовый DomainError с машинными кодами (этап 4, PR-1)"
```

---

### Task 2: `ApiError`, `ErrorOut` и общие хендлеры

**Files:**
- Create: `backend/app/api/errors.py`
- Modify: `backend/app/main.py` (два инлайн-хендлера → `register_error_handlers`)
- Modify: `backend/app/api/schemas.py` (модель `ErrorOut`, добавить рядом с другими Out-моделями)
- Test: `backend/tests/test_error_body.py` (новый)

**Interfaces:**
- Consumes: `DomainError.code` из Task 1.
- Produces: `ApiError(status_code: int, code: str, detail: Any, headers: dict[str, str] | None = None)` — HTTPException с кодом; `register_error_handlers(app: FastAPI) -> None`; `ErrorOut(detail: str | dict, code: str)`. Task 3–5 бросают `ApiError` из роутов.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_error_body.py
"""Единая форма тела ошибки {detail, code}: хендлеры ApiError/AuthError/Duplicate/422."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_wrong_password_has_code(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "wrong-pass"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Неверный email или пароль"  # инвариант: текст не изменился
    assert body["code"] == "invalid_credentials"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_pydantic_422_has_validation_error_code(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"email": "user@example.com"})  # нет password
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert body["detail"] == "Некорректные данные запроса"
    assert isinstance(body["errors"], list) and body["errors"]  # массив pydantic сериализуем
```

Точную фикстуру клиента и сид пользователя взять из существующего `backend/tests/test_auth_routes.py` (там уже есть логин с неверным паролем — скопировать подготовку, не изобретать свою).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_error_body.py -v`
Expected: FAIL — `KeyError: 'code'` (тело сейчас `{"detail": ...}`).

- [ ] **Step 3: Write implementation**

Создать `backend/app/api/errors.py`:

```python
"""HTTP-ошибка с машинным кодом и общие хендлеры единой формы тела (этап 4, PR-1).

Форма тела любой пользовательской ошибки: {"detail": <русский текст>, "code": <snake_case>}.
detail — прежний человекочитаемый текст (инвариант совместимости), code — добавка.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import AuthError, DuplicateError


class ApiError(HTTPException):
    """HTTPException, несущий машинный код для тела ErrorOut."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def register_error_handlers(app: FastAPI) -> None:
    """Хендлеры регистрируются в create_app(); Starlette ищет по __mro__ —
    ApiError-хендлер перекрывает дефолтный HTTPException-хендлер."""

    @app.exception_handler(ApiError)
    def _on_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
            headers=exc.headers,
        )

    @app.exception_handler(AuthError)
    def _on_auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc), "code": exc.code},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(DuplicateError)
    def _on_duplicate(_: Request, exc: DuplicateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": exc.code})

    @app.exception_handler(RequestValidationError)
    def _on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder обязателен: в ctx pydantic-ошибок бывают ValueError (спека §3.2)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Некорректные данные запроса",
                "code": "validation_error",
                "errors": jsonable_encoder(exc.errors()),
            },
        )
```

В `backend/app/main.py`: удалить оба инлайн-хендлера (строки 36–46) и импорт `AuthError, DuplicateError` из `app.domain.errors`; добавить `from app.api.errors import register_error_handlers` и вызов `register_error_handlers(app)` сразу после `app.add_middleware(RequestIdMiddleware)`.

В `backend/app/api/schemas.py` (рядом с другими Out-моделями, документационная модель — в хендлерах не используется, роуты подключат её в `responses=` по мере надобности, не в этом PR):

```python
class ErrorOut(BaseModel):
    """Единая форма тела ошибки: русский detail (fallback) + машинный code."""

    detail: str | dict
    code: str
```

- [ ] **Step 4: Run tests**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_error_body.py tests/test_auth_routes.py -v; uv run pytest -q`
Expected: новые PASS; `test_auth_routes` зелёный без правок (тексты не менялись); полный прогон зелёный.

- [ ] **Step 5: Lint + commit**

```powershell
cd backend; uv run ruff check .; uv run ruff format --check .
git add backend/app/api/errors.py backend/app/api/schemas.py backend/app/main.py backend/tests/test_error_body.py
git commit -m "feat(api): ApiError + единая форма тела ошибки {detail, code}"
```

---

### Task 3: Auth-точки в `deps.py` → `ApiError`

**Files:**
- Modify: `backend/app/api/deps.py:92-96` (unauthorized), `:109-115` (require_admin)
- Test: Modify `backend/tests/test_authz_matrix.py` (добавить ассерты кода)

**Interfaces:**
- Consumes: `ApiError` из Task 2.
- Produces: 401-ответы без/с битым токеном несут `code: "not_authenticated"`; 403 — `code: "admin_required"`.

- [ ] **Step 1: Write the failing test** — в `backend/tests/test_authz_matrix.py` добавить (рядом с существующими проверками статусов, используя те же фикстуры):

```python
def test_401_body_has_not_authenticated_code(client: TestClient) -> None:
    resp = client.get("/api/estimates")  # без Authorization
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Не аутентифицирован", "code": "not_authenticated"}
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_403_body_has_admin_required_code(client: TestClient, user_token: str) -> None:
    resp = client.post(
        "/api/articles/embed", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Требуются права администратора", "code": "admin_required"}
```

Имена фикстур (`client`, `user_token`) сверить с фактическими в `test_authz_matrix.py` и переиспользовать их.

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_authz_matrix.py -v`
Expected: новые тесты FAIL (`code` отсутствует), старые PASS.

- [ ] **Step 3: Implement** — в `backend/app/api/deps.py` добавить импорт `from app.api.errors import ApiError` и заменить:

```python
    unauthorized = ApiError(
        status.HTTP_401_UNAUTHORIZED,
        "not_authenticated",
        "Не аутентифицирован",
        headers={"WWW-Authenticate": "Bearer"},
    )
```

и в `require_admin`:

```python
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "admin_required",
            "Требуются права администратора",
        )
```

- [ ] **Step 4: Run tests**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest -q`
Expected: полный прогон зелёный.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/deps.py backend/tests/test_authz_matrix.py
git commit -m "feat(api): коды not_authenticated/admin_required в auth-точках deps"
```

---

### Task 4: Сметы — роуты, сервисы, 202-статусы

**Files:**
- Modify: `backend/app/services/estimate_review_service.py` (LookupError → новые классы; коды InvalidReviewAction)
- Modify: `backend/app/services/estimate_export_service.py:31,34,41-43`
- Modify: `backend/app/services/estimate_service.py:91`
- Modify: `backend/app/api/routes/estimates.py` (все HTTPException + except-ветки + 202-тело)
- Test: Modify `backend/tests/test_estimate_sweep.py:11,20`; добавить ассерты в `backend/tests/test_estimate_routes.py`, `backend/tests/test_estimate_review.py`, `backend/tests/test_estimate_export.py`, `backend/tests/test_estimate_completion.py`

**Interfaces:**
- Consumes: `ApiError`, `EstimateNotFoundError`, `EstimateRowNotFoundError`, коды классов из Task 1.
- Produces: контракт §3.4 для доменов estimates/upload/review/completion/export/infra + 202-коды.

- [ ] **Step 1: Write the failing tests.** Добавить в существующие файлы (используя их фикстуры и подготовку):

В `test_estimate_routes.py` — рядом с текущим тестом 404 (`:118` и соседние):

```python
def test_get_missing_estimate_body(client, auth_headers) -> None:
    resp = client.get("/api/estimates/999999", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Смета не найдена", "code": "estimate_not_found"}
```

и для upload (`Ожидается файл .xlsx`):

```python
def test_upload_wrong_extension_body(client, auth_headers) -> None:
    resp = client.post(
        "/api/estimates",
        files={"file": ("smeta.txt", b"not xlsx", "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "file_not_xlsx"
    assert resp.json()["detail"] == "Ожидается файл .xlsx"
```

В `test_estimate_review.py` — по одному ассерту `code` на каждую существующую 409/422-проверку (файл уже дёргает эти ветки на `:37,85,99,110`): `estimate_completed_readonly`, `row_not_matched`, `row_not_reviewable`, `review_unknown_action`, `review_confirm_no_recommendation`, `review_pick_requires_article`, `review_article_not_found` — расширить существующие ассерты `resp.json()["code"] == ...`, тексты `detail` НЕ трогать.

В `test_estimate_export.py:73,83` — добавить `assert resp.json()["code"] == "export_unreviewed_rows"` (strict) и `"estimate_not_found"` (404).

В `test_estimate_completion.py:210-227` — `assert resp.json()["code"] == "estimate_not_completable"` на существующей 409-проверке.

Домен infra: найти существующий тест 503 (`Grep "503" backend/tests` / `Grep "Хранилище недоступно" backend/tests`) и добавить `assert resp.json()["code"] == "storage_unavailable"`; если теста 503 нет — добавить его в `test_estimate_routes.py` (фейк storage, кидающий `StorageError` на upload, по образцу фейков файла).

В `test_estimate_sweep.py` — два существующих ассерта текстов заменить на коды (единственное санкционированное изменение ассертов текстов, спека §3.5):

```python
    # было: assert "после сбоя" in resp.json()["detail"]
    assert resp.json()["code"] == "match_requeued"
    # было: assert resp.json()["detail"] == "уже выполняется"
    assert resp.json()["code"] == "match_already_running"
```

- [ ] **Step 2: Run to verify fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_estimate_routes.py tests/test_estimate_review.py tests/test_estimate_export.py tests/test_estimate_completion.py tests/test_estimate_sweep.py -v`
Expected: новые/изменённые ассерты FAIL (`KeyError: 'code'`), остальное PASS.

- [ ] **Step 3: Implement — сервисы.**

`estimate_review_service.py`: импорт `EstimateNotFoundError, EstimateRowNotFoundError` из `app.domain.errors`; замены:
- `:38` и `:62` `raise LookupError("Смета не найдена")` → `raise EstimateNotFoundError("Смета не найдена")`
- `:45` и `:65` `raise LookupError("Строка не найдена")` → `raise EstimateRowNotFoundError("Строка не найдена")`
- `:70` → `raise InvalidReviewActionError("Нет рекомендации AI — confirm недоступен", code="review_confirm_no_recommendation")`
- `:79` → `raise InvalidReviewActionError("pick требует article_id", code="review_pick_requires_article")`
- `:86` → `raise InvalidReviewActionError("Статья не найдена", code="review_article_not_found")`
- `:58` (`Неизвестное действие`) — без изменений: дефолтный код класса `review_unknown_action`.

`estimate_export_service.py`: `:31,:34` → `EstimateNotFoundError("Смета не найдена")`; `:41-43` → `InvalidReviewActionError(f"Не просмотрено строк: {len(unreviewed)}", code="export_unreviewed_rows")`.

`estimate_service.py:91` → `raise EstimateNotFoundError("Смета не найдена")`.

- [ ] **Step 4: Implement — роут `estimates.py`.** Импорт: `from app.api.errors import ApiError`; `from app.domain.errors import EstimateNotFoundError, EstimateRowNotFoundError` (дополнить существующий импорт errors). Замены (детали → `ApiError(status, code, detail)`):

```python
# retrigger_match :80
raise ApiError(status.HTTP_404_NOT_FOUND, "estimate_not_found", "Смета не найдена")
# retrigger_match 202-тело :87-93
if swept:
    code, detail = "match_requeued", "перезапущено после сбоя"
elif est.status == "running":
    code, detail = "match_already_running", "уже выполняется"
else:
    code, detail = "match_queued", "поставлено в очередь"
return {"status": "accepted", "code": code, "detail": detail}
# upload :104
raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_not_xlsx", "Ожидается файл .xlsx")
# upload :106-109
too_large = ApiError(
    status.HTTP_413_CONTENT_TOO_LARGE,
    "file_too_large",
    f"Файл больше {settings.estimate_max_upload_mb} МБ",
)
# upload :116
raise ApiError(
    status.HTTP_422_UNPROCESSABLE_CONTENT, "file_not_zip", "Файл не является .xlsx (ZIP)"
)
# upload :120-123
except ValueError as exc:  # нет обязательных колонок — до put в MinIO
    raise ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "estimate_missing_columns", str(exc)
    ) from exc
except StorageError as exc:  # ТОЛЬКО сбой MinIO → 503; прочее (БД и т.п.) → 500
    raise ApiError(
        status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, "Хранилище недоступно"
    ) from exc
# get_estimate :159 / delete_estimate :172 / toggle_reference :235 — как :80
# review_row :189-198
except (EstimateNotFoundError, EstimateRowNotFoundError) as exc:
    raise ApiError(status.HTTP_404_NOT_FOUND, exc.code, str(exc)) from exc
except EstimateCompletedError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
except RowNotMatchedError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
except RowNotReviewableError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
except InvalidReviewActionError as exc:
    raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code, str(exc)) from exc
# toggle_completion :218-221
except EstimateNotFoundError as exc:
    raise ApiError(status.HTTP_404_NOT_FOUND, exc.code, str(exc)) from exc
except EstimateNotCompletableError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
# export_estimate :263-268
except EstimateNotFoundError as exc:
    raise ApiError(status.HTTP_404_NOT_FOUND, exc.code, str(exc)) from exc
except InvalidReviewActionError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
except StorageError as exc:
    raise ApiError(
        status.HTTP_503_SERVICE_UNAVAILABLE, exc.code, "Хранилище недоступно"
    ) from exc
```

`except LookupError` больше не встречается в файле — проверить `Grep LookupError backend/app` (допустимые остатки — вне поверхности пользователя; если найдутся в этих трёх сервисах, значит замена не полная).

- [ ] **Step 5: Run tests**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest -q`
Expected: полный прогон зелёный.

- [ ] **Step 6: Lint + commit**

```powershell
cd backend; uv run ruff check .; uv run ruff format --check .
git add backend/app/services backend/app/api/routes/estimates.py backend/tests
git commit -m "feat(estimates): машинные коды ошибок и 202-статусов (домены estimates/review/export)"
```

---

### Task 5: Справочник — роуты и сервисы

**Files:**
- Modify: `backend/app/services/article_service.py:21-36`
- Modify: `backend/app/services/template_parser.py:60,72`
- Modify: `backend/app/api/routes/articles.py:44-47,79-82,114-120`
- Test: Modify `backend/tests/test_articles_routes.py`, `backend/tests/test_import_endpoint.py`, `backend/tests/test_article_search.py`

**Interfaces:**
- Consumes: `ApiError`, коды из Task 1.
- Produces: контракт §3.4 для доменов articles/import.

- [ ] **Step 1: Write the failing tests.** В существующие файлы, их фикстурами:

`test_article_search.py` (рядом с `:15`):

```python
def test_short_query_body(client, auth_headers) -> None:
    resp = client.get("/api/articles/search", params={"q": "а"}, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Запрос слишком короткий", "code": "search_query_too_short"}
```

`test_articles_routes.py` — к существующей 409-проверке дубля (`:34`) добавить `assert resp.json()["code"] == "article_code_exists"`; добавить проверку невалидного кода → `article_code_not_numeric` (создание статьи с `article_code` из букв идёт через pydantic-regex → это `validation_error`; `article_code_not_numeric` достижим только через сервис — тест уровня сервиса:

```python
def test_service_rejects_non_numeric_code() -> None:
    svc = make_article_service()  # фабрика/фикстура из существующих тестов сервиса
    with pytest.raises(TemplateValidationError) as ei:
        svc.create(article_code="1.x", name="n", parent_code=None)
    assert ei.value.code == "article_code_not_numeric"
```

— место: `backend/tests/test_article_service.py`, если такого файла нет — положить рядом с тестами сервиса в существующий файл, где уже конструируется `ArticleService` с фейком; аналогично для `article_parent_not_found` и `article_code_would_be_ancestor`).

`test_import_endpoint.py:79` (DeletionGuard) — дополнить:

```python
    body = resp.json()
    assert body["detail"]["force_required"] is True  # форма detail не изменилась
    assert body["code"] == "template_deletion_guard"  # code на верхнем уровне
```

и к 400-проверкам импорта (`:94,109`) — `assert resp.json()["code"] == "template_duplicate_code"` / `"template_orphan_parent"` (сверить, какой из них дёргает каждый тест, по фикстурным файлам).

- [ ] **Step 2: Run to verify fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_article_search.py tests/test_articles_routes.py tests/test_import_endpoint.py -v`
Expected: новые ассерты FAIL.

- [ ] **Step 3: Implement.**

`article_service.py` — коды в точках raise:
- `:21-23` → `TemplateValidationError(f"Код {code} должен состоять из числовых сегментов...", code="article_code_not_numeric")` (текст сохранить посимвольно из текущего кода)
- `:25` → `DuplicateError(f"Статья с кодом {code} уже существует", code="article_code_exists")`
- `:27-30` → `code="article_code_would_be_ancestor"`
- `:36` → `code="article_parent_not_found"`

`template_parser.py`: `:60` → `code="template_duplicate_code"`; `:72` → `code="template_orphan_parent"`.

`routes/articles.py` — импорт `ApiError`; замены:

```python
# search :44-47
raise ApiError(status.HTTP_400_BAD_REQUEST, "search_query_too_short", "Запрос слишком короткий")
# create :79-82
except DuplicateError as exc:
    raise ApiError(status.HTTP_409_CONFLICT, exc.code, str(exc)) from exc
except TemplateValidationError as exc:
    raise ApiError(status.HTTP_400_BAD_REQUEST, exc.code, str(exc)) from exc
# import :114-120
except TemplateValidationError as exc:
    raise ApiError(status.HTTP_400_BAD_REQUEST, exc.code, str(exc)) from exc
except DeletionGuardError as exc:
    raise ApiError(
        status.HTTP_409_CONFLICT,
        exc.code,
        {"message": str(exc), "force_required": True, "deleted": exc.deleted},
    ) from exc
```

Внимание: `DuplicateError` в create-роуте несёт код точки raise (`article_code_exists`), а не классовый дефолт — глобальный хендлер `DuplicateError` из Task 2 сюда не доходит (роут ловит раньше), логика не конфликтует.

- [ ] **Step 4: Run tests**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest -q`
Expected: зелёный.

- [ ] **Step 5: Lint + commit**

```powershell
cd backend; uv run ruff check .; uv run ruff format --check .
git add backend/app/services/article_service.py backend/app/services/template_parser.py backend/app/api/routes/articles.py backend/tests
git commit -m "feat(articles): машинные коды ошибок справочника и импорта"
```

---

### Task 6: Персистируемый `estimates.status_code`

**Files:**
- Create: `backend/alembic/versions/0010_estimate_status_code.py`
- Modify: `backend/app/infrastructure/db/models.py:88` (рядом со `status_detail`)
- Modify: `backend/app/domain/entities.py:252` (поле `Estimate.status_code`)
- Modify: `backend/app/domain/ports.py:219-224` (сигнатура `set_status`)
- Modify: `backend/app/infrastructure/db/estimate_repository.py:88,247-255` (чтение + запись)
- Modify: `backend/tests/fakes.py` (FakeEstimateRepository.set_status + выдача в entity)
- Modify: `backend/app/services/estimate_matching_service.py:99-103,110-112,242-252`
- Modify: `backend/app/infrastructure/tasks/tasks.py:31`
- Modify: `backend/app/api/deps.py:293-296` (_do_sweep)
- Modify: `backend/app/api/schemas.py:245-276` (`EstimateDetailOut.status_code`)
- Test: Modify `backend/tests/test_estimate_models.py`; добавить в тесты матчинг-сервиса (`backend/tests/test_estimate_matching*.py` — найти фактический файл по `Grep "partial_error" backend/tests`)

**Interfaces:**
- Consumes: коды `matching_partial_error` / `matching_unexpected` / `matching_blocked_dictionary` / `matching_reset_after_crash` (§3.4).
- Produces: `set_status(estimate_id, status, detail=None, code=None)`; `Estimate.status_code: str | None`; `EstimateDetailOut.status_code: str | None` — PR-2 читает его для локализованного баннера.

- [ ] **Step 1: Write the failing tests.**

`test_estimate_models.py` (рядом с `:29`): `assert "status_code" in EstimateModel.__table__.columns.keys()`.

Тест сервиса (в файл с тестами матчинга, его фейками):

```python
def test_partial_error_sets_status_code(...) -> None:
    # подготовка как в существующем тесте partial_error этого файла
    ...
    assert fake_estimates.details[est_id] == "errors=1 unfinished=0"   # детальный текст прежний
    assert fake_estimates.codes[est_id] == "matching_partial_error"    # код добавился
```

(поле `codes` появится в фейке на Step 3; форму подготовки скопировать из существующего partial_error-теста).

- [ ] **Step 2: Run to verify fails**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest tests/test_estimate_models.py -v`
Expected: FAIL — колонки нет.

- [ ] **Step 3: Implement.**

Ревизия `backend/alembic/versions/0010_estimate_status_code.py` (по образцу `0004_estimate_match_snapshot.py` — тот же стиль `op.execute`):

```python
"""estimates.status_code — машинный код статуса матчинга (этап 4, PR-1).

Nullable: старые сметы остаются с NULL → фронт показывает сырой status_detail (фолбэк).
"""

from __future__ import annotations

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE estimates ADD COLUMN status_code TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE estimates DROP COLUMN IF EXISTS status_code")
```

`models.py` — после `status_detail`: `status_code: Mapped[str | None] = mapped_column(Text, nullable=True)`.

`entities.py` — в `Estimate` после `status_detail`: `status_code: str | None = None`.

`ports.py`:

```python
    @abstractmethod
    def set_status(
        self,
        estimate_id: int,
        status: EstimateStatus,
        detail: str | None = None,
        code: str | None = None,
    ) -> None:
        """Пишет статус + status_detail + status_code, бампает updated_at.

        detail/code перезаписываются каждым вызовом (переход в READY очищает оба)."""
        ...
```

`estimate_repository.py`: `set_status` — добавить параметр и `status_code=code` в `values(...)`; `:88` — `status_code=m.status_code` при сборке entity.

`fakes.py`: `FakeEstimateRepository.set_status` — принять `code`, писать в `self.codes: dict[int, str | None]` (инициализировать в `__init__` рядом с `self.details`); `:472` — `status_code=self.codes.get(est.id)`.

Писатели:
- `estimate_matching_service.py:99-103` → `detail=f"errors={errors} unfinished={unfinished}", code="matching_partial_error"`
- `:110-112` → `detail=f"unexpected: {exc}", code="matching_unexpected"`
- `mark_blocked(self, estimate_id: int, detail: str, code: str | None = None)`; `:250` → `set_status(estimate_id, EstimateStatus.BLOCKED, detail=detail, code=code)`
- `tasks.py:31` → `service.mark_blocked(estimate_id, detail=f"timeout ждали справочник: {exc}", code=exc.code)` (у `DictionaryNotReadyError` код классовый — `matching_blocked_dictionary`)
- `deps.py:294-296` → `repo.set_status(estimate_id, EstimateStatus.PENDING, detail="сброшено после сбоя воркера", code="matching_reset_after_crash")`

`schemas.py` `EstimateDetailOut`: поле `status_code: str | None = None` после `status_detail`; в `from_entity` — `status_code=e.status_code`.

- [ ] **Step 4: Run tests**

Run: `cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest -q`
Expected: зелёный (фейк принимает новый параметр; сигнатурные несоответствия всплывут здесь).

- [ ] **Step 5: Lint + commit**

```powershell
cd backend; uv run ruff check .; uv run ruff format --check .
git add backend/alembic/versions/0010_estimate_status_code.py backend/app backend/tests
git commit -m "feat(estimates): персистируемый status_code для статусов матчинга"
```

---

### Task 7: Финализация PR-1

**Files:**
- Create: `docs/devlog/2026-07-06-ux-stage4-i18n-backend-codes.md`
- Modify: `docs/TECH_DEBT.md` (если по ходу что-то отложено; иначе не трогать)

**Interfaces:** нет (процедурная задача).

- [ ] **Step 1: Полная верификация**

```powershell
cd backend; $env:PYTHONIOENCODING = "utf-8"; uv run pytest -q; uv run ruff check .; uv run ruff format --check .
```

Expected: всё зелёное. Плюс smoke руками: `Grep -pattern "HTTPException\(" -path backend/app` — остаться должны только определения в `api/errors.py` (наследование) и, возможно, точки вне пользовательской поверхности; каждую оставшуюся объяснить в devlog.

- [ ] **Step 2: Devlog** — краткий отчёт по шаблону соседних файлов в `docs/devlog/`: что сделано (ссылка на спеку §3), инвариант совместимости, список кодов не дублировать (ссылка на §3.4), отложенное — в TECH_DEBT.

- [ ] **Step 3: Push + PR**

```powershell
git push -u origin feat/i18n-backend-error-codes
gh pr create --title "feat(backend): машинные коды ошибок (этап 4 UX, PR-1)" --body "..."
```

Тело PR: цель, ссылка на спеку, инвариант совместимости, чек-лист доменов. PR-2 (фронт) стартует после мержа.
