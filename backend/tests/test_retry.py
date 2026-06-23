from __future__ import annotations

import pytest

from app.domain.errors import TransientError
from app.infrastructure.retry import retry_transient


def test_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok"

    out = retry_transient(flaky, budget=3, classify=lambda e: isinstance(e, ConnectionError))
    assert out == "ok" and calls["n"] == 3


def test_exhausts_budget_raises_transient() -> None:
    def always():
        raise ConnectionError("blip")

    with pytest.raises(TransientError):
        retry_transient(always, budget=2, classify=lambda e: isinstance(e, ConnectionError))


def test_non_transient_propagates_as_is() -> None:
    def boom():
        raise ValueError("logic")

    with pytest.raises(ValueError):
        retry_transient(boom, budget=3, classify=lambda e: isinstance(e, ConnectionError))
