"""Подключение к облачному PostgreSQL (Neon/Supabase) через SQLAlchemy 2.0."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Базовый класс для ORM-моделей."""


_settings = get_settings()
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI-зависимость: открывает сессию на время запроса."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
