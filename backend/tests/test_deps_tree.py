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
