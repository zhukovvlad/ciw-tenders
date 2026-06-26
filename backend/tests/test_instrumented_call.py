from __future__ import annotations

import logging

import pytest

from app.domain.errors import TransientError
from app.infrastructure.ai._instrumented import instrumented_call


def _nosleep(_: float) -> None:
    """No-op sleep function for testing."""


def _summary(caplog):
    recs = [r for r in caplog.records if hasattr(r, "outcome")]
    assert recs, "summary-запись не найдена"
    return recs[-1]


def test_ok_logs_info_attempts_one(caplog) -> None:
    with caplog.at_level(logging.INFO):
        out = instrumented_call(
            provider="openrouter", model="m", fn=lambda: "ok",
            budget=3, classify=lambda e: True, sleep=_nosleep,
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
            classify=lambda e: isinstance(e, ConnectionError), sleep=_nosleep,
        )
    rec = _summary(caplog)
    assert rec.attempts == 2 and rec.outcome == "ok"


def test_transient_exhausted_warns_and_reraises(caplog) -> None:
    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        instrumented_call(
            provider="p", model="m", fn=always, budget=2,
            classify=lambda e: isinstance(e, ConnectionError), sleep=_nosleep,
        )
    rec = _summary(caplog)
    assert rec.outcome == "transient_exhausted" and rec.levelno == logging.WARNING


def test_permanent_error_logged_and_reraised(caplog) -> None:
    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        instrumented_call(
            provider="p", model="m", fn=boom, budget=3,
            classify=lambda e: isinstance(e, ConnectionError), sleep=_nosleep,
        )
    rec = _summary(caplog)
    assert rec.outcome == "error" and rec.levelno == logging.WARNING
