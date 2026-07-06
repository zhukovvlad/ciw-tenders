from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_article_service, get_current_user, get_task_queue
from app.domain.entities import Role, User
from app.main import app
from app.services.article_service import ArticleService
from tests.fakes import FakeRepository, FakeTaskQueue


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


def test_create_duplicate_returns_409_with_code() -> None:
    repo = FakeRepository()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_article_service] = lambda: ArticleService(repo)
    app.dependency_overrides[get_task_queue] = lambda: FakeTaskQueue()
    try:
        client = TestClient(app)
        client.post("/api/articles", json={"article_code": "1", "name": "Раздел"})
        resp = client.post("/api/articles", json={"article_code": "1", "name": "Дубль"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "article_code_exists"
    finally:
        app.dependency_overrides.clear()
