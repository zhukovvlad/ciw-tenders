"""Конфигурация приложения. Единственный источник правды для переменных окружения."""

from __future__ import annotations

from functools import lru_cache

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
    llm_model: str = "claude-3-5-sonnet-20240620"
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


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()  # type: ignore[call-arg]
