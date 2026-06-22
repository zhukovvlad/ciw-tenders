from __future__ import annotations

import pytest

from app.core.config import Settings


def test_jwt_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # _env_file=None + delenv: изолируемся от .env-файла И от переменных окружения,
    # чтобы проверять именно дефолты класса (регресс-гард на опечатку в дефолте).
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    settings = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert settings.admin_email == ""
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expire_minutes == 720


def test_embedding_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    settings = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert settings.openrouter_api_key == ""
    assert settings.embedding_model == "google/gemini-embedding-2"
    assert settings.embedding_base_url == "https://openrouter.ai/api/v1"
    assert settings.embedding_dim == 768


def test_settings_have_s3_and_upload_limit() -> None:
    from app.core.config import Settings

    s = Settings()  # env заданы в conftest
    assert s.s3_bucket == "estimates"
    assert s.estimate_max_upload_mb == 25.0
    assert s.s3_endpoint  # непустой дефолт
