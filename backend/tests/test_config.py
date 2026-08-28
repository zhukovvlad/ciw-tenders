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


def test_tree_engine_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    # Изолируемся от .env-файла И от переменных окружения, чтобы проверять именно
    # дефолты класса — регресс-гард на опечатку в дефолте, как test_jwt_defaults.
    # Во время ручной проверки разработчик может временно добавить MATCHING_ENGINE=tree в .env.
    monkeypatch.delenv("MATCHING_ENGINE", raising=False)
    monkeypatch.delenv("OPENROUTER_TREE_MODEL", raising=False)
    monkeypatch.delenv("TREE_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("TREE_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("TREE_CHUNK_ROWS", raising=False)
    monkeypatch.delenv("TREE_MIN_CHUNK_ROWS", raising=False)
    monkeypatch.delenv("TREE_OUTPUT_RESERVE_PER_ROW", raising=False)
    monkeypatch.delenv("TREE_PRECEDENTS_BUDGET", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.matching_engine == "rag"
    assert s.openrouter_tree_model == "anthropic/claude-sonnet-5"
    assert s.tree_reasoning_effort == "low"
    assert (s.tree_context_window, s.tree_chunk_rows, s.tree_min_chunk_rows) == (200_000, 120, 10)
    assert (s.tree_output_reserve_per_row, s.tree_precedents_budget) == (48, 2_000)


@pytest.mark.parametrize("env,value", [
    ("MATCHING_ENGINE", "vector"), ("TREE_CONTEXT_WINDOW", "0"), ("TREE_CHUNK_ROWS", "0"),
    ("TREE_MIN_CHUNK_ROWS", "500"), ("OPENROUTER_TREE_MODEL", "  "),
])
def test_tree_engine_validation(monkeypatch: pytest.MonkeyPatch, env: str, value: str) -> None:
    from app.core.config import Settings

    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_tree_call_budget_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # P1-2: собственный бюджет tree-вызова, отдельный от ai_call_timeout_s/transient_retry_budget —
    # регресс-гард на дефолты, как test_tree_engine_defaults.
    from app.core.config import _BACKOFF_BASE_S, _TREE_BUDGET_MARGIN_S, Settings

    monkeypatch.delenv("TREE_CALL_TIMEOUT_S", raising=False)
    monkeypatch.delenv("TREE_RETRY_BUDGET", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.tree_call_timeout_s == 180.0
    assert s.tree_retry_budget == 2
    # инвариант из валидатора (round 3) должен выполняться на дефолтах с запасом — проверяем
    # полную формулу (timeout*budget + бэкофф + запас), а не урезанную, иначе тест не заметит
    # выпадение бэкоффа/запаса из проверки.
    backoff_total = _BACKOFF_BASE_S * (2 ** (s.tree_retry_budget - 1) - 1)
    worst_case = (
        s.tree_call_timeout_s * s.tree_retry_budget + backoff_total + _TREE_BUDGET_MARGIN_S
    )
    assert worst_case <= s.task_soft_time_limit_s


@pytest.mark.parametrize("env,value", [
    ("TREE_CALL_TIMEOUT_S", "0"),
    ("TREE_CALL_TIMEOUT_S", "-1"),
    ("TREE_RETRY_BUDGET", "0"),
    # 400*2 + 0.5 бэкофф + 30 запас = 830.5 > task_soft_time_limit_s=600 → нарушение
    # кросс-полевого инварианта
    ("TREE_CALL_TIMEOUT_S", "400"),
])
def test_tree_call_budget_validation(monkeypatch: pytest.MonkeyPatch, env: str, value: str) -> None:
    from app.core.config import Settings

    monkeypatch.setenv(env, value)
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_backoff_base_mirrors_retry_module() -> None:
    # config.py не может импортировать infrastructure/ (направление зависимостей), поэтому
    # `_BACKOFF_BASE_S` продублирован как отдельная константа — этот тест единственный, кто
    # видит обе копии сразу и ловит расхождение, если кто-то поменяет шаг бэкоффа в одном
    # месте и забудет про другое (тот же паттерн, что `_OUTPUT_MARGIN` в
    # tree_matching_service.py / openrouter_tree_matcher.py, см.
    # test_openrouter_tree_matcher.py).
    from app.core.config import _BACKOFF_BASE_S as _CONFIG_BACKOFF_BASE_S
    from app.infrastructure.retry import _BACKOFF_BASE_S as _RETRY_BACKOFF_BASE_S

    assert _CONFIG_BACKOFF_BASE_S == _RETRY_BACKOFF_BASE_S


def test_backoff_shape_mirrors_config_formula() -> None:
    # test_backoff_base_mirrors_retry_module пинит только шаг (_BACKOFF_BASE_S), но не форму
    # бэкоффа. Если retry.py сменит экспоненциальный бэкофф на линейный/джиттер, оставив
    # _BACKOFF_BASE_S=0.5, geometric-sum формула в config.py::_validate_llm тихо станет неверной,
    # а прежний тест этого не заметит. Гоняем настоящий retry_transient с записывающим sleep
    # (инъекция аргумента, а не патч time.sleep — instrumented_call биндит sleep как keyword
    # default на импорте) и сверяем сумму задержек с формулой из валидатора.
    from app.domain.errors import TransientError
    from app.infrastructure.retry import _BACKOFF_BASE_S, retry_transient

    def _always_fails() -> None:
        raise ValueError("boom")

    for budget, expected_total in ((1, 0.0), (2, 0.5), (3, 1.5)):
        sleeps: list[float] = []
        with pytest.raises(TransientError):
            retry_transient(
                _always_fails,
                budget=budget,
                classify=lambda exc: True,
                sleep=sleeps.append,
            )
        assert sum(sleeps) == _BACKOFF_BASE_S * (2 ** (budget - 1) - 1) == expected_total


def test_tree_call_budget_ignores_backoff_and_margin_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Round 3 P2: прежняя проверка сверяла только TREE_CALL_TIMEOUT_S * TREE_RETRY_BUDGET,
    # игнорируя экспоненциальный бэкофф между попытками (retry.py::retry_transient) и
    # операционный запас. 299.9 * 2 = 599.8 < 600 — старая проверка это пропускала, но
    # истинный худший случай (599.8 + бэкофф 0.5 = 600.3, плюс операционный запас) уже
    # превышает TASK_SOFT_TIME_LIMIT_S=600.
    from app.core.config import Settings

    monkeypatch.setenv("TREE_CALL_TIMEOUT_S", "299.9")
    monkeypatch.setenv("TREE_RETRY_BUDGET", "2")
    with pytest.raises(ValueError):
        Settings(_env_file=None)  # type: ignore[call-arg]
