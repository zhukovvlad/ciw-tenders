"""Порты (абстрактные интерфейсы) доменного слоя.

Слой приложения (services) зависит ТОЛЬКО от этих абстракций — это Dependency
Inversion Principle. Конкретные реализации живут в infrastructure/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import (
    ArticleCandidate,
    ExistingArticle,
    ImportPlan,
    TemplateArticle,
    TokenPayload,
    User,
)


class ArticleRepository(ABC):
    """Хранилище эталонных статей: CRUD + векторный поиск."""

    @abstractmethod
    def add(self, article: TemplateArticle) -> TemplateArticle: ...

    @abstractmethod
    def get_by_code(self, code: str) -> TemplateArticle | None: ...

    @abstractmethod
    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]: ...

    @abstractmethod
    def delete(self, article_id: int) -> None: ...

    @abstractmethod
    def search_similar(
        self, embedding: list[float], top_k: int = 3
    ) -> list[ArticleCandidate]:
        """Топ-K ближайших статей по эмбеддингу (cosine similarity)."""
        ...


class Embedder(ABC):
    """Порт векторизации текста (RAG: retrieval)."""

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class LLMMatcher(ABC):
    """Порт LLM-арбитра: выбирает лучший кандидат из топ-K (RAG: generation)."""

    @abstractmethod
    def choose_best(
        self, query: str, candidates: list[ArticleCandidate]
    ) -> TemplateArticle | None: ...


class UserRepository(ABC):
    """Хранилище пользователей."""

    @abstractmethod
    def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    def add(self, user: User) -> User: ...


class PasswordHasher(ABC):
    """Хеширование и проверка паролей."""

    @abstractmethod
    def hash(self, plain: str) -> str: ...

    @abstractmethod
    def verify(self, plain: str, hashed: str) -> bool: ...


class TokenService(ABC):
    """Выпуск и разбор JWT."""

    @abstractmethod
    def issue(self, user: User) -> str: ...

    @abstractmethod
    def decode(self, token: str) -> TokenPayload: ...


class ArticleImportRepository(ABC):
    """Снимок справочника и атомарное применение плана импорта."""

    @abstractmethod
    def load_existing(self) -> list[ExistingArticle]: ...

    @abstractmethod
    def apply_plan(self, plan: ImportPlan) -> None: ...
