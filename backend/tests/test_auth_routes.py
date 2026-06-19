from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import get_password_hasher, get_token_service, get_user_repository
from app.domain.entities import Role, User
from app.main import app
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository

_TS = datetime(2026, 1, 1, tzinfo=UTC)
_ADMIN = User(
    id=1, email="admin@mr.kz", password_hash="hashed::adminpw", role=Role.ADMIN, created_at=_TS
)
_USER = User(
    id=2, email="user@mr.kz", password_hash="hashed::userpw", role=Role.USER, created_at=_TS
)


def _wire_fakes() -> None:
    repo = FakeUserRepository([_ADMIN, _USER])
    app.dependency_overrides[get_user_repository] = lambda: repo
    app.dependency_overrides[get_password_hasher] = FakePasswordHasher
    app.dependency_overrides[get_token_service] = FakeTokenService


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_login_returns_token() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"email": "admin@mr.kz", "password": "adminpw"})
    assert resp.status_code == 200
    assert resp.json()["access_token"] == "token::1"


def test_login_bad_credentials_401() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post("/api/auth/login", json={"email": "admin@mr.kz", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_without_token_is_401_not_403() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401  # HTTPBearer(auto_error=False) → 401, не 403
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_token() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer token::2"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "user@mr.kz"


def test_create_user_as_admin_201() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post(
        "/api/auth/users",
        headers={"Authorization": "Bearer token::1"},
        json={"email": "new@mr.kz", "password": "password123", "role": "user"},
    )
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@mr.kz"


def test_create_user_as_non_admin_403() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post(
        "/api/auth/users",
        headers={"Authorization": "Bearer token::2"},
        json={"email": "new@mr.kz", "password": "password123"},
    )
    assert resp.status_code == 403


def test_create_user_anonymous_401() -> None:
    _wire_fakes()
    client = TestClient(app)
    resp = client.post(
        "/api/auth/users",
        json={"email": "new@mr.kz", "password": "password123"},
    )
    assert resp.status_code == 401  # require_admin → get_current_user → нет токена
