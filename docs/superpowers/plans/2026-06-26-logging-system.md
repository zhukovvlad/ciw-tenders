# Система логирования — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Внедрить централизованное логирование backend (FastAPI + Celery + скрипты) со сквозной корреляцией `request_id → task_id` и точками наблюдения за AI-пайплайном.

**Architecture:** stdlib `logging`, человекочитаемый текст (паттерн соседнего UDP): один `setup_logging()`, консоль + ротируемые файлы, уровни на хендлерах, root=DEBUG. Корреляция — через `ContextVar` + `RequestIdFilter`, чистый ASGI-middleware (web) и сигналы Celery (воркер). Наблюдаемость AI — через хелпер `instrumented_call` в AI-слое поверх generic `retry_transient` (хук `on_retry`).

**Tech Stack:** Python 3.11, FastAPI/Starlette, Celery 5.6.3 + Redis, pytest + httpx TestClient, `uv`.

**Spec:** [docs/superpowers/specs/2026-06-26-logging-system-design.md](../specs/2026-06-26-logging-system-design.md)

## Global Constraints

- ruff line-length 100, `target py311`; type hints обязательны; `from __future__ import annotations` в каждом модуле.
- Юнит-тесты НЕ ходят в реальную БД/AI — фейки портов (`tests/fakes.py`) + `app.dependency_overrides`. `tests/conftest.py` задаёт фиктивные env до импорта приложения.
- Запуск всего — через `uv run` из `backend/` (не системный python/pip).
- `LOG_LEVEL`/`LOG_TO_FILE`/`LOG_DIR` читаются из `os.getenv`, НЕ из `Settings` (логирование не зависит от валидации `DATABASE_URL`/`JWT_SECRET`).
- `extra={...}` — только неймспейснутые ключи (`provider`, `latency_ms`, `attempts`, `outcome`, `estimate_id`, ...); НИКОГДА зарезервированные (`name`, `message`, `args`) — иначе `KeyError: Attempt to overwrite`.
- Команды в `justfile` — Windows PowerShell 5.1 (`&&` не работает). Файлы в LF.

---

## File Structure

| Файл | Ответственность |
|---|---|
| `backend/app/core/logging_config.py` | `setup_logging()`, формат, хендлеры, `ContextVar`-ы, `RequestIdFilter`, хелперы корреляции |
| `backend/app/api/middleware.py` | ASGI `RequestIdMiddleware`: request_id в contextvar + заголовок ответа + лог запроса |
| `backend/app/infrastructure/ai/_instrumented.py` | `instrumented_call(...)`: таймер + попытки + summary на всех путях |
| `backend/app/infrastructure/retry.py` | + generic-хук `on_retry` (в гварде) |
| `backend/app/infrastructure/tasks/celery_app.py` | сигналы `setup_logging`/`task_prerun`/`task_postrun`, `worker_hijack_root_logger=False` |
| `backend/app/infrastructure/tasks/task_queue.py` | `enqueue_match` → проброс `request_id` в заголовке |
| `backend/app/main.py` | `setup_logging()` + регистрация middleware |
| `backend/app/services/estimate_matching_service.py` | per-estimate summary + постадийный DEBUG |
| 4 AI-адаптера | вызов `retry_transient` через `instrumented_call` |
| `backend/app/scripts/{create_admin,smoke_import}.py` | `setup_logging()`; `print`→`logger` по правилу |
| `backend/.env.example`, `.gitignore`, `docs/TECH_DEBT.md` | конфиг-флаги, `logs/`, заметка |

---

## Task 1: Ядро логирования (`logging_config`)

**Files:**
- Create: `backend/app/core/logging_config.py`
- Test: `backend/tests/test_logging_config.py`
- Modify: `backend/tests/conftest.py`, `backend/.env.example`, `.gitignore`, `docs/TECH_DEBT.md`

**Interfaces:**
- Produces: `setup_logging() -> None`; `get_request_id() -> str | None`; `bind_request_id(value: str | None) -> None`; `bind_task_id(value: str | None) -> None`; `reset_correlation() -> None`; `class RequestIdFilter(logging.Filter)`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_logging_config.py
from __future__ import annotations

import logging

import app.core.logging_config as lc


def _reset() -> None:
    lc._configured = False
    logging.getLogger().handlers.clear()


def test_setup_idempotent_no_duplicate_handlers(monkeypatch) -> None:
    monkeypatch.setenv("LOG_TO_FILE", "0")
    _reset()
    lc.setup_logging()
    n = len(logging.getLogger().handlers)
    lc.setup_logging()  # второй вызов — no-op
    assert len(logging.getLogger().handlers) == n


def test_root_level_is_debug(monkeypatch) -> None:
    monkeypatch.setenv("LOG_TO_FILE", "0")
    _reset()
    lc.setup_logging()
    assert logging.getLogger().level == logging.DEBUG


def test_filter_sets_default_dash() -> None:
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    assert lc.RequestIdFilter().filter(rec) is True
    assert rec.request_id == "-" and rec.task_id == "-"


def test_filter_uses_contextvar() -> None:
    lc.bind_request_id("abc123")
    lc.bind_task_id("t1")
    try:
        rec = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        lc.RequestIdFilter().filter(rec)
        assert rec.request_id == "abc123" and rec.task_id == "t1"
    finally:
        lc.reset_correlation()


