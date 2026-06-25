"""Конфигурация приложения. Единственный источник правды для переменных окружения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки читаются из переменных окружения / .env (см. .env.example)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    google_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""

    confidence_threshold: float = 0.90
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "google/gemini-embedding-2"
    # LLM-арбитр матчинга — переключаемый провайдер.
    llm_provider: str = "openrouter"  # "openrouter" | "anthropic"
    openrouter_llm_model: str = "anthropic/claude-sonnet-4.6"  # слаг OpenRouter (проверен)
    anthropic_llm_model: str = "claude-sonnet-4-6"             # нативный id Anthropic
    # Классификатор вид-работ/оргструктура — дешёвая модель через OpenRouter, отдельно от арбитра.
    # NB: слаг OpenRouter — сверить с каталогом (как openrouter_llm_model); правится через env.
    classifier_model: str = "anthropic/claude-haiku-4.5"
    classifier_batch_size: int = 40
    openrouter_base_url: str = "https://openrouter.ai/api/v1"  # только для OpenRouter-матчера
    llm_model: str | None = None  # DEPRECATED: задано → ошибка в валидаторе (см. ниже)
    embedding_dim: int = 768

    frontend_origin: str = "http://localhost:5173"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720  # 12 ч

    admin_email: str = ""
    admin_password: str = ""

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "estimates"

    estimate_max_upload_mb: float = 25.0

    # Celery / Redis (брокер на Timeweb). Result backend НЕ используется — БД источник правды.
    celery_broker_url: str = "redis://localhost:6379/0"

    # Тайм-лимиты задачи матчинга (от них зависит истинность семантики running):
    # зависший воркер → SIGKILL/исключение → коннект рвётся → PG отпускает advisory-lock.
    task_soft_time_limit_s: int = 600
    task_time_limit_s: int = 660

    # Инлайн-обработка транзиента в адаптерах эмбеддера/LLM:
    ai_call_timeout_s: float = 30.0       # hard per-call timeout
    transient_retry_budget: int = 3       # попыток на один вызов до TransientError

    # Bounded gate-retry: ожидание готовности справочника (DictionaryNotReadyError → self.retry).
    gate_retry_max: int = 30
    gate_retry_backoff_s: float = 20.0

    @model_validator(mode="after")
    def _validate_llm(self) -> Settings:
        if self.llm_model is not None:
            raise ValueError(
                "LLM_MODEL устарел → задайте OPENROUTER_LLM_MODEL и/или ANTHROPIC_LLM_MODEL"
            )
        valid = {"openrouter", "anthropic"}
        if self.llm_provider not in valid:
            raise ValueError(
                f"LLM_PROVIDER должен быть из {valid}, получено: {self.llm_provider!r}"
            )
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("LLM_PROVIDER=openrouter требует OPENROUTER_API_KEY")
        if self.llm_provider == "openrouter" and not self.openrouter_llm_model.strip():
            raise ValueError("LLM_PROVIDER=openrouter требует непустой OPENROUTER_LLM_MODEL")
        if self.llm_provider == "openrouter" and not self.openrouter_base_url.strip():
            raise ValueError("LLM_PROVIDER=openrouter требует непустой OPENROUTER_BASE_URL")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("LLM_PROVIDER=anthropic требует ANTHROPIC_API_KEY")
        if self.llm_provider == "anthropic" and not self.anthropic_llm_model.strip():
            raise ValueError("LLM_PROVIDER=anthropic требует непустой ANTHROPIC_LLM_MODEL")
        # Классификатор оргзаголовков — ВСЕГДА OpenRouter, НЕЗАВИСИМО от llm_provider
        # (как и эмбеддер). Без этих настроек он молча деградировал бы в UNSURE (401) или
        # упал бы на range(..., step=0) в classify() — поэтому fail-fast здесь.
        if not self.openrouter_api_key:
            raise ValueError("Классификатор/эмбеддер требуют OPENROUTER_API_KEY")
        if not self.openrouter_base_url.strip():
            raise ValueError("Классификатор требует непустой OPENROUTER_BASE_URL")
        if not self.classifier_model.strip():
            raise ValueError("Классификатор требует непустой CLASSIFIER_MODEL")
        if self.classifier_batch_size <= 0:
            raise ValueError("CLASSIFIER_BATCH_SIZE должен быть > 0")
        return self


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()  # type: ignore[call-arg]
