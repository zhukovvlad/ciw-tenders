from __future__ import annotations

from app.api.deps import get_llm_matcher
from app.core.config import get_settings
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher
from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher


def _reset_caches() -> None:
    get_settings.cache_clear()
    get_llm_matcher.cache_clear()


def test_factory_openrouter(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    _reset_caches()
    try:
        assert isinstance(get_llm_matcher(), OpenRouterLLMMatcher)
    finally:
        _reset_caches()


def test_factory_anthropic(monkeypatch) -> None:
    # зависит от ANTHROPIC_API_KEY из conftest (иначе валидатор уронит на missing-key,
    # а не на ассерте типа) — см. Global Constraints.
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    _reset_caches()
    try:
        assert isinstance(get_llm_matcher(), AnthropicLLMMatcher)
    finally:
        _reset_caches()
