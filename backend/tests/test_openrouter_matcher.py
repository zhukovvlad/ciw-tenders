from __future__ import annotations

import httpx
import pytest

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.errors import TransientError
from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher, _BodyError


def _cand(aid: int, code: str, name: str) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"), 0.5
    )


def _cands() -> list[ArticleCandidate]:
    return [_cand(1, "1.1", "Кладка"), _cand(2, "1.2", "Штукатурка")]


class _FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class _FakeClient:
    def __init__(self, *, data: dict | None = None, exc: Exception | None = None) -> None:
        self._data = data
        self._exc = exc
        self.calls: list[dict] = []

    def post(self, url, headers, json) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._data or {})


def _ok(text: str) -> dict:
    return {"choices": [{"message": {"content": text}}]}


def test_picks_candidate_sends_headers_and_temperature() -> None:
    client = _FakeClient(data=_ok("2"))
    matcher = OpenRouterLLMMatcher(api_key="k", client=client)
    result = matcher.choose_best("штукатурка", _cands())
    assert result.article_code == "1.2"
    sent = client.calls[0]
    assert sent["headers"]["HTTP-Referer"] and sent["headers"]["X-Title"]
    assert sent["json"]["temperature"] == 0


def test_transport_error_exhausts_to_transient() -> None:
    client = _FakeClient(exc=httpx.ConnectError("boom"))
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        matcher.choose_best("q", _cands())


def test_body_error_transient_becomes_transient() -> None:
    client = _FakeClient(data={"error": {"code": 429, "message": "rate limited"}})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        matcher.choose_best("q", _cands())


def test_body_error_permanent_is_loud_not_transient() -> None:
    client = _FakeClient(data={"error": {"code": 404, "message": "model not found"}})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(_BodyError) as exc:  # перманент — НЕ TransientError, не None
        matcher.choose_best("q", _cands())
    assert not exc.value.transient and "model not found" in str(exc.value)


def test_empty_choices_is_transient() -> None:
    # ОТДЕЛЬНАЯ ветка от структурной (ниже): пусто/нет choices → ТРАНЗИЕНТ (модель моргнула) →
    # становится TransientError. Граница «пусто=транзиент, кривая структура=перманент» запинена тем,
    # что это РАЗНЫЕ типы исключений (TransientError vs _BodyError), а не оба «просто исключение».
    client = _FakeClient(data={"choices": []})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        matcher.choose_best("q", _cands())


def test_unexpected_choice_structure_is_loud_permanent() -> None:
    # есть choices, но без message.content (некоторые модели/прокси) → НЕ голый KeyError,
    # а перманентный _BodyError с логом (единообразно с error-веткой, без «глухого» partial_error)
    client = _FakeClient(data={"choices": [{"message": {}}]})
    matcher = OpenRouterLLMMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(_BodyError) as exc:
        matcher.choose_best("q", _cands())
    assert not exc.value.transient  # перманент явно — не съедет в транзиент при рефакторе


def test_empty_candidates_returns_none() -> None:
    matcher = OpenRouterLLMMatcher(api_key="k", client=_FakeClient(data=_ok("1")))
    assert matcher.choose_best("q", []) is None
