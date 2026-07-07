"""Единая форма тела ошибки {detail, code}: хендлеры ApiError/AuthError/Duplicate/422."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_password_hasher, get_token_service, get_user_repository
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository

_TS = datetime(2026, 1, 1, tzinfo=UTC)
_USER = User(
    id=1,
    email="user@example.com",
    password_hash="hashed::correct-pass",
    role=Role.USER,
    created_at=_TS,
)


@pytest.fixture()
def client() -> TestClient:
    """Локальная фикстура (перекрывает conftest.client для этого файла): сид одного
    пользователя + фейки auth-портов — скопировано из test_auth_routes.py."""
    repo = FakeUserRepository([_USER])
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_password_hasher] = FakePasswordHasher
    app.dependency_overrides[get_token_service] = FakeTokenService
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


def test_login_wrong_password_has_code(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "wrong-pass"}
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Неверный email или пароль"  # инвариант: текст не изменился
    assert body["code"] == "invalid_credentials"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_pydantic_422_has_validation_error_code(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"email": "user@example.com"})  # нет password
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert body["detail"] == "Некорректные данные запроса"
    assert isinstance(body["errors"], list) and body["errors"]  # массив pydantic сериализуем
