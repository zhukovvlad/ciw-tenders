"""Реализация Embedder через OpenRouter (OpenAI-совместимый /embeddings).

Модель google/gemini-embedding-2 с параметром dimensions=768 (Matryoshka) — вектор
ложится в существующую схему VECTOR(768)/HNSW.
"""

from __future__ import annotations

import httpx

from app.domain.ports import Embedder
from app.infrastructure.ai._instrumented import instrumented_call


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429,) or exc.response.status_code >= 500
    return False


class OpenRouterEmbedder(Embedder):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "google/gemini-embedding-2",
        dimensions: int = 768,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        retry_budget: int = 3,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dimensions = dimensions
        self._retry_budget = retry_budget
        self._client = client or httpx.Client(timeout=timeout_s)

    def _post(self, value: str | list[str]) -> list[list[float]]:
        resp = self._client.post(
            f"{self._base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self._model, "input": value, "dimensions": self._dimensions},
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]

    def _post_with_retry(self, value: str | list[str]) -> list[list[float]]:
        return instrumented_call(
            provider="openrouter", model=self._model,
            fn=lambda: self._post(value),
            budget=self._retry_budget, classify=_is_transient,
        )

    def embed(self, text: str) -> list[float]:
        return self._post_with_retry(text)[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._post_with_retry(texts)
