"""Точка входа FastAPI: инициализация приложения, CORS, подключение роутов."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.middleware import RequestIdMiddleware
from app.api.routes import articles, auth, estimates
from app.core.config import get_settings
from app.core.logging_config import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="Автоматизатор строительных смет",
        description="RAG-сопоставление строк сметы со справочником СМР",
        version="0.1.0",
    )

    # RequestIdMiddleware регистрируем ПОСЛЕ CORS → он становится ВНЕШНИМ (ставит request_id
    # до остальных, лог запроса оборачивает всё).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_error_handlers(app)

    app.include_router(auth.router, prefix="/api")
    app.include_router(articles.router, prefix="/api")
    app.include_router(estimates.router, prefix="/api")

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
