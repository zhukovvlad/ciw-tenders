"""SQL-реализация очереди эмбеддингов поверх template_articles (embedding IS NULL)."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain.entities import PendingEmbedding
from app.domain.ports import EmbeddingQueueRepository
from app.infrastructure.db.models import TemplateArticleModel

_NS_EMBED = 0x454D4244  # "EMBD" — namespace singleton-лока эмбеддинга справочника


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

    def try_embed_lock(self) -> bool:
        return bool(self._session.scalar(select(func.pg_try_advisory_lock(_NS_EMBED, 0))))

    def release_embed_lock(self) -> None:
        self._session.scalar(select(func.pg_advisory_unlock(_NS_EMBED, 0)))
