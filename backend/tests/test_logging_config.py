from __future__ import annotations

import logging

import pytest

import app.core.logging_config as lc


@pytest.fixture()
def fresh_logging(monkeypatch):
    """setup_logging() с чистого листа; teardown ВОЗВРАЩАЕТ _configured=True.

    Иначе оставленный _configured=False позволит повторному setup_logging() в других
    модулях снести caplog-хендлер (root.handlers.clear()) → тихо пустой caplog. Footgun.
    """
    monkeypatch.setenv("LOG_TO_FILE", "0")
    lc._configured = False
    logging.getLogger().handlers.clear()
    yield lc
    lc._configured = True  # повторный setup_logging() → no-op, root.handlers не трогается


def test_setup_idempotent_no_duplicate_handlers(fresh_logging) -> None:
    fresh_logging.setup_logging()
    n = len(logging.getLogger().handlers)
    fresh_logging.setup_logging()  # второй вызов — no-op
    assert len(logging.getLogger().handlers) == n


def test_root_level_is_debug(fresh_logging) -> None:
    fresh_logging.setup_logging()
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
