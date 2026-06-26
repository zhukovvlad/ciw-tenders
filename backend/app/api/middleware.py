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
        if key.lower() == b"x-request-id":
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
                scope.get("method", "?"),
                scope.get("path", "?"),
                status["code"],
                duration_ms,
            )
            reset_correlation()
