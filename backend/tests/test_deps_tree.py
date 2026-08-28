"""Task 10: DI — build_estimate_matching_service выбирает tree-движок по MATCHING_ENGINE."""

from __future__ import annotations

from unittest.mock import MagicMock


def _reset_caches() -> None:
    from app.api import deps
    from app.core.config import get_settings

    get_settings.cache_clear()
    deps.get_tree_matcher.cache_clear()


def test_build_service_uses_tree_when_engine_tree(monkeypatch) -> None:
    from app.api import deps

    monkeypatch.setenv("MATCHING_ENGINE", "tree")
    _reset_caches()
    try:
        svc = deps.build_estimate_matching_service(session=MagicMock())
        assert svc._tree is not None  # noqa: SLF001 — целевой атрибут под тестом
    finally:
        _reset_caches()


def test_build_service_defaults_to_rag_without_engine_set(monkeypatch) -> None:
    from app.api import deps

    monkeypatch.delenv("MATCHING_ENGINE", raising=False)
    _reset_caches()
    try:
        svc = deps.build_estimate_matching_service(session=MagicMock())
        assert svc._tree is None  # noqa: SLF001 — дефолт остаётся RAG
    finally:
        _reset_caches()


def test_tree_matcher_uses_dedicated_tree_budget_not_shared_ai_budget(monkeypatch) -> None:
    # P1-2: до фикса get_tree_matcher собирал OpenRouterTreeMatcher из общего
    # ai_call_timeout_s/transient_retry_budget (max(30, 300)=300s × 3 попытки ≈ 900s — больше,
    # чем весь Celery-таск в 600s). Матчер должен нести СВОИ tree_call_timeout_s/tree_retry_budget.
    from app.api import deps

    monkeypatch.setenv("TREE_CALL_TIMEOUT_S", "111")
    monkeypatch.setenv("TREE_RETRY_BUDGET", "2")
    monkeypatch.setenv("AI_CALL_TIMEOUT_S", "30")
    monkeypatch.setenv("TRANSIENT_RETRY_BUDGET", "3")
    _reset_caches()
    try:
        matcher = deps.get_tree_matcher()
        assert matcher._budget == 2  # noqa: SLF001 — не общий transient_retry_budget=3
        assert matcher._client.timeout.read == 111.0  # noqa: SLF001 — не общий ai_call_timeout_s
    finally:
        _reset_caches()
