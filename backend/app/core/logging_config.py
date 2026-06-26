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
        record.request_id = _request_id_var.get() or "-"  # type: ignore[attr-defined]
        record.task_id = _task_id_var.get() or "-"  # type: ignore[attr-defined]
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
