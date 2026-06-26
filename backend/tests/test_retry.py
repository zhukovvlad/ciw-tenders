from __future__ import annotations

import pytest

from app.domain.errors import TransientError
from app.infrastructure.retry import retry_transient


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok"

    out = retry_transient(
        flaky,
        budget=3,
        classify=lambda e: isinstance(e, ConnectionError),
        sleep=slept.append,
    )
    assert out == "ok" and calls["n"] == 3
    assert slept == [0.5, 1.0]


def test_exhausts_budget_raises_transient() -> None:
    slept: list[float] = []

    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        retry_transient(
            always,
            budget=2,
            classify=lambda e: isinstance(e, ConnectionError),
            sleep=slept.append,
        )
    assert slept == [0.5]


def test_non_transient_propagates_as_is() -> None:
    slept: list[float] = []

    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        retry_transient(
            boom,
            budget=3,
            classify=lambda e: isinstance(e, ConnectionError),
            sleep=slept.append,
        )
    assert slept == []


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
