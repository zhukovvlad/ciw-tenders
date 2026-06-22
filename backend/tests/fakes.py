"""Тестовые дублёры портов (in-memory). Подтверждают, что сервисы зависят от абстракций."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities import (
    ArticleCandidate,
    Estimate,
    EstimateNode,
    EstimateSummary,
    ExistingArticle,
    ImportPlan,
    NewEstimate,
    StoredEstimateRow,
    TemplateArticle,
    TokenPayload,
    User,
)
from app.domain.errors import StorageError, TokenError
from app.domain.ports import (
    ArticleImportRepository,
    ArticleRepository,
    Embedder,
    EstimateRepository,
    LLMMatcher,
    ObjectStorage,
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
            parent_id=article.parent_id,
            article_code=article.article_code,
            name=article.name,
            embedding_input=article.embedding_input,
            embedding=article.embedding,
        )
        self._store.append(stored)
        return stored

    def get_by_code(self, code: str) -> TemplateArticle | None:
        return next((a for a in self._store if a.article_code == code), None)

    def list_all(self, limit: int = 100, offset: int = 0) -> list[TemplateArticle]:
        return self._store[offset : offset + limit]

    def delete(self, article_id: int) -> None:
        self._store = [a for a in self._store if a.id != article_id]

    def delete_all(self) -> int:
        n = len(self._store)
        self._store = []
        return n

    def has_descendant_codes(self, code: str) -> bool:
        prefix = f"{code}."
        return any(a.article_code.startswith(prefix) for a in self._store)

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


class FakeImportRepository(ArticleImportRepository):
    """In-memory справочник для тестов сервиса импорта.

    rows: code -> TemplateArticle (с id, embedding, embedding_input, parent_id).
    """

    def __init__(self) -> None:
        self.rows: dict[str, TemplateArticle] = {}
        self._next_id = 1

    def load_existing(self) -> list[ExistingArticle]:
        return [
            ExistingArticle(id=a.id, article_code=a.article_code, embedding_input=a.embedding_input)
            for a in self.rows.values()
        ]

    def apply_plan(self, plan: ImportPlan) -> None:
        for code in plan.delete_codes:
            self.rows.pop(code, None)
        for ins in plan.inserts:
            self.rows[ins.article_code] = TemplateArticle(
                id=self._next_id,
                parent_id=None,
                article_code=ins.article_code,
                name=ins.name,
                embedding_input=ins.embedding_input,
                embedding=None,
            )
            self._next_id += 1
        for upd in plan.updates:
            self.rows[upd.article_code] = TemplateArticle(
                id=upd.id,
                parent_id=None,
                article_code=upd.article_code,
                name=upd.name,
                embedding_input=upd.embedding_input,
                embedding=(
                    None if upd.invalidate_embedding else self.rows[upd.article_code].embedding
                ),
            )
        # Фаза 2: резолв parent_id по карте code->id — как в SqlAlchemyArticleImportRepository.
        id_by_code = {a.article_code: a.id for a in self.rows.values()}
        for planned in (*plan.inserts, *plan.updates):
            if planned.parent_code is None:
                continue
            parent_id = id_by_code.get(planned.parent_code)
            if parent_id is None:
                raise ValueError(
                    f"Родитель '{planned.parent_code}' не найден для '{planned.article_code}'"
                )
            current = self.rows[planned.article_code]
            self.rows[planned.article_code] = TemplateArticle(
                id=current.id,
                parent_id=parent_id,
                article_code=current.article_code,
                name=current.name,
                embedding_input=current.embedding_input,
                embedding=current.embedding,
            )

    # помощники для тестов
    def set_embedding(self, code: str, vector: list[float]) -> None:
        a = self.rows[code]
        self.rows[code] = TemplateArticle(
            id=a.id,
            parent_id=a.parent_id,
            article_code=a.article_code,
            name=a.name,
            embedding_input=a.embedding_input,
            embedding=vector,
        )

    def get(self, code: str) -> TemplateArticle:
        return self.rows[code]


class FakeObjectStorage(ObjectStorage):
    def __init__(self, *, fail: bool = False) -> None:
        self.store: dict[str, bytes] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []
        self._fail = fail

    def put(self, key: str, data: bytes, content_type: str) -> None:
        if self._fail:
            raise StorageError("MinIO недоступен")
        self.put_calls.append(key)
        self.store[key] = data

    def get(self, key: str) -> bytes:
        return self.store[key]

    def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.store.pop(key, None)


class FakeEstimateRepository(EstimateRepository):
    def __init__(self) -> None:
        self.estimates: dict[int, Estimate] = {}
        self._keys: dict[int, str] = {}  # estimate_id -> object_key
        self._next = 1
        self.create_calls = 0

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        self.create_calls += 1
        eid = self._next
        self._next += 1
        rows = [
            StoredEstimateRow(
                id=i + 1,
                code=n.code,
                name=n.name,
                parent_code=n.parent_code,
                section_type=n.section_type,
                depth=n.depth,
                embedding_input=n.embedding_input,
                source_index=n.source_index,
                status="pending",
                has_embedding=False,
            )
            for i, n in enumerate(nodes)
        ]
        est = Estimate(
            id=eid,
            user_id=new.user_id,
            filename=new.filename,
            status="pending",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),  # noqa: UP017
            rows=rows,
        )
        self.estimates[eid] = est
        self._keys[eid] = new.original_object_key
        return est

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return [
            EstimateSummary(
                id=e.id,
                filename=e.filename,
                status=e.status,
                nodes_count=len(e.rows),
                created_at=e.created_at,
            )
            for e in self.estimates.values()
            if is_admin or e.user_id == owner_id
        ]

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        return est

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        self.estimates.pop(estimate_id)
        return self._keys.pop(estimate_id)
