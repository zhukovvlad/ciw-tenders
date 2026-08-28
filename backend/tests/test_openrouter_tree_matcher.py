from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.domain.entities import CatalogArticle, SectionMatchRequest
from app.domain.errors import TransientError
from app.infrastructure.ai.openrouter_tree_matcher import OpenRouterTreeMatcher, _BodyError
from tests.fakes import make_tree_node as _tn


class _FakeResponse:
    def __init__(self, data: dict, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            raise httpx.HTTPStatusError("boom", request=request, response=self)

    def json(self) -> dict:
        return self._data


class _FakeClient:
    def __init__(
        self, *, data: dict | None = None, exc: Exception | None = None, status_code: int = 200
    ) -> None:
        self._data = data
        self._exc = exc
        self._status_code = status_code
        self.calls: list[dict] = []

    def post(self, url, headers, json) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._exc is not None:
            raise self._exc
        return _FakeResponse(self._data or {}, self._status_code)


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
    # регрессия «справочник просочился и в user-сообщение» удвоила бы некэшируемые токены
    # на каждый вызов и не упала бы ни на одном из assert'ов выше — пин отдельно
    assert "СПРАВОЧНИК" not in body["messages"][1]["content"]


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


def test_http_429_status_error_is_transient() -> None:
    # exercises resp.raise_for_status() -> httpx.HTTPStatusError -> _is_transient's
    # `exc.response.status_code == 429` arm (openrouter_tree_matcher.py, _is_transient)
    client = _FakeClient(data={}, status_code=429)
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        m.match_section(_req())


def test_http_5xx_status_error_is_transient() -> None:
    # exercises the `exc.response.status_code >= 500` arm of the same branch
    client = _FakeClient(data={}, status_code=503)
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        m.match_section(_req())


def test_body_error_transient_becomes_transient() -> None:
    # exercises: if (error := data.get("error")) is not None: ... transient = code == 429
    client = _FakeClient(data={"error": {"code": 429, "message": "rate limited"}})
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        m.match_section(_req())


def test_body_error_permanent_is_loud_not_transient() -> None:
    # exercises the same branch with a non-429/5xx code -> _BodyError(transient=False), re-raised
    client = _FakeClient(data={"error": {"code": 404, "message": "model not found"}})
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(_BodyError) as exc:
        m.match_section(_req())
    assert not exc.value.transient and "model not found" in str(exc.value)


def test_empty_choices_is_transient() -> None:
    # exercises: if not choices: raise _BodyError(..., transient=True)
    client = _FakeClient(data={"choices": []})
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(TransientError):
        m.match_section(_req())


def test_unexpected_choice_structure_is_loud_permanent() -> None:
    # exercises the try/except (KeyError, IndexError, TypeError) around
    # choices[0]["message"]["content"] -> _BodyError(transient=False)
    client = _FakeClient(data={"choices": [{"message": {}}]})
    m = OpenRouterTreeMatcher(api_key="k", client=client, retry_budget=1)
    with pytest.raises(_BodyError) as exc:
        m.match_section(_req())
    assert not exc.value.transient


def test_null_content_is_treated_as_unparseable() -> None:
    # exercises `content = choices[0]["message"]["content"] or ""` (null -> "") ->
    # parse_verdicts("") is None -> items=[], truncated=False
    payload = {"choices": [{"message": {"content": None}, "finish_reason": "stop"}]}
    client = _FakeClient(data=payload)
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.items == [] and resp.truncated is False


def test_missing_finish_reason_key_falls_through_to_parse() -> None:
    # exercises `finish = choices[0].get("finish_reason")` -> None when the key is absent,
    # confirming `if finish == "length"` stays False and verdicts are parsed normally
    client = _FakeClient(
        data={"choices": [{"message": {"content": '[{"i":1,"code":"4","sure":true,"alt":null}]'}}]}
    )
    resp = OpenRouterTreeMatcher(api_key="k", client=client).match_section(_req())
    assert resp.items == [{"i": 1, "code": "4", "sure": True, "alt": None}]
    assert resp.truncated is False
