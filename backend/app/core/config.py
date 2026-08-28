"""Конфигурация приложения. Единственный источник правды для переменных окружения."""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Зеркало `app/infrastructure/retry.py::_BACKOFF_BASE_S` — `config.py` не может импортировать
# `infrastructure/` (направление зависимостей api → services → domain ← infrastructure), поэтому
# константа продублирована. Синхронизацию проверяет
# `test_config.py::test_backoff_base_mirrors_retry_module`.
_BACKOFF_BASE_S = 0.5

# Операционный запас для инварианта бюджета tree-вызова (см. `_validate_llm` ниже): устанавливает
# соединение (DNS/TLS-хендшейк до OpenRouter) и собственная работа раннера на чанк (сборка чанка,
# CAS-запись, логирование) занимают время СНАРУЖИ таймаута одной попытки (`tree_call_timeout_s`
# мерит только сам HTTP-вызов), но по-прежнему тратят soft time limit Celery-задачи. Число не
# измерено профилированием — выбрано с явным запасом (десятки секунд) на медленный
# DNS/TLS-хендшейк и GC-паузы под нагрузкой; дефолты (180×2=360 + 0.5 backoff + 30 margin = 390.5)
# оставляют больше 200с запаса до `task_soft_time_limit_s=600`.
_TREE_BUDGET_MARGIN_S = 30.0


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
    # Сколько кандидатов pgvector отдаёт арбитру. 5 (не 3): в тесных кластерах сестёр-статей
    # правильная статья выпадает из топ-3 на доли score (TECH_DEBT «Качество матчинга», Кейс C).
    match_top_k: int = 5
    # Движок сопоставления (спека tree matching 2026-08-27): "rag" (текущий) | "tree".
    matching_engine: str = "rag"
    openrouter_tree_model: str = "anthropic/claude-sonnet-5"
    tree_reasoning_effort: str = "low"     # без ограничения Sonnet 5 давал ×3 completion-токенов
    tree_context_window: int = 200_000     # окно модели, задаётся явно
    tree_chunk_rows: int = 120
    tree_min_chunk_rows: int = 10
    tree_output_reserve_per_row: int = 48
    tree_precedents_budget: int = 2_000
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

    s3_endpoint: str = "http://127.0.0.1:9120"  # дефолт под just minio, см. justfile
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

    # Отдельный бюджет tree-вызова (P1-2 codex round 2): один чанк не должен быть способен
    # пережить бюджет всей Celery-задачи. С дефолтами 180×2=360 < task_soft_time_limit_s=600.
    tree_call_timeout_s: float = 180.0    # hard per-call timeout для tree-матчера
    tree_retry_budget: int = 2            # попыток на один tree-вызов до TransientError

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
        if self.match_top_k <= 0:
            raise ValueError("MATCH_TOP_K должен быть > 0 (иначе арбитр не получит кандидатов)")
        if self.matching_engine not in ("rag", "tree"):
            raise ValueError("MATCHING_ENGINE должен быть 'rag' или 'tree'")
        if not self.openrouter_tree_model.strip():
            raise ValueError("OPENROUTER_TREE_MODEL не может быть пустым")
        if self.tree_context_window <= 0 or self.tree_chunk_rows <= 0:
            raise ValueError("TREE_CONTEXT_WINDOW и TREE_CHUNK_ROWS должны быть > 0")
        if not 1 <= self.tree_min_chunk_rows <= self.tree_chunk_rows:
            raise ValueError("TREE_MIN_CHUNK_ROWS должен быть в [1, TREE_CHUNK_ROWS]")
        if self.tree_output_reserve_per_row <= 0 or self.tree_precedents_budget < 0:
            raise ValueError("TREE_OUTPUT_RESERVE_PER_ROW > 0, TREE_PRECEDENTS_BUDGET >= 0")
        if self.tree_call_timeout_s <= 0:
            raise ValueError("TREE_CALL_TIMEOUT_S должен быть > 0")
        if self.tree_retry_budget < 1:
            raise ValueError("TREE_RETRY_BUDGET должен быть >= 1")
        # Точный худший случай `retry_transient` (retry.py): между попытками 1..budget-1 —
        # экспоненциальный бэкофф `_BACKOFF_BASE_S * 2**attempt`, поэтому суммарный бэкофф —
        # не 0 (как в прежней проверке), а геометрическая прогрессия. Плюс операционный запас
        # `_TREE_BUDGET_MARGIN_S` на то, что происходит вне таймаута самого вызова.
        backoff_total = _BACKOFF_BASE_S * (2 ** (self.tree_retry_budget - 1) - 1)
        worst_case = (
            self.tree_call_timeout_s * self.tree_retry_budget
            + backoff_total
            + _TREE_BUDGET_MARGIN_S
        )
        if worst_case > self.task_soft_time_limit_s:
            raise ValueError(
                "TREE_CALL_TIMEOUT_S * TREE_RETRY_BUDGET + бэкофф между попытками "
                f"(шаг {_BACKOFF_BASE_S}s, экспоненциальный, см. retry.py) + операционный "
                f"запас {_TREE_BUDGET_MARGIN_S}s должны быть <= TASK_SOFT_TIME_LIMIT_S — "
                "иначе один чанк способен пережить бюджет всей задачи"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Кэшированный синглтон настроек."""
    return Settings()  # type: ignore[call-arg]
