"""Composition Root: сборка зависимостей (DI) для FastAPI.

Здесь и только здесь конкретные реализации соединяются с абстракциями.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.entities import Role, User
from app.domain.errors import TokenError
from app.domain.ports import (
    ArticleImportRepository,
    ArticleRepository,
    Embedder,
    LLMMatcher,
    PasswordHasher,
    TokenService,
    UserRepository,
)
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher
from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder
from app.infrastructure.auth.jwt_token_service import JwtTokenService
from app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.import_repository import SqlAlchemyArticleImportRepository
from app.infrastructure.db.session import get_session
from app.infrastructure.db.user_repository import SqlAlchemyUserRepository
from app.services.article_service import ArticleService
from app.services.auth_service import AuthService
from app.services.excel_parser import ExcelEstimateParser
from app.services.matching_service import MatchingService
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser

_bearer = HTTPBearer(auto_error=False)


def get_user_repository(session: Session = Depends(get_session)) -> UserRepository:
    return SqlAlchemyUserRepository(session)


@lru_cache
def get_password_hasher() -> PasswordHasher:
    return Argon2PasswordHasher()


@lru_cache
def get_token_service() -> TokenService:
    settings = get_settings()
    return JwtTokenService(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expire_minutes=settings.jwt_expire_minutes,
    )


def get_auth_service(
    users: UserRepository = Depends(get_user_repository),
    hasher: PasswordHasher = Depends(get_password_hasher),
    tokens: TokenService = Depends(get_token_service),
) -> AuthService:
    return AuthService(users=users, hasher=hasher, tokens=tokens)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    users: UserRepository = Depends(get_user_repository),
    tokens: TokenService = Depends(get_token_service),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не аутентифицирован",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        payload = tokens.decode(creds.credentials)
    except TokenError as exc:
        raise unauthorized from exc
    user = users.get_by_id(payload.user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role is not Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Требуются права администратора",
        )
    return user


def get_repository(session: Session = Depends(get_session)) -> ArticleRepository:
    return SqlAlchemyArticleRepository(session)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    return OpenRouterEmbedder(
        api_key=settings.openrouter_api_key,
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
    )


@lru_cache
def get_llm_matcher() -> LLMMatcher:
    settings = get_settings()
    return AnthropicLLMMatcher(api_key=settings.anthropic_api_key, model=settings.llm_model)


def get_parser() -> ExcelEstimateParser:
    return ExcelEstimateParser()


def get_article_service(
    repository: ArticleRepository = Depends(get_repository),
) -> ArticleService:
    return ArticleService(repository=repository)


def get_import_repository(
    session: Session = Depends(get_session),
) -> ArticleImportRepository:
    return SqlAlchemyArticleImportRepository(session)


def get_template_ingest_service(
    repository: ArticleImportRepository = Depends(get_import_repository),
) -> TemplateIngestService:
    return TemplateIngestService(parser=TemplateParser(), repository=repository)


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