def test_reset_clears_contextvars() -> None:
    lc.bind_request_id("r")
    lc.bind_task_id("t")
    lc.reset_correlation()
    assert lc.get_request_id() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_logging_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.logging_config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/core/logging_config.py
"""Централизованная настройка логирования: setup_logging() + сквозная корреляция.

Уровни задаём ХЕНДЛЕРАМ; root — DEBUG (пол), иначе дефолтный WARNING срежет INFO/DEBUG
ещё до хендлеров (Logger.isEnabledFor отсекает до callHandlers). LOG_LEVEL/LOG_TO_FILE/
LOG_DIR читаем из env, НЕ из Settings — логирование не должно зависеть от валидации
DATABASE_URL/JWT_SECRET (скрипты/воркер настраивают логи до неё).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from pathlib import Path

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)

_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)-25s | "
    "req=%(request_id)s task=%(task_id)s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_NOISY = ("httpx", "httpcore", "urllib3", "botocore", "s3transfer")

_configured = False


def get_request_id() -> str | None:
    return _request_id_var.get()


def bind_request_id(value: str | None) -> None:
    _request_id_var.set(value)


def bind_task_id(value: str | None) -> None:
    _task_id_var.set(value)


def reset_correlation() -> None:
    _request_id_var.set(None)
    _task_id_var.set(None)


class RequestIdFilter(logging.Filter):
    """Подмешивает request_id/task_id из contextvar в каждую запись; дефолт '-'."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        record.task_id = _task_id_var.get() or "-"
        return True


