from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.domain.entities import CatalogArticle, SectionMatchRequest
from app.domain.errors import TransientError
from app.infrastructure.ai.openrouter_tree_matcher import OpenRouterTreeMatcher
from tests.fakes import make_tree_node as _tn


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


def _req() -> SectionMatchRequest:
    nodes = [_tn(1, 1, "4", name="Конструктив"), _tn(2, 2, "4.1", name="Плита")]
    return SectionMatchRequest(
        nodes=nodes, ancestors=[], hints={}, targets=frozenset({1, 2}),
        catalog=[CatalogArticle(1, "4", "Конструктив", None)], precedents=[],
    )


def _ok(text: str, finish: str = "stop") -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}]}


def test_sends_cached_system_block_reasoning_and_max_tokens() -> None:
    client = _FakeClient(data=_ok('[{"i":1,"code":"4","sure":true,"alt":null}]'))
    m = OpenRouterTreeMatcher(api_key="k", client=client, output_reserve_per_row=48)
    resp = m.match_section(_req())
    assert resp.items == [{"i": 1, "code": "4", "sure": True, "alt": None}] and not resp.truncated
    body = client.calls[0]["json"]
    assert body["temperature"] == 0 and body["reasoning"] == {"effort": "low"}
    assert body["max_tokens"] == 2 * 48 + 512
    sys_msg = body["messages"][0]
    assert sys_msg["role"] == "system"
    assert sys_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert "СПРАВОЧНИК" in sys_msg["content"][0]["text"]  # справочник — в кэшируемом префиксе
    assert "ФРАГМЕНТ" in body["messages"][1]["content"]


def test_truncated_response_flagged() -> None:
    client = _FakeClient(data=_ok('[{"i":1,"code":"4","sure":tr', finish="length"))
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.truncated is True and resp.items == []


def test_invalid_json_on_stop_gives_empty_items() -> None:
    client = _FakeClient(data=_ok("извините, не могу"))
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.items == [] and resp.truncated is False


def test_transport_error_exhausts_to_transient() -> None:
    client = _FakeClient(exc=httpx.ConnectError("boom"))
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=2)
    with patch("app.infrastructure.retry.time.sleep"):
        with pytest.raises(TransientError):
            m.match_section(_req())
