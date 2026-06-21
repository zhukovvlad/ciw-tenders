"""SQL-реализация очереди эмбеддингов поверх template_articles (embedding IS NULL)."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.entities import PendingEmbedding
from app.domain.ports import EmbeddingQueueRepository
from app.infrastructure.db.models import TemplateArticleModel


class SqlAlchemyEmbeddingQueueRepository(EmbeddingQueueRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def fetch_pending(self, limit: int) -> list[PendingEmbedding]:
        stmt = (
            select(TemplateArticleModel.id, TemplateArticleModel.embedding_input)
            .where(TemplateArticleModel.embedding.is_(None))
            .order_by(TemplateArticleModel.id)
            .limit(limit)
        )
        return [PendingEmbedding(id=row.id, embedding_input=row.embedding_input)
                for row in self._session.execute(stmt)]

    def save_embedding(self, article_id: int, embedding_input: str, vector: list[float]) -> bool:
        stmt = (
            update(TemplateArticleModel)
            .where(
                TemplateArticleModel.id == article_id,
                TemplateArticleModel.embedding_input == embedding_input,
            )
            .values(embedding=vector)
        )
        result = self._session.execute(stmt)
        self._session.commit()
        return result.rowcount > 0
