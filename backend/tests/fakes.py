"""Тестовые дублёры портов (in-memory). Подтверждают, что сервисы зависят от абстракций."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities import ArticleCandidate, TemplateArticle, TokenPayload, User
from app.domain.errors import TokenError
from app.domain.ports import (
    ArticleRepository,
    Embedder,
    LLMMatcher,
    PasswordHasher,
    TokenService,
    UserRepository,
)


class FakeEmbedder(Embedder):
    def embed(self, text: str) -> list[float]:
        return [float(len(text) % 7), 1.0, 0.0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeRepository(ArticleRepository):
    def __init__(self, candidates: list[ArticleCandidate] | None = None) -> None:
        self._candidates = candidates or []
        self._store: list[TemplateArticle] = []

    def add(self, article: TemplateArticle) -> TemplateArticle:
        stored = TemplateArticle(
            id=len(self._store) + 1,
            article_code=article.article_code,
            name=article.name,
            section_name=article.section_name,
            embedding=article.embedding,
        )
        self._store.append(stored)
        return stored

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._store[offset : offset + limit]

    def delete(self, article_id: int) -> None:
        self._store = [a for a in self._store if a.id != article_id]

    def search_similar(self, embedding: list[float], top_k: int = 3) -> list[ArticleCandidate]:
        return self._candidates[:top_k]


class FakeLLMMatcher(LLMMatcher):
    def __init__(self, pick_index: int = 0) -> None:
        self._pick_index = pick_index

    def choose_best(self, query: str, candidates: list[ArticleCandidate]) -> TemplateArticle | None:
        if not candidates:
            return None
        return candidates[self._pick_index].article


class FakePasswordHasher(PasswordHasher):
    def hash(self, plain: str) -> str:
        return f"hashed::{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed::{plain}"


class FakeTokenService(TokenService):
    def issue(self, user: User) -> str:
        return f"token::{user.id}"

    def decode(self, token: str) -> TokenPayload:
        if not token.startswith("token::"):
            raise TokenError("bad token")
        return TokenPayload(user_id=int(token.removeprefix("token::")))


class FakeUserRepository(UserRepository):
    def __init__(self, users: list[User] | None = None) -> None:
        self._store: list[User] = list(users or [])

    def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._store if u.email == email), None)

    def get_by_id(self, user_id: int) -> User | None:
        return next((u for u in self._store if u.id == user_id), None)

    def add(self, user: User) -> User:
        stored = User(
            id=len(self._store) + 1,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            is_active=user.is_active,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),  # noqa: UP017
        )
        self._store.append(stored)
        return stored
