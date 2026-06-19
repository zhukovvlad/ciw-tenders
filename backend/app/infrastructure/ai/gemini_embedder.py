"""Реализация Embedder через Google Gemini (модель text-embedding-004, 768 dim)."""

from __future__ import annotations

import google.generativeai as genai

from app.domain.ports import Embedder


class GeminiEmbedder(Embedder):
    def __init__(self, api_key: str, model: str = "text-embedding-004") -> None:
        genai.configure(api_key=api_key)
        self._model = f"models/{model}" if not model.startswith("models/") else model

    def embed(self, text: str) -> list[float]:
        result = genai.embed_content(
            model=self._model,
            content=text,
            task_type="retrieval_document",
        )
        return list(result["embedding"])

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result = genai.embed_content(
            model=self._model,
            content=texts,
            task_type="retrieval_document",
        )
        return [list(vec) for vec in result["embedding"]]
