"""Tests for auth domain entities."""

from __future__ import annotations

from app.domain.entities import Role, TokenPayload, User


def test_user_defaults() -> None:
    user = User(email="a@b.c", password_hash="h")
    assert user.role is Role.USER
    assert user.is_active is True
    assert user.id is None


def test_role_values() -> None:
    assert Role.ADMIN.value == "admin"
    assert Role.USER.value == "user"


def test_token_payload() -> None:
    assert TokenPayload(user_id=7).user_id == 7
