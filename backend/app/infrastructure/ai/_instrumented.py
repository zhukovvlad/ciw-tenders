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
