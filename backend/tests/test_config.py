from __future__ import annotations

from app.core.config import Settings


def test_jwt_defaults() -> None:
    settings = Settings(jwt_secret="x")  # type: ignore[call-arg]
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expire_minutes == 720
    assert settings.admin_email == ""
