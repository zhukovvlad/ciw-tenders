from __future__ import annotations

import pytest

from app.domain.entities import Role, User
from app.domain.errors import AuthError, DuplicateError
from app.services.auth_service import AuthService
from tests.fakes import FakePasswordHasher, FakeTokenService, FakeUserRepository


def _service(users: list[User] | None = None) -> AuthService:
    return AuthService(
        users=FakeUserRepository(users),
        hasher=FakePasswordHasher(),
        tokens=FakeTokenService(),
    )


def _user(**kw: object) -> User:
    base = {"id": 1, "email": "ivan@mr.kz", "password_hash": "hashed::secret"}
    base.update(kw)
    return User(**base)  # type: ignore[arg-type]


def test_login_success_returns_token() -> None:
    service = _service([_user()])
    assert service.login("ivan@mr.kz", "secret") == "token::1"


def test_login_normalizes_email_case() -> None:
    service = _service([_user()])
    assert service.login("  IVAN@MR.KZ ", "secret") == "token::1"


def test_login_wrong_password_raises_auth_error() -> None:
    service = _service([_user()])
    with pytest.raises(AuthError):
        service.login("ivan@mr.kz", "nope")


def test_login_unknown_email_raises_same_auth_error() -> None:
    service = _service([])
    with pytest.raises(AuthError):
        service.login("ghost@mr.kz", "whatever")


def test_login_inactive_user_raises_auth_error() -> None:
    service = _service([_user(is_active=False)])
    with pytest.raises(AuthError):
        service.login("ivan@mr.kz", "secret")


def test_create_user_persists_lowercased_email() -> None:
    service = _service([])
    user = service.create_user("NEW@mr.kz", "password123", Role.ADMIN)
    assert user.email == "new@mr.kz"
    assert user.role is Role.ADMIN
    assert user.id is not None


def test_create_user_duplicate_raises() -> None:
    service = _service([_user()])
    with pytest.raises(DuplicateError):
        service.create_user("ivan@mr.kz", "password123")
