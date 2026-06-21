from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder


def _embedder(
    handler: Callable[[httpx.Request], httpx.Response], captured: dict[str, Any]
) -> OpenRouterEmbedder:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterEmbedder(
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
        model="google/gemini-embedding-2",
        dimensions=768,
        client=client,
    )


def test_embed_single_builds_request_and_parses() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    out = _embedder(handler, captured).embed("бетон")

    assert out == [0.1, 0.2, 0.3]
    assert captured["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "google/gemini-embedding-2"
    assert captured["body"]["dimensions"] == 768
    assert captured["body"]["input"] == "бетон"


def test_embed_batch_sends_list_and_keeps_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["input"] == ["a", "b"]
        return httpx.Response(200, json={"data": [{"embedding": [1.0]}, {"embedding": [2.0]}]})

    out = _embedder(handler, {}).embed_batch(["a", "b"])
    assert out == [[1.0], [2.0]]


def test_embed_batch_empty_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise AssertionError("не должно быть запроса на пустой вход")

    assert _embedder(handler, {}).embed_batch([]) == []
