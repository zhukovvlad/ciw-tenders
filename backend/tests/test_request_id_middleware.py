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
