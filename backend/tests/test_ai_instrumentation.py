from __future__ import annotations

import logging

import httpx

from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_embedder_emits_one_summary_per_batch(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}, {"embedding": [0.2]}]})

    emb = OpenRouterEmbedder(api_key="k", model="google/gemini-embedding-2",
                             client=_client(handler))
    with caplog.at_level(logging.INFO):
        emb.embed_batch(["a", "b"])
    summaries = [r for r in caplog.records if getattr(r, "outcome", None) == "ok"]
    assert len(summaries) == 1  # один батч → одна summary
    assert summaries[0].provider == "openrouter"
    assert summaries[0].model == "google/gemini-embedding-2"
