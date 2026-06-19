"""Composition Root: сборка зависимостей (DI) для FastAPI.

Здесь и только здесь конкретные реализации соединяются с абстракциями.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.ports import ArticleRepository, Embedder, LLMMatcher
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher
from app.infrastructure.ai.gemini_embedder import GeminiEmbedder
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.session import get_session
from app.services.article_service import ArticleService
from app.services.excel_parser import ExcelEstimateParser
from app.services.matching_service import MatchingService


def get_repository(session: Session = Depends(get_session)) -> ArticleRepository:
    return SqlAlchemyArticleRepository(session)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return GeminiEmbedder(api_key=settings.google_api_key, model=settings.embedding_model)


@lru_cache
def get_llm_matcher() -> LLMMatcher:
    settings = get_settings()
    return AnthropicLLMMatcher(api_key=settings.anthropic_api_key, model=settings.llm_model)


def get_parser() -> ExcelEstimateParser:
    return ExcelEstimateParser()


def get_article_service(
    repository: ArticleRepository = Depends(get_repository),
    embedder: Embedder = Depends(get_embedder),
) -> ArticleService:
    return ArticleService(repository=repository, embedder=embedder)


def get_matching_service(
    repository: ArticleRepository = Depends(get_repository),
    embedder: Embedder = Depends(get_embedder),
    llm_matcher: LLMMatcher = Depends(get_llm_matcher),
    settings: Settings = Depends(get_settings),
) -> MatchingService:
    return MatchingService(
        repository=repository,
        embedder=embedder,
        llm_matcher=llm_matcher,
        confidence_threshold=settings.confidence_threshold,
    )