def setup_logging() -> None:
    """Идемпотентно настраивает root-логгер: консоль + (опц.) ротируемые файлы."""
    global _configured
    if _configured:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    to_file = os.getenv("LOG_TO_FILE", "1") != "0"
    default_dir = Path(__file__).resolve().parents[2] / "logs"  # backend/logs
    log_dir = Path(os.getenv("LOG_DIR", default_dir))

    # Кириллица в Windows-консоли (cp1252 → UnicodeEncodeError). errors=replace — страховка.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)
    id_filter = RequestIdFilter()
    handlers: list[logging.Handler] = []

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)
    console.addFilter(id_filter)
    handlers.append(console)

    if to_file:
        os.makedirs(log_dir, exist_ok=True)  # ДО создания файловых хендлеров
        app_file = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        app_file.setFormatter(formatter)
        app_file.setLevel(logging.DEBUG)
        app_file.addFilter(id_filter)
        handlers.append(app_file)

        err_file = logging.handlers.RotatingFileHandler(
            log_dir / "errors.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        err_file.setFormatter(formatter)
        err_file.setLevel(logging.WARNING)
        err_file.addFilter(id_filter)
        handlers.append(err_file)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # пол = минимум по хендлерам; иначе WARNING срежет INFO/DEBUG
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Хендофф uvicorn: его записи идут через наш root, без своих хендлеров (без дублей).
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    _configured = True
    logging.getLogger(__name__).info(
        "Логирование инициализировано (level=%s, to_file=%s, dir=%s)", level, to_file, log_dir
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_logging_config.py -v`
Expected: PASS (5 тестов).

- [ ] **Step 5: Обновить конфиг/доки**

В `backend/tests/conftest.py` добавить (рядом с прочими `os.environ.setdefault`, ДО импорта приложения) — иначе тесты, импортирующие `app.main`, при `create_app()` создадут `backend/logs/`:

```python
os.environ.setdefault("LOG_TO_FILE", "0")  # тесты не пишут лог-файлы (только в память/консоль)
```

В `backend/.env.example` добавить блок (после существующих переменных):

```dotenv
# Логирование
LOG_LEVEL=INFO          # уровень консоли (файлы: app.log=DEBUG, errors.log=WARNING)
LOG_TO_FILE=1           # 0 → только консоль (прод-агрегатор / prefook-concurrency)
# LOG_DIR=               # переопределение каталога логов (default: backend/logs)
```

В `.gitignore` (корень репо) добавить:

```gitignore
backend/logs/
```

В `docs/TECH_DEBT.md` добавить пункт:

```markdown
- **Логи на проде под prefork.** `RotatingFileHandler` не multiprocess-safe: при
  `celery --concurrency>1` процессы гонят ротацию по одному файлу → гонка/порча.
  Решение: `LOG_TO_FILE=0` (лог в stdout, ротация снаружи — systemd/journald).
  Когда появится агрегатор (Loki/ELK) — заменить текстовый форматтер на JSON в
  `app/core/logging_config.py` (код логирования не трогается).
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/logging_config.py backend/tests/test_logging_config.py backend/tests/conftest.py backend/.env.example .gitignore docs/TECH_DEBT.md
git commit -m "feat(logging): ядро setup_logging + контекст корреляции (req/task id)"
```

---

## Task 2: Generic-хук `on_retry` в `retry_transient`

**Files:**
- Modify: `backend/app/infrastructure/retry.py:16-37`
- Test: `backend/tests/test_retry.py` (дополнить)

**Interfaces:**
- Consumes: существующий `retry_transient(fn, *, budget, classify, sleep)`.
- Produces: `retry_transient(fn, *, budget, classify, sleep=time.sleep, on_retry: Callable[[int, Exception], None] | None = None)`. Инвариант: `on_retry` зовётся в гварде `attempt < budget - 1` → число вызовов `== (фактических вызовов fn) - 1` на ОБОИХ путях (успех-после-ретраев и исчерпание).

- [ ] **Step 1: Write the failing test** (дополнить `tests/test_retry.py`)

```python
def test_on_retry_fires_in_guard_on_success_after_retries() -> None:
    events: list[int] = []
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok"

    retry_transient(
        flaky, budget=5, classify=lambda e: isinstance(e, ConnectionError),
        sleep=lambda _: None, on_retry=lambda a, e: events.append(a),
    )
    assert calls["n"] == 3 and events == [0, 1]  # count == fn-calls - 1


def test_on_retry_count_on_budget_exhaustion() -> None:
    events: list[int] = []

    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        retry_transient(
            always, budget=3, classify=lambda e: isinstance(e, ConnectionError),
            sleep=lambda _: None, on_retry=lambda a, e: events.append(a),
        )
    assert events == [0, 1]  # терминальная попытка 2 НЕ вызывает on_retry


def test_on_retry_not_called_on_permanent() -> None:
    events: list[int] = []

    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        retry_transient(
            boom, budget=3, classify=lambda e: isinstance(e, ConnectionError),
            sleep=lambda _: None, on_retry=lambda a, e: events.append(a),
        )
    assert events == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_retry.py -v -k on_retry`
Expected: FAIL — `TypeError: retry_transient() got an unexpected keyword argument 'on_retry'`.

- [ ] **Step 3: Write minimal implementation** — заменить тело `retry_transient` в `backend/app/infrastructure/retry.py`:

```python
def retry_transient(
    fn: Callable[[], _T],
    *,
    budget: int,
    classify: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> _T:
    """Зовёт fn до budget раз, ретраит только транзиент (classify=True); иначе пробрасывает.

    Исчерпан бюджет на транзиенте → TransientError. Бэкофф экспоненциальный (тест мокает sleep).
    on_retry (опц.) вызывается в гварде «ретрай запланирован» → число вызовов == fn-calls - 1
    на обоих путях (успех-после-ретраев и исчерпание): даёт наблюдателю честный attempts.
    """
    last: Exception | None = None
    for attempt in range(budget):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — классифицируем явно ниже
            if not classify(exc):
                raise
            last = exc
            if attempt < budget - 1:
                if on_retry is not None:
                    on_retry(attempt, exc)
                sleep(_BACKOFF_BASE_S * (2**attempt))
    raise TransientError(str(last))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_retry.py -v`
Expected: PASS (старые 3 + новые 3).

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/retry.py backend/tests/test_retry.py
git commit -m "feat(retry): generic-хук on_retry в гварде для наблюдаемости попыток"
```

---

## Task 3: Хелпер `instrumented_call` (наблюдаемость AI-вызова)

**Files:**
- Create: `backend/app/infrastructure/ai/_instrumented.py`
- Test: `backend/tests/test_instrumented_call.py`

**Interfaces:**
- Consumes: `retry_transient(..., on_retry=...)` (Task 2); `TransientError`.
- Produces: `instrumented_call(*, provider: str, model: str, fn: Callable[[], _T], budget: int, classify: Callable[[Exception], bool], sleep=time.sleep, monotonic=time.monotonic) -> _T`. Пишет ОДИН лог-summary на любом исходе с `extra={"provider","model","latency_ms","attempts","outcome"}`, `outcome ∈ {ok, transient_exhausted, error}`; на отказе уровень WARNING + ре-рейз.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_instrumented_call.py
from __future__ import annotations

import logging

import pytest

from app.domain.errors import TransientError
from app.infrastructure.ai._instrumented import instrumented_call

_NOSLEEP = lambda _: None


def _summary(caplog):
    recs = [r for r in caplog.records if hasattr(r, "outcome")]
    assert recs, "summary-запись не найдена"
    return recs[-1]


def test_ok_logs_info_attempts_one(caplog) -> None:
    with caplog.at_level(logging.INFO):
        out = instrumented_call(
            provider="openrouter", model="m", fn=lambda: "ok",
            budget=3, classify=lambda e: True, sleep=_NOSLEEP,
        )
    assert out == "ok"
    rec = _summary(caplog)
    assert rec.outcome == "ok" and rec.attempts == 1 and rec.levelno == logging.INFO
    assert rec.provider == "openrouter" and rec.model == "m" and rec.latency_ms >= 0


def test_attempts_after_retries(caplog) -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("blip")
        return "ok"

    with caplog.at_level(logging.INFO):
        instrumented_call(
            provider="p", model="m", fn=flaky, budget=5,
            classify=lambda e: isinstance(e, ConnectionError), sleep=_NOSLEEP,
        )
    rec = _summary(caplog)
    assert rec.attempts == 2 and rec.outcome == "ok"


def test_transient_exhausted_warns_and_reraises(caplog) -> None:
    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        instrumented_call(
            provider="p", model="m", fn=always, budget=2,
            classify=lambda e: isinstance(e, ConnectionError), sleep=_NOSLEEP,
        )
    rec = _summary(caplog)
    assert rec.outcome == "transient_exhausted" and rec.levelno == logging.WARNING


def test_permanent_error_logged_and_reraised(caplog) -> None:
    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        instrumented_call(
            provider="p", model="m", fn=boom, budget=3,
            classify=lambda e: isinstance(e, ConnectionError), sleep=_NOSLEEP,
        )
    rec = _summary(caplog)
    assert rec.outcome == "error" and rec.levelno == logging.WARNING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_instrumented_call.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.ai._instrumented'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/infrastructure/ai/_instrumented.py
"""Инструментация одного логического AI-вызова: таймер + попытки + summary на ВСЕХ путях.

provider/model живут в адаптере (граница «одного вызова» = обёртка вокруг retry_transient),
поэтому инструментация здесь, в AI-слое, а не в generic retry.py. Ре-рейз обязателен
(load-bearing): классификатор полагается на него для своего UNSURE-фолбэка.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from app.domain.errors import TransientError
from app.infrastructure.retry import retry_transient

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def instrumented_call(
    *,
    provider: str,
    model: str,
    fn: Callable[[], _T],
    budget: int,
    classify: Callable[[Exception], bool],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> _T:
    attempts = 1  # первый вызов fn; on_retry инкрементит → attempts == фактических вызовов fn
    start = monotonic()

    def _on_retry(_attempt: int, _exc: Exception) -> None:
        nonlocal attempts
        attempts += 1

    outcome = "ok"
    try:
        return retry_transient(
            fn, budget=budget, classify=classify, sleep=sleep, on_retry=_on_retry
        )
    except TransientError:
        outcome = "transient_exhausted"
        raise
    except Exception:  # noqa: BLE001 — перманентная: лог + ре-рейз
        outcome = "error"
        raise
    finally:
        latency_ms = round((monotonic() - start) * 1000)
        level = logging.INFO if outcome == "ok" else logging.WARNING
        logger.log(
            level,
            "AI-вызов %s/%s: %s за %d мс (попыток: %d)",
            provider, model, outcome, latency_ms, attempts,
            extra={
                "provider": provider, "model": model,
                "latency_ms": latency_ms, "attempts": attempts, "outcome": outcome,
            },
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_instrumented_call.py -v`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/infrastructure/ai/_instrumented.py backend/tests/test_instrumented_call.py
git commit -m "feat(ai): instrumented_call — summary вызова на всех путях"
```

---

## Task 4: ASGI `RequestIdMiddleware` + интеграция в `create_app`

**Files:**
- Create: `backend/app/api/middleware.py`
- Modify: `backend/app/main.py:1-28`
- Test: `backend/tests/test_request_id_middleware.py`

**Interfaces:**
- Consumes: `bind_request_id`, `reset_correlation` (Task 1).
- Produces: `class RequestIdMiddleware`; `_sanitize(raw: str) -> str`; `_incoming_request_id(scope) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_request_id_middleware.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.middleware import _incoming_request_id, _sanitize
from app.main import app


def test_health_response_has_generated_request_id() -> None:
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) == 8


def test_incoming_request_id_is_reused() -> None:
    r = TestClient(app).get("/health", headers={"X-Request-ID": "myreq123"})
    assert r.headers["x-request-id"] == "myreq123"


def test_sanitize_strips_control_and_truncates() -> None:
    assert _sanitize("a\x00b\nc") == "abc"
    assert len(_sanitize("x" * 200)) == 64


def test_empty_after_sanitize_falls_back_to_generated() -> None:
    scope = {"headers": [(b"x-request-id", b"\x00\x01\x1f")]}
    rid = _incoming_request_id(scope)
    assert len(rid) == 8  # схлопнулся в пустую → сгенерированный
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_request_id_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.api.middleware'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/api/middleware.py
"""Чистый ASGI-middleware корреляции: request_id в contextvar + заголовок ответа + лог запроса.

BaseHTTPMiddleware не используем — у него проблемы с видимостью contextvar в эндпоинте
(разные контексты). Чистый ASGI ставит contextvar в той же корутине, что зовёт downstream.
"""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging_config import bind_request_id, reset_correlation

logger = logging.getLogger("app.request")

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _sanitize(raw: str) -> str:
    """Чистит клиентский X-Request-ID: control-символы прочь, длина ≤ 64 (анти-log-injection)."""
    return _CONTROL.sub("", raw)[:64]


def _incoming_request_id(scope: Scope) -> str:
    for key, value in scope.get("headers", []):
        if key == b"x-request-id":
            rid = _sanitize(value.decode("latin-1"))
            if rid:  # непустой после вычистки — переиспользуем; иначе фоллбэк ниже
                return rid
            break
    return uuid4().hex[:8]


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope)
        bind_request_id(request_id)
        start = time.monotonic()
        status = {"code": 0}

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self._app(scope, receive, _send)
        finally:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.info(
                "%s %s → %s за %d мс",
                scope.get("method", "?"), scope.get("path", "?"), status["code"], duration_ms,
            )
            reset_correlation()
```

- [ ] **Step 4: Подключить в `create_app`** — в `backend/app/main.py` добавить импорты и две строки:

```python
from app.api.middleware import RequestIdMiddleware
from app.core.logging_config import setup_logging
```

В начале `create_app()` — первой строкой:

```python
def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Автоматизатор строительных смет",
        description="RAG-сопоставление строк сметы со справочником СМР",
        version="0.1.0",
    )

    # RequestIdMiddleware регистрируем ПОСЛЕ CORS → он становится ВНЕШНИМ (ставит request_id
    # до остальных, лог запроса оборачивает всё).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_request_id_middleware.py -v`
Expected: PASS (4 теста).

- [ ] **Step 6: Регрессия — весь набор не сломан**

Run: `cd backend && uv run pytest -q`
Expected: PASS (существующие тесты роутов/смет проходят с новым middleware).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/middleware.py backend/app/main.py backend/tests/test_request_id_middleware.py
git commit -m "feat(web): ASGI RequestIdMiddleware + setup_logging в create_app"
```

---

## Task 5: Корреляция Celery (сигналы) + проброс `request_id`

**Files:**
- Modify: `backend/app/infrastructure/tasks/celery_app.py`
- Modify: `backend/app/infrastructure/tasks/task_queue.py`
- Test: `backend/tests/test_celery_correlation.py`

**Interfaces:**
- Consumes: `setup_logging`, `bind_task_id`, `bind_request_id`, `reset_correlation`, `get_request_id` (Task 1).
- Produces: сигнал-хендлеры `_on_task_prerun(task_id, task, **_)`, `_on_task_postrun(**_)`; `CeleryTaskQueue.enqueue_match` пробрасывает `headers={"request_id": ...}`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_celery_correlation.py
from __future__ import annotations

import app.core.logging_config as lc


class _Req:
    def __init__(self, request_id: str) -> None:
        self.request_id = request_id


class _Task:
    def __init__(self, request_id: str) -> None:
        self.request = _Req(request_id)


class _BareReq:
    pass


class _BareTask:
    def __init__(self) -> None:
        self.request = _BareReq()


def test_prerun_binds_then_postrun_resets() -> None:
    from app.infrastructure.tasks.celery_app import _on_task_postrun, _on_task_prerun

    _on_task_prerun(task_id="t-1", task=_Task("r-9"))
    assert lc.get_request_id() == "r-9"
    _on_task_postrun()
    assert lc.get_request_id() is None


def test_prerun_without_header_binds_none() -> None:
    from app.infrastructure.tasks.celery_app import _on_task_postrun, _on_task_prerun

    lc.bind_request_id("leftover")  # имитируем протёкший id от прошлой задачи
    _on_task_prerun(task_id="t-2", task=_BareTask())
    assert lc.get_request_id() is None  # getattr default None — не несём чужой id
    _on_task_postrun()


def test_enqueue_match_propagates_request_id(monkeypatch) -> None:
    import app.infrastructure.tasks.task_queue as tq

    captured: dict = {}
    monkeypatch.setattr(
        tq.match_estimate_task, "apply_async",
        lambda args, headers: captured.update(args=args, headers=headers),
    )
    lc.bind_request_id("req-42")
    try:
        tq.CeleryTaskQueue().enqueue_match(7)
    finally:
        lc.reset_correlation()
    assert captured["args"] == (7,)
    assert captured["headers"] == {"request_id": "req-42"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_celery_correlation.py -v`
Expected: FAIL — `ImportError: cannot import name '_on_task_prerun'`.

- [ ] **Step 3: Реализовать сигналы** — в `backend/app/infrastructure/tasks/celery_app.py` добавить импорты, флаг hijack и хендлеры:

```python
from celery.signals import setup_logging as celery_setup_logging
from celery.signals import task_postrun, task_prerun

from app.core.logging_config import (
    bind_request_id,
    bind_task_id,
    reset_correlation,
    setup_logging,
)
```

В `celery_app.conf.update(...)` добавить строку (рядом с остальными):

```python
    worker_hijack_root_logger=False,  # иначе Celery переопределит наш форматтер/фильтр
```

После `celery_app.conf.update(...)` добавить:

```python
@celery_setup_logging.connect
def _on_setup_logging(**_kwargs) -> None:
    # Перехватываем настройку логирования у Celery → наш setup_logging() (с фильтром req/task).
    setup_logging()


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **_kwargs) -> None:
    bind_task_id(task_id)
    # ВНИМАНИЕ (open item, см. spec §2): точный аксессор кастомного заголовка версионно-зависим
    # в celery 5.6.3. Отказ тихий — request_id останется None. Проверить на реальном Redis (Step 6).
    request_id = getattr(task.request, "request_id", None) if task is not None else None
    bind_request_id(request_id)


@task_postrun.connect
def _on_task_postrun(**_kwargs) -> None:
    reset_correlation()  # ОБЯЗАТЕЛЬНО: solo-pool переиспользует процесс → иначе id протечёт
```

- [ ] **Step 4: Проброс `request_id` в `task_queue.py`** — заменить тело `CeleryTaskQueue`:

```python
from app.core.logging_config import get_request_id
from app.domain.ports import TaskQueue
from app.infrastructure.tasks.tasks import embed_articles_task, match_estimate_task


class CeleryTaskQueue(TaskQueue):
    def enqueue_match(self, estimate_id: int) -> None:
        # request_id едет в заголовке сообщения → воркер восстановит корреляцию (task_prerun).
        match_estimate_task.apply_async(
            (estimate_id,), headers={"request_id": get_request_id()}
        )

    def enqueue_articles_embed(self) -> None:
        # fan-in drain (тянет pending из многих запросов) — НАМЕРЕННО вне request-корреляции,
        # коррелируется только по task_id.
        embed_articles_task.delay()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_celery_correlation.py -v`
Expected: PASS (3 теста).

- [ ] **Step 6: Интеграционная проверка аксессора на РЕАЛЬНОМ брокере (open item, НЕ eager)**

`task_always_eager` сериализует заголовок иначе доставки через Redis — eager пропустит тихую дыру. Проверить вручную (нужен запущенный Redis из `CELERY_BROKER_URL`):

Терминал 1 — воркер:
`cd backend && PYTHONIOENCODING=utf-8 LOG_LEVEL=DEBUG uv run celery -A app.infrastructure.tasks.celery_app worker --pool=solo --loglevel=info --without-mingle --without-gossip`

Терминал 2 — поставить задачу с заголовком:
```bash
cd backend && uv run python -c "from app.core.logging_config import bind_request_id; from app.infrastructure.tasks.task_queue import CeleryTaskQueue; bind_request_id('probe-123'); CeleryTaskQueue().enqueue_match(999999)"
```

Ожидаемо: в логе воркера строки задачи содержат `req=probe-123`. Если `req=-` — аксессор не тот: заменить `getattr(task.request, "request_id", None)` на чтение из `task.request.headers` (или `task.request.get("request_id")`) и повторить. Зафиксировать рабочий аксессор комментарием в коде.

- [ ] **Step 7: Commit**

```bash
git add backend/app/infrastructure/tasks/celery_app.py backend/app/infrastructure/tasks/task_queue.py backend/tests/test_celery_correlation.py
git commit -m "feat(celery): корреляция через сигналы + проброс request_id в заголовке"
```

---

## Task 6: Инструментация 4 AI-адаптеров через `instrumented_call`

**Files:**
- Modify: `backend/app/infrastructure/ai/openrouter_matcher.py:65-76`
- Modify: `backend/app/infrastructure/ai/anthropic_matcher.py:42-60`
- Modify: `backend/app/infrastructure/ai/openrouter_embedder.py:54-59`
- Modify: `backend/app/infrastructure/ai/openrouter_classifier.py:128-139`
- Test: `backend/tests/test_ai_instrumentation.py`

**Interfaces:**
- Consumes: `instrumented_call(...)` (Task 3). Гранулярность: матчеры → 1 INFO/вызов; эмбеддер → 1 INFO/батч (`_post_with_retry`); классификатор → 1 INFO/батч (`_classify_chunk`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_ai_instrumentation.py
from __future__ import annotations

import logging

import httpx

from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_embedder_emits_one_summary_per_batch(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}, {"embedding": [0.2]}]})

    emb = OpenRouterEmbedder(api_key="k", model="google/gemini-embedding-2",
                             client=_client(handler))
    with caplog.at_level(logging.INFO):
        emb.embed_batch(["a", "b"])
    summaries = [r for r in caplog.records if getattr(r, "outcome", None) == "ok"]
    assert len(summaries) == 1  # один батч → одна summary
    assert summaries[0].provider == "openrouter"
    assert summaries[0].model == "google/gemini-embedding-2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_ai_instrumentation.py -v`
Expected: FAIL — summary не пишется (`len(summaries) == 0`), т.к. адаптер ещё зовёт голый `retry_transient`.

- [ ] **Step 3: Реализовать — `openrouter_embedder.py`**, заменить `_post_with_retry`:

```python
from app.infrastructure.ai._instrumented import instrumented_call
# (удалить прежний import retry_transient — он больше не нужен в этом файле)
```

```python
    def _post_with_retry(self, value: str | list[str]) -> list[list[float]]:
        return instrumented_call(
            provider="openrouter", model=self._model,
            fn=lambda: self._post(value),
            budget=self._retry_budget, classify=_is_transient,
        )
```

- [ ] **Step 4: Реализовать — `openrouter_matcher.py`**, заменить вызов в `choose_best`:

```python
from app.infrastructure.ai._instrumented import instrumented_call
# (удалить import retry_transient)
```

```python
        text = instrumented_call(
            provider="openrouter", model=self._model,
            fn=lambda: self._call(user_prompt),
            budget=self._retry_budget, classify=_is_transient,
        )
```

- [ ] **Step 5: Реализовать — `anthropic_matcher.py`**, заменить вызов в `choose_best`:

```python
from app.infrastructure.ai._instrumented import instrumented_call
# (удалить import retry_transient)
```

```python
        text = instrumented_call(
            provider="anthropic", model=self._model,
            fn=_call_llm, budget=self._retry_budget, classify=_is_transient,
        )
```

- [ ] **Step 6: Реализовать — `openrouter_classifier.py`**, заменить вызов в `_classify_chunk` (ре-рейз `instrumented_call` сохраняет внешний `except → UNSURE`):

```python
from app.infrastructure.ai._instrumented import instrumented_call
# (удалить import retry_transient)
```

```python
    def _classify_chunk(self, chunk: list[NodeToClassify]) -> list[WorkClass]:
        prompt = build_batch_prompt(chunk)
        try:
            text = instrumented_call(
                provider="openrouter", model=self._model,
                fn=lambda: self._call(prompt),
                budget=self._retry_budget, classify=_is_transient,
            )
        except Exception:  # noqa: BLE001 — фолбэк по асимметрии: сбой → UNSURE, не ORG
            logger.warning("Классификатор: сбой батча (%d имён) → UNSURE", len(chunk))
            return [WorkClass.UNSURE] * len(chunk)
        return parse_classifications(text, len(chunk))
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ai_instrumentation.py tests/test_openrouter_matcher.py tests/test_anthropic_matcher.py tests/test_openrouter_embedder.py tests/test_openrouter_classifier.py -v`
Expected: PASS — новый тест зелёный, существующие адаптерные тесты не сломаны (поведение то же, добавлен лишь лог).

- [ ] **Step 8: Commit**

```bash
git add backend/app/infrastructure/ai/openrouter_matcher.py backend/app/infrastructure/ai/anthropic_matcher.py backend/app/infrastructure/ai/openrouter_embedder.py backend/app/infrastructure/ai/openrouter_classifier.py backend/tests/test_ai_instrumentation.py
git commit -m "feat(ai): инструментация 4 адаптеров (provider/model/latency/attempts)"
```

---

## Task 7: Per-estimate summary в `EstimateMatchingService`

**Files:**
- Modify: `backend/app/services/estimate_matching_service.py`
- Test: `backend/tests/test_estimate_matching_service.py` (дополнить)

**Interfaces:**
- `_classify_nodes(estimate_id) -> int` (возвращает число исключённых ORG); `_match_nodes(estimate_id) -> Counter[EstimateRowStatus]`. `match_estimate` логирует INFO-summary с `extra={"estimate_id","confident","needs_review","no_match","match_error","excluded","latency_ms"}`.

- [ ] **Step 1: Write the failing test** (дополнить `tests/test_estimate_matching_service.py`)

```python
def test_match_estimate_logs_summary(caplog) -> None:
    import logging

    repo = FakeEstimateRepository()
    est = repo.create(NewEstimate(1, "a.xlsx", "k"), [_node("1")])
    art = _ready_articles([ArticleCandidate(_article(1, "1.1"), 0.97)])
    with caplog.at_level(logging.INFO, logger="app.services.estimate_matching_service"):
        _service(repo, art).match_estimate(est.id)

    recs = [r for r in caplog.records if hasattr(r, "estimate_id")]
    assert recs, "summary-запись не найдена"
    rec = recs[-1]
    assert rec.estimate_id == est.id
    assert rec.confident == 1
    assert rec.needs_review == 0 and rec.no_match == 0 and rec.match_error == 0
    assert rec.latency_ms >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_estimate_matching_service.py::test_match_estimate_logs_summary -v`
Expected: FAIL — `AttributeError`/нет записи с `estimate_id` (summary ещё не логируется).

- [ ] **Step 3: Реализовать** — в `backend/app/services/estimate_matching_service.py`:

Добавить в шапку (после `from __future__ import annotations`):

```python
import logging
import time
from collections import Counter
```

После блока импортов (рядом с `_EMBED_CHUNK`):

```python
logger = logging.getLogger(__name__)
```

Заменить метод `match_estimate` целиком:

```python
    def match_estimate(self, estimate_id: int) -> None:
        if not self._estimates.try_matching_lock(estimate_id):
            return  # конкурент владеет → no-op
        start = time.monotonic()
        excluded = 0
        counts: Counter[EstimateRowStatus] = Counter()
        try:
            self._estimates.set_status(estimate_id, EstimateStatus.RUNNING)  # COMMIT до embed
            excluded = self._classify_nodes(estimate_id)
            logger.debug("Матчинг %s: классификация завершена (ORG-исключено: %d)",
                         estimate_id, excluded)
            self._embed_nodes(estimate_id)
            logger.debug("Матчинг %s: эмбеддинг завершён", estimate_id)
            total, pending = self._articles.matching_readiness()
            if total == 0 or pending > 0:
                raise DictionaryNotReadyError(total=total, pending=pending)
            counts = self._match_nodes(estimate_id)
            logger.debug("Матчинг %s: сопоставление завершено", estimate_id)
            errors = self._estimates.count_node_errors(estimate_id)
            unfinished = self._estimates.count_unfinished_nodes(estimate_id)
            if errors or unfinished:
                self._estimates.set_status(
                    estimate_id,
                    EstimateStatus.PARTIAL_ERROR,
                    detail=f"errors={errors} unfinished={unfinished}",
                )
            else:
                self._estimates.set_status(estimate_id, EstimateStatus.READY)
            self._log_summary(estimate_id, counts, excluded, start)
        except DictionaryNotReadyError:
            raise  # gate: обёртка ретраит/блокирует — summary НЕ пишем (не терминал)
        except Exception as exc:  # noqa: BLE001 — непредвиденный сбой не оставляем в running
            self._estimates.set_status(
                estimate_id, EstimateStatus.PARTIAL_ERROR, detail=f"unexpected: {exc}"
            )
            self._log_summary(estimate_id, counts, excluded, start)
            raise
        finally:
            self._estimates.release_matching_lock(estimate_id)

    def _log_summary(
        self,
        estimate_id: int,
        counts: Counter[EstimateRowStatus],
        excluded: int,
        start: float,
    ) -> None:
        duration_ms = round((time.monotonic() - start) * 1000)
        status = self._estimates.get_status(estimate_id)
        logger.info(
            "Матчинг сметы %s завершён: статус=%s confident=%d needs_review=%d "
            "no_match=%d error=%d excluded=%d за %d мс",
            estimate_id, getattr(status, "value", status),
            counts[EstimateRowStatus.CONFIDENT], counts[EstimateRowStatus.NEEDS_REVIEW],
            counts[EstimateRowStatus.NO_MATCH], counts[EstimateRowStatus.ERROR],
            excluded, duration_ms,
            extra={
                "estimate_id": estimate_id,
                "confident": counts[EstimateRowStatus.CONFIDENT],
                "needs_review": counts[EstimateRowStatus.NEEDS_REVIEW],
                "no_match": counts[EstimateRowStatus.NO_MATCH],
                "match_error": counts[EstimateRowStatus.ERROR],
                "excluded": excluded,
                "latency_ms": duration_ms,
            },
        )
```

Изменить конец `_classify_nodes` — вернуть число исключённых. Заменить хвост метода (строки от `self._estimates.save_node_classifications(results)`) и ранний `return`:

```python
    def _classify_nodes(self, estimate_id: int) -> int:
        nodes = self._estimates.fetch_all_nodes(estimate_id)
        if not nodes:
            return 0
        # ... тело без изменений ...
        self._estimates.save_node_classifications(results)  # один commit, охрана статуса
        return sum(1 for r in results if r.excluded)
```

Изменить `_match_nodes` — накапливать и вернуть `Counter`:

```python
    def _match_nodes(self, estimate_id: int) -> Counter[EstimateRowStatus]:
        counts: Counter[EstimateRowStatus] = Counter()
        for i, node in enumerate(self._estimates.fetch_matchable_nodes(estimate_id), start=1):
            try:
                result = self._matcher.match_one(node.embedding, node.embedding_input)
            except TransientError as exc:  # адаптер исчерпал инлайн-бюджет
                result = NodeMatch(EstimateRowStatus.ERROR, match_error=str(exc))
            counts[result.status] += 1
            self._estimates.save_node_match(node.id, result)
            if i % _HEARTBEAT_EVERY == 0:
                self._estimates.touch(estimate_id)
        return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_estimate_matching_service.py -v`
Expected: PASS — новый summary-тест зелёный, все существующие тесты матчинга не сломаны.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/estimate_matching_service.py backend/tests/test_estimate_matching_service.py
git commit -m "feat(matching): per-estimate summary + постадийный DEBUG"
```

---

## Task 8: Логирование в скриптах

**Files:**
- Modify: `backend/app/scripts/create_admin.py`
- Modify: `backend/app/scripts/smoke_import.py`
- Test: `backend/tests/test_scripts_logging.py`

**Interfaces:**
- Правило: диагностика/статус → `logger`; фактический результат программы → `print`. `create_admin` — статусные строки в `logger`; `smoke_import` — `print(report)` ОСТАЁТСЯ (вывод скрипта), добавляется лишь `setup_logging()`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_scripts_logging.py
from __future__ import annotations

import app.scripts.create_admin as ca
import app.scripts.smoke_import as si


def test_create_admin_uses_logger_not_print() -> None:
    src = ca.__loader__.get_source(ca.__name__)
    assert "print(" not in src  # статусные строки переведены на logger
    assert "logger" in src


def test_smoke_import_keeps_print_report() -> None:
    src = si.__loader__.get_source(si.__name__)
    assert "print(report)" in src  # фактический вывод скрипта остаётся print
    assert "setup_logging" in src  # но логирование инициализируется
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_scripts_logging.py -v`
Expected: FAIL — `create_admin` ещё содержит `print(`; `smoke_import` не зовёт `setup_logging`.

- [ ] **Step 3: Реализовать — `create_admin.py`** (статус → logger):

Добавить в шапку:

```python
import logging

from app.core.logging_config import setup_logging
```

```python
logger = logging.getLogger(__name__)
```

В начале `main()` — первой строкой `setup_logging()`. Заменить три `print(...)` на:

```python
                logger.info("Роль пользователя %s повышена до admin (пароль не изменён).", email)
```
```python
                logger.info("Админ %s уже существует — изменений нет.", email)
```
```python
        logger.info("Создан администратор %s.", email)
```

- [ ] **Step 4: Реализовать — `smoke_import.py`** (оставить `print(report)`, добавить setup):

Добавить в шапку:

```python
from app.core.logging_config import setup_logging
```

В начале `main()` — первой строкой:

```python
    setup_logging()
```

`print(report)` НЕ трогать — это вывод скрипта (отчёт в stdout), а не диагностика.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_scripts_logging.py -v`
Expected: PASS (2 теста).

- [ ] **Step 6: Commit**

```bash
git add backend/app/scripts/create_admin.py backend/app/scripts/smoke_import.py backend/tests/test_scripts_logging.py
git commit -m "feat(scripts): setup_logging + статус через logger (вывод остаётся print)"
```

---

## Финальная проверка (после всех задач)

- [ ] **Полный прогон тестов и линт**

Run: `cd backend && uv run pytest -q && uv run ruff check .`
Expected: все тесты PASS, ruff — без ошибок.

- [ ] **Дымовая проверка web** (ручная): `just dev-back`, затем `curl -i http://localhost:8260/health` — в ответе заголовок `x-request-id`, в `backend/logs/app.log` строка запроса с `req=<id>`.
