"""ORM-модели. Изолированы от доменных сущностей (маппинг — в репозитории)."""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.infrastructure.db.session import Base

_EMBEDDING_DIM = get_settings().embedding_dim


class TemplateArticleModel(Base):
    __tablename__ = "template_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("template_articles.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    article_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_input: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserModel(Base):
    __tablename__ = "users"
    # Констрейнты и дефолты дублируют DDL ревизии 0001 один-в-один (ORM = источник
    # правды наравне с Alembic). Имена совпадают с именами в миграции.
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="users_role_check"),
        CheckConstraint("email = lower(email)", name="users_email_is_lower"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="user")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EstimateModel(Base):
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    original_object_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    status_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EstimateRowModel(Base):
    __tablename__ = "estimate_rows"
    __table_args__ = (
        UniqueConstraint("estimate_id", "source_index", name="uq_estimate_rows_estimate_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_index: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_input: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_EMBEDDING_DIM), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    matched_article_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    matched_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Double, nullable=True)
    candidates: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    match_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unreviewed"
    )
    final_article_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BenchmarkModel(Base):
    __tablename__ = "benchmark"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BenchmarkNodeModel(Base):
    __tablename__ = "benchmark_node"
    __table_args__ = (
        CheckConstraint(
            "expected_kind IN ('matchable', 'structural', 'no_article')",
            name="benchmark_node_kind_check",
        ),
        UniqueConstraint("benchmark_id", "source_index", name="uq_benchmark_node_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    benchmark_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("benchmark.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_index: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    expected_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_article_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_article_name: Mapped[str | None] = mapped_column(Text, nullable=True)


class DecisionFundModel(Base):
    __tablename__ = "decision_fund"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)  # дебаг, не уникальный
    crumb_version: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)  # БЕЗ FK (см. спеку §4.1)
    votes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'human_review'")
    )
    source_estimate_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("cache_key_hash", "crumb_version", "article_id",
                         name="uq_decision_fund_key_version_article"),
    )
