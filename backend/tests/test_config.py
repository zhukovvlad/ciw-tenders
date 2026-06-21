from __future__ import annotations

from app.core.config import Settings


def test_jwt_defaults() -> None:
    settings = Settings(jwt_secret="x")  # type: ignore[call-arg]
    assert settings.jwt_algorithm == "HS256"
    assert settings.jwt_expire_minutes == 720


def test_embedding_defaults() -> None:
    settings = Settings(jwt_secret="x")  # type: ignore[call-arg]
    assert settings.embedding_model == "google/gemini-embedding-2"
    assert settings.embedding_base_url == "https://openrouter.ai/api/v1"
    assert settings.embedding_dim == 768
