"""Матрица доступа: проверяет, что гварды авторизации работают корректно."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import (
    get_article_service,
    get_password_hasher,
    get_token_service,
    get_user_repository,
)
from app.domain.entities import Role, User
from app.main import app
from app.services.article_service import ArticleService
from tests.fakes import (
    FakeEmbedder,
    FakePasswordHasher,
    FakeRepository,
    FakeTokenService,
    FakeUserRepository,
)

_ADMIN = User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)
_USER = User(id=2, email="user@mr.kz", password_hash="h", role=Role.USER)


def _wire() -> None:
    repo = FakeUserRepository([_ADMIN, _USER])
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_token_service] = FakeTokenService
    app.dependency_overrides[get_password_hasher] = FakePasswordHasher
    app.dependency_overrides[get_article_service] = lambda: ArticleService(
        repository=FakeRepository(), embedder=FakeEmbedder()
    )


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_articles_read_requires_auth() -> None:
    _wire()
    client = TestClient(app)
    assert client.get("/api/articles").status_code == 401


def test_articles_read_allowed_for_user() -> None:
    _wire()
    client = TestClient(app)
    resp = client.get("/api/articles", headers={"Authorization": "Bearer token::2"})
    assert resp.status_code == 200


def test_articles_write_forbidden_for_user() -> None:
    _wire()
    client = TestClient(app)
    resp = client.post(
        "/api/articles",
        headers={"Authorization": "Bearer token::2"},
        json={"article_code": "X", "name": "n", "section_name": "s"},
    )
    assert resp.status_code == 403


def test_articles_write_allowed_for_admin() -> None:
    _wire()
    client = TestClient(app)
    resp = client.post(
        "/api/articles",
        headers={"Authorization": "Bearer token::1"},
        json={"article_code": "X", "name": "n", "section_name": "s"},
    )
    assert resp.status_code == 201
