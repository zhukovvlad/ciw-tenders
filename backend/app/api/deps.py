"""Composition Root: сборка зависимостей (DI) для FastAPI.

Здесь и только здесь конкретные реализации соединяются с абстракциями.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.entities import EstimateStatus, Role, User
from app.domain.errors import TokenError
from app.domain.ports import (
    ArticleImportRepository,
    ArticleRepository,
    Embedder,
    EstimateRepository,
    LLMMatcher,
    ObjectStorage,
    PasswordHasher,
    TaskQueue,
    TokenService,
    UserRepository,
    WorkTypeClassifier,
)
from app.infrastructure.ai.anthropic_matcher import AnthropicLLMMatcher
from app.infrastructure.ai.openrouter_classifier import OpenRouterWorkClassifier
from app.infrastructure.ai.openrouter_embedder import OpenRouterEmbedder
from app.infrastructure.ai.openrouter_matcher import OpenRouterLLMMatcher
from app.infrastructure.auth.jwt_token_service import JwtTokenService
from app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.import_repository import SqlAlchemyArticleImportRepository
from app.infrastructure.db.session import get_session
from app.infrastructure.db.user_repository import SqlAlchemyUserRepository
from app.infrastructure.storage.s3_object_storage import S3ObjectStorage
from app.services.article_service import ArticleService
from app.services.auth_service import AuthService
from app.services.estimate_export_service import EstimateExportService
from app.services.estimate_matching_service import EstimateMatchingService
from app.services.estimate_parser import EstimateParser
from app.services.estimate_review_service import EstimateReviewService
from app.services.estimate_service import EstimateService
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
        timeout_s=settings.ai_call_timeout_s,
        retry_budget=settings.transient_retry_budget,
    )


@lru_cache
def get_llm_matcher() -> LLMMatcher:
    settings = get_settings()
    if settings.llm_provider == "anthropic":
        return AnthropicLLMMatcher(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_llm_model,
            timeout_s=settings.ai_call_timeout_s,
            retry_budget=settings.transient_retry_budget,
        )
    if settings.llm_provider == "openrouter":
        return OpenRouterLLMMatcher(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            model=settings.openrouter_llm_model,
            timeout_s=settings.ai_call_timeout_s,
            retry_budget=settings.transient_retry_budget,
        )
    # страховка: конфиг уже валидирует провайдер, но на случай рассинхронизации.
    raise ValueError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider!r}")


@lru_cache
def get_task_queue() -> TaskQueue:
    # Ленивый импорт: не тащить Celery при старте API-модуля.
    from app.infrastructure.tasks.task_queue import CeleryTaskQueue

    return CeleryTaskQueue()


@lru_cache
def get_work_classifier() -> WorkTypeClassifier:
    settings = get_settings()
    return OpenRouterWorkClassifier(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        model=settings.classifier_model,
        batch_size=settings.classifier_batch_size,
        timeout_s=settings.ai_call_timeout_s,
        retry_budget=settings.transient_retry_budget,
    )


def build_estimate_matching_service(session: Session) -> EstimateMatchingService:
    """Фабрика для Celery-задачи (вне FastAPI DI): репозитории — на ПЕРЕДАННОЙ сессии
    (пиннутый коннект задачи), а embedder/LLM-матчер берём из кэшированных синглтонов
    `get_embedder()`/`get_llm_matcher()`. Они stateless (конфиг + HTTP-клиент), поэтому
    переиспользуются процессом воркера — без создания нового httpx-клиента на каждую
    задачу и каждый gate-retry (иначе течёт пул сокетов на долгоживущем воркере)."""
    settings = get_settings()
    articles = SqlAlchemyArticleRepository(session)
    estimates = SqlAlchemyEstimateRepository(session)
    matcher = MatchingService(
        articles,
        embedder=None,
        llm_matcher=get_llm_matcher(),
        confidence_threshold=settings.confidence_threshold,
        top_k=settings.match_top_k,
    )
    return EstimateMatchingService(
        matcher=matcher,
        embedder=get_embedder(),
        estimates=estimates,
        articles=articles,
        classifier=get_work_classifier(),
    )


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


def get_estimate_parser() -> EstimateParser:
    return EstimateParser()


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    return S3ObjectStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_bucket,
    )


def get_estimate_repository(session: Session = Depends(get_session)) -> EstimateRepository:
    return SqlAlchemyEstimateRepository(session)


def get_estimate_review_service(
    repository: EstimateRepository = Depends(get_estimate_repository),
    articles: ArticleRepository = Depends(get_repository),
) -> EstimateReviewService:
    return EstimateReviewService(estimates=repository, articles=articles)


def get_estimate_service(
    parser: EstimateParser = Depends(get_estimate_parser),
    repository: EstimateRepository = Depends(get_estimate_repository),
    storage: ObjectStorage = Depends(get_object_storage),
    task_queue: TaskQueue = Depends(get_task_queue),
) -> EstimateService:
    return EstimateService(
        parser=parser, repository=repository, storage=storage, task_queue=task_queue
    )


def get_estimate_export_service(
    repository: EstimateRepository = Depends(get_estimate_repository),
    storage: ObjectStorage = Depends(get_object_storage),
) -> EstimateExportService:
    return EstimateExportService(estimates=repository, storage=storage)


def _do_sweep(repo: EstimateRepository, estimate_id: int, max_age_seconds: int) -> bool:
    """Общая логика sweep: лок = арбитр живости (занят → воркер жив → no-op)."""
    if not repo.is_stale_running(estimate_id, max_age_seconds):
        return False
    if not repo.try_matching_lock(estimate_id):
        return False
    try:
        repo.set_status(
            estimate_id, EstimateStatus.PENDING, detail="сброшено после сбоя воркера"
        )
        return True
    finally:
        repo.release_matching_lock(estimate_id)


def sweep_stale_running(estimate_id: int, max_age_seconds: int) -> bool:
    """Сброс зависшего running→pending на ВЫДЕЛЕННОМ коннекте (как Celery-обёртка tasks.py):
    try_lock → set_status → release держатся на ОДНОМ коннекте, иначе commit вернёт его в пул
    и release/lock утекут (грабли SP2 на новом call-site)."""
    from app.infrastructure.db.session import SessionLocal, engine

    conn = engine.connect()
    try:
        session = SessionLocal(bind=conn)  # bind=conn → commit() не вернёт коннект в пул
        try:
            return _do_sweep(SqlAlchemyEstimateRepository(session), estimate_id, max_age_seconds)
        finally:
            session.close()  # внешний conn НЕ закрывает
    finally:
        conn.close()  # лок уже снят в _do_sweep → коннект в пул чистым


def get_stale_sweeper() -> Callable[[int, int], bool]:
    return sweep_stale_running
