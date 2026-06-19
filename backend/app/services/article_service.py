"""Сервис управления справочником: создаёт статьи и сразу их векторизует."""

from __future__ import annotations

from app.domain.entities import TemplateArticle
from app.domain.ports import ArticleRepository, Embedder


class ArticleService:
    def __init__(self, repository: ArticleRepository, embedder: Embedder) -> None:
        self._repository = repository
        self._embedder = embedder

    def create(self, article_code: str, name: str, section_name: str) -> TemplateArticle:
        # Векторизуем по составному тексту, чтобы раздел давал контекст.
        embedding = self._embedder.embed(f"{section_name}. {name}")
        article = TemplateArticle(
            article_code=article_code,
            name=name,
            section_name=section_name,
            embedding=embedding,
        )
        return self._repository.add(article)

    def list(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._repository.list_all(limit=limit, offset=offset)

    def delete(self, article_id: int) -> None:
        self._repository.delete(article_id)
