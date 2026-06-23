from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_task_queue
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import FakeTaskQueue


def _admin() -> User:
    return User(id=1, email="a@mr.kz", password_hash="h", role=Role.ADMIN)


def _user() -> User:
    return User(id=2, email="u@mr.kz", password_hash="h", role=Role.USER)


def test_admin_embed_enqueues() -> None:
    queue = FakeTaskQueue()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_task_queue] = lambda: queue
    try:
        resp = TestClient(app).post("/api/articles/embed")
        assert resp.status_code == 202 and queue.articles_embed_calls == 1
    finally:
        app.dependency_overrides.clear()


def test_non_admin_embed_forbidden() -> None:
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_task_queue] = lambda: FakeTaskQueue()
    try:
        assert TestClient(app).post("/api/articles/embed").status_code == 403
    finally:
        app.dependency_overrides.clear()
