"""Инлайн-бюджет ретраев транзиента для внешних вызовов. Граница: исчерпан → TransientError."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from app.domain.errors import TransientError

_BACKOFF_BASE_S = 0.5

_T = TypeVar("_T")


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
