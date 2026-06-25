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
    # OpenRouter-ключ нужен всегда (эмбеддер + классификатор — openrouter-only), поэтому
    # задаём фиктивный и проверяем именно embedding-дефолты, а не отсутствие ключа.
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    settings = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert settings.embedding_model == "google/gemini-embedding-2"
    assert settings.embedding_base_url == "https://openrouter.ai/api/v1"
    assert settings.embedding_dim == 768


def test_settings_have_s3_and_upload_limit() -> None:
    from app.core.config import Settings

    s = Settings()  # env заданы в conftest
    assert s.s3_bucket == "estimates"
    assert s.estimate_max_upload_mb == 25.0
    assert s.s3_endpoint  # непустой дефолт


def test_settings_have_celery_and_matching_knobs() -> None:
    from app.core.config import Settings

    s = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert s.celery_broker_url  # непустой дефолт
    assert s.task_time_limit_s > s.task_soft_time_limit_s
    assert s.ai_call_timeout_s > 0
    assert s.transient_retry_budget >= 1
    assert s.gate_retry_max >= 1
    assert s.gate_retry_backoff_s > 0


def test_llm_provider_defaults_to_openrouter() -> None:
    from app.core.config import Settings

    s = Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert s.llm_provider == "openrouter"
    assert s.openrouter_llm_model and s.anthropic_llm_model
    assert s.openrouter_base_url == "https://openrouter.ai/api/v1"


def test_unknown_provider_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValidationError) as exc:
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert "LLM_PROVIDER должен быть из" in str(exc.value)


def test_missing_key_for_provider_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_classifier_requires_openrouter_key_even_on_anthropic(monkeypatch) -> None:
    # Классификатор оргзаголовков ВСЕГДА через OpenRouter (независимо от llm_provider) —
    # без ключа он молча деградировал бы в UNSURE (401), поэтому валидатор обязан падать.
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValidationError) as exc:
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_nonpositive_classifier_batch_size_fails(monkeypatch) -> None:
    # batch_size <= 0 → range(..., step=0) в classify() упал бы в рантайме → fail-fast.
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("CLASSIFIER_BATCH_SIZE", "0")
    with pytest.raises(ValidationError) as exc:
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert "CLASSIFIER_BATCH_SIZE" in str(exc.value)


def test_deprecated_llm_model_fails(monkeypatch) -> None:
    import pytest
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20240620")
    with pytest.raises(ValidationError) as exc:
        Settings(jwt_secret="x", _env_file=None)  # type: ignore[call-arg]
    assert "LLM_MODEL устарел" in str(exc.value)
