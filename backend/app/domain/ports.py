"""Порты (абстрактные интерфейсы) доменного слоя.

Слой приложения (services) зависит ТОЛЬКО от этих абстракций — это Dependency
Inversion Principle. Конкретные реализации живут в infrastructure/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import ArticleCandidate, TemplateArticle


class ArticleRepository(ABC):
    """Хранилище эталонных статей: CRUD + векторный поиск."""

    @abstractmethod
    def add(self, article: TemplateArticle) -> TemplateArticle: ...

    @abstractmethod
    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]: ...

    @abstractmethod
    def delete(self, article_id: int) -> None: ...

    @abstractmethod
    def search_similar(
        self, embedding: list[float], top_k: int = 3
    ) -> list[ArticleCandidate]:
        """Топ-K ближайших статей по эмбеддингу (cosine similarity)."""
        ...


class Embedder(ABC):
    """Порт векторизации текста (RAG: retrieval)."""

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class LLMMatcher(ABC):
    """Порт LLM-арбитра: выбирает лучший кандидат из топ-K (RAG: generation)."""

    @abstractmethod
    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None: ...
