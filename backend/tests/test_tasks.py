from __future__ import annotations

import pytest

from app.domain.errors import DictionaryNotReadyError
from app.infrastructure.tasks.tasks import run_match


class _Service:
    def __init__(self, raise_gate: bool) -> None:
        self._raise = raise_gate
        self.blocked: list[int] = []
        self.matched: list[int] = []

    def match_estimate(self, estimate_id: int) -> None:
        if self._raise:
            raise DictionaryNotReadyError(total=0, pending=0)
        self.matched.append(estimate_id)

    def mark_blocked(self, estimate_id: int, detail: str) -> None:
        self.blocked.append(estimate_id)


def test_run_match_success() -> None:
    svc = _Service(raise_gate=False)
    run_match(svc, 7, is_final=False)
    assert svc.matched == [7] and svc.blocked == []


def test_run_match_gate_not_final_reraises_for_retry() -> None:
    svc = _Service(raise_gate=True)
    with pytest.raises(DictionaryNotReadyError):
        run_match(svc, 7, is_final=False)        # обёртка сделает self.retry
    assert svc.blocked == []


def test_run_match_gate_final_marks_blocked() -> None:
    svc = _Service(raise_gate=True)
    run_match(svc, 7, is_final=True)             # исчерпаны → blocked, не пробрасывает
    assert svc.blocked == [7]
