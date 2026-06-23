from __future__ import annotations

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher


def _cand(aid: int, code: str, name: str) -> ArticleCandidate:
    return ArticleCandidate(
        TemplateArticle(id=aid, article_code=code, name=name, embedding_input=f"ei {code}"), 0.5
    )


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeContent(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.kwargs: dict | None = None

    def create(self, **kwargs) -> _FakeResponse:
        self.kwargs = kwargs
        return _FakeResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.messages = _FakeMessages(text)


def test_picks_candidate_and_sets_temperature_zero() -> None:
    client = _FakeClient("2")
    matcher = AnthropicLLMMatcher(api_key="x", client=client)
    cands = [_cand(1, "1.1", "Кладка"), _cand(2, "1.2", "Штукатурка")]
    result = matcher.choose_best("штукатурка", cands)
    assert result.article_code == "1.2"
    assert client.messages.kwargs["temperature"] == 0  # детерминизм


def test_empty_candidates_returns_none() -> None:
    assert AnthropicLLMMatcher(api_key="x", client=_FakeClient("1")).choose_best("q", []) is None


def test_refusal_zero_is_none() -> None:
    matcher = AnthropicLLMMatcher(api_key="x", client=_FakeClient("0"))
    assert matcher.choose_best("q", [_cand(1, "1.1", "X")]) is None
