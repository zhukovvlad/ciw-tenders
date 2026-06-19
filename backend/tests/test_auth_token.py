from __future__ import annotations

import jwt
import pytest

from app.domain.entities import User
from app.domain.errors import TokenError
from app.infrastructure.auth.jwt_token_service import JwtTokenService


def _service(expire_minutes: int = 720) -> JwtTokenService:
    return JwtTokenService(secret="s", algorithm="HS256", expire_minutes=expire_minutes)


def test_roundtrip_returns_user_id() -> None:
    service = _service()
    token = service.issue(User(id=42, email="a@b.c", password_hash="h"))
    assert service.decode(token).user_id == 42


def test_sub_is_string_in_raw_token() -> None:
    service = _service()
    token = service.issue(User(id=42, email="a@b.c", password_hash="h"))
    raw = jwt.decode(token, "s", algorithms=["HS256"])
    assert raw["sub"] == "42"  # строка, не int (PyJWT >= 2.10)


def test_expired_token_raises_token_error() -> None:
    service = _service(expire_minutes=-1)  # уже просрочен
    token = service.issue(User(id=1, email="a@b.c", password_hash="h"))
    with pytest.raises(TokenError):
        service.decode(token)


def test_tampered_token_raises_token_error() -> None:
    service = _service()
    with pytest.raises(TokenError):
        service.decode("not.a.valid.token")
