from __future__ import annotations

import httpx

from app.domain.entities import NodeToClassify, WorkClass
from app.infrastructure.ai.openrouter_classifier import (
    OpenRouterWorkClassifier,
    _strip_fences,
    parse_classifications,
)


class _StubResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._text}}]}


class _StubClient:
    """Мок httpx.Client: .post(...) → _StubResponse с заданным content."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def post(self, url, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append({"url": url, **kwargs})
        return _StubResponse(self._text)


def test_parse_classifications_maps_classes() -> None:
    text = '[{"i": 0, "class": "org"}, {"i": 1, "class": "work"}]'
    assert parse_classifications(text, 2) == [WorkClass.ORG, WorkClass.WORK]


def test_parse_unknown_class_becomes_unsure() -> None:
    text = '[{"i": 0, "class": "banana"}]'
    assert parse_classifications(text, 1) == [WorkClass.UNSURE]


def test_parse_strips_markdown_fences() -> None:
    text = '```json\n[{"i": 0, "class": "org"}]\n```'
    assert parse_classifications(text, 1) == [WorkClass.ORG]


def test_classify_returns_aligned_verdicts() -> None:
    client = _StubClient('[{"i": 0, "class": "org"}, {"i": 1, "class": "work"}]')
    clf = OpenRouterWorkClassifier(api_key="x", client=client)
    items = [
        NodeToClassify("1 Этап ЖК", ()),
        NodeToClassify("Наружное освещение", ("1 Этап ЖК",)),
    ]
    assert clf.classify(items) == [WorkClass.ORG, WorkClass.WORK]


def test_broken_json_falls_back_to_unsure() -> None:
    client = _StubClient("не json вовсе")
    clf = OpenRouterWorkClassifier(api_key="x", client=client)
    items = [NodeToClassify("a", ()), NodeToClassify("b", ())]
    assert clf.classify(items) == [WorkClass.UNSURE, WorkClass.UNSURE]


class _RaisingClient:
    def post(self, url, **kwargs):  # noqa: ANN001, ANN003
        raise httpx.TransportError("boom")


def test_transport_error_falls_back_to_unsure() -> None:
    clf = OpenRouterWorkClassifier(api_key="x", client=_RaisingClient())
    items = [NodeToClassify("a", ()), NodeToClassify("b", ())]
    assert clf.classify(items) == [WorkClass.UNSURE, WorkClass.UNSURE]


def test_strip_fences_tolerates_trailing_text() -> None:
    text = '```json\n[{"i": 0, "class": "org"}]\n```\nкомментарий после рамки'
    assert parse_classifications(_strip_fences(text), 1) == [WorkClass.ORG]
