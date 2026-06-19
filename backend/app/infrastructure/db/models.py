"""ORM-модели. Изолированы от доменных сущностей (маппинг — в репозитории)."""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.infrastructure.db.session import Base

_EMBEDDING_DIM = get_settings().embedding_dim


class TemplateArticleModel(Base):
    __tablename__ = "template_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    section_name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
