"""Реализация ArticleRepository поверх PostgreSQL + pgvector.

Векторный поиск использует оператор косинусной дистанции `<=>` (cosine_distance).
similarity = 1 - cosine_distance, что соответствует порогу 0.90 из ТЗ.
(Оператор L2-дистанции `<->` тоже доступен в pgvector, но для порога-«похожести»
семантически корректнее косинус.)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import ArticleCandidate, TemplateArticle
from app.domain.ports import ArticleRepository
from app.infrastructure.db.models import TemplateArticleModel


class SqlAlchemyArticleRepository(ArticleRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: TemplateArticleModel) -> TemplateArticle:
        return TemplateArticle(
            id=model.id,
            article_code=model.article_code,
            name=model.name,
            section_name=model.section_name,
            embedding=list(model.embedding) if model.embedding is not None else None,
        )

    def add(self, article: TemplateArticle) -> TemplateArticle:
        model = TemplateArticleModel(
            article_code=article.article_code,
            name=article.name,
            section_name=article.section_name,
            embedding=article.embedding,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        stmt = (
            select(TemplateArticleModel)
            .order_by(TemplateArticleModel.id)
            .limit(limit)
            .offset(offset)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def delete(self, article_id: int) -> None:
        model = self._session.get(TemplateArticleModel, article_id)
        if model is not None:
            self._session.delete(model)
            self._session.commit()

    def search_similar(
        self, embedding: list[float], top_k: int = 3
    ) -> list[ArticleCandidate]:
        distance = TemplateArticleModel.embedding.cosine_distance(embedding)
        stmt = (
            select(TemplateArticleModel, distance.label("distance"))
            .order_by(distance)
            .limit(top_k)
        )
        candidates: list[ArticleCandidate] = []
        for model, dist in self._session.execute(stmt):
            candidates.append(
                ArticleCandidate(article=self._to_entity(model), score=1.0 - float(dist))
            )
        return candidates
