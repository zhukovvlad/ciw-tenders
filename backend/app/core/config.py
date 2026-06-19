"""Конфигурация приложения. Единственный источник правды для переменных окружения."""

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

    confidence_threshold: float = 0.90
    embedding_model: str = "text-embedding-004"
    llm_model: str = "claude-3-5-sonnet-20240620"
    embedding_dim: int = 768

    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()  # type: ignore[call-arg]
