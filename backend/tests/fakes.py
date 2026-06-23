"""Тестовые дублёры портов (in-memory). Подтверждают, что сервисы зависят от абстракций."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities import (
    ArticleCandidate,
    Estimate,
    EstimateNode,
    EstimateStatus,
    EstimateSummary,
    ExistingArticle,
    ImportPlan,
    MatchableNode,
    MatchCandidate,
    NewEstimate,
    NodeMatch,
    PendingEmbedding,
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
    TaskQueue,
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

    def matching_readiness(self) -> tuple[int, int]:
        total = len(self._store)
        pending = sum(1 for a in self._store if a.embedding is None)
        return total, pending


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


class FakeTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self.match_calls: list[int] = []
        self.articles_embed_calls = 0

    def enqueue_match(self, estimate_id: int) -> None:
        self.match_calls.append(estimate_id)

    def enqueue_articles_embed(self) -> None:
        self.articles_embed_calls += 1


class FakeEstimateRepository(EstimateRepository):
    def __init__(self) -> None:
        self.estimates: dict[int, Estimate] = {}
        self._keys: dict[int, str] = {}
        self._next = 1
        self.create_calls = 0
        # SP2: узлы как изменяемые словари + статус/детали/лок/таймстамп
        self.nodes: dict[int, dict] = {}  # node_id -> {estimate_id, embedding_input, ...}
        self.statuses: dict[int, str] = {}  # estimate_id -> status
        self.details: dict[int, str | None] = {}
        self.touch_count: dict[int, int] = {}
        self._locks: set[int] = set()
        self._node_seq = 0

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        self.create_calls += 1
        eid = self._next
        self._next += 1
        rows = []
        for n in nodes:
            self._node_seq += 1
            nid = self._node_seq
            self.nodes[nid] = {
                "id": nid,
                "estimate_id": eid,
                "embedding_input": n.embedding_input,
                "embedding": None,
                "status": "pending",
                "match_error": None,
                "matched_article_id": None,
                "matched_code": None,
                "matched_name": None,
                "score": None,
                "candidates": [],
                "review_status": "unreviewed",
                "final_article_id": None,
                "final_code": None,
                "final_name": None,
                "reviewed_at": None,
            }
            rows.append(
                StoredEstimateRow(
                    id=nid,
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
            )
        est = Estimate(
            id=eid,
            user_id=new.user_id,
            filename=new.filename,
            status="pending",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),  # noqa: UP017
            rows=rows,
        )
        self.estimates[eid] = est
        self.statuses[eid] = "pending"
        self.details[eid] = None
        self.touch_count[eid] = 0
        self._keys[eid] = new.original_object_key
        return est

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        return [
            EstimateSummary(
                id=e.id,
                filename=e.filename,
                status=self.statuses.get(e.id, e.status),
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
        rows = [self._row_entity(r, self.nodes[r.id]) for r in est.rows]
        return Estimate(
            id=est.id, user_id=est.user_id, filename=est.filename,
            status=self.statuses.get(est.id, est.status),
            created_at=est.created_at, rows=rows,
            status_detail=self.details.get(est.id),
        )

    @staticmethod
    def _row_entity(base: StoredEstimateRow, n: dict) -> StoredEstimateRow:
        return StoredEstimateRow(
            id=base.id, code=base.code, name=base.name, parent_code=base.parent_code,
            section_type=base.section_type, depth=base.depth,
            embedding_input=base.embedding_input, source_index=base.source_index,
            status=n["status"], has_embedding=n["embedding"] is not None,
            matched_article_id=n["matched_article_id"], matched_code=n["matched_code"],
            matched_name=n["matched_name"], score=n["score"],
            candidates=[
                MatchCandidate(id=c.get("id"), code=c["code"], name=c["name"], score=c["score"])
                for c in n["candidates"]
            ],
            review_status=n["review_status"], final_article_id=n["final_article_id"],
            final_code=n["final_code"], final_name=n["final_name"],
            reviewed_at=n["reviewed_at"],
        )

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        est = self.estimates.get(estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        self.estimates.pop(estimate_id)
        return self._keys.pop(estimate_id)

    # --- SP2 ---
    def try_matching_lock(self, estimate_id: int) -> bool:
        if estimate_id in self._locks:
            return False
        self._locks.add(estimate_id)
        return True

    def release_matching_lock(self, estimate_id: int) -> None:
        self._locks.discard(estimate_id)

    def set_status(
        self, estimate_id: int, status: EstimateStatus, detail: str | None = None
    ) -> None:
        self.statuses[estimate_id] = str(status)
        self.details[estimate_id] = detail
        self.touch_count[estimate_id] = self.touch_count.get(estimate_id, 0) + 1

    def touch(self, estimate_id: int) -> None:
        self.touch_count[estimate_id] = self.touch_count.get(estimate_id, 0) + 1

    def get_status(self, estimate_id: int) -> str | None:
        return self.statuses.get(estimate_id)

    def fetch_unembedded_nodes(
        self, estimate_id: int, after_id: int, limit: int
    ) -> list[PendingEmbedding]:
        rows = sorted(
            (
                n
                for n in self.nodes.values()
                if n["estimate_id"] == estimate_id
                and n["embedding"] is None
                and n["id"] > after_id
            ),
            key=lambda n: n["id"],
        )
        return [
            PendingEmbedding(id=n["id"], embedding_input=n["embedding_input"])
            for n in rows[:limit]
        ]

    def save_node_embedding(self, node_id: int, embedding_input: str, vector: list[float]) -> bool:
        n = self.nodes.get(node_id)
        if n is None or n["embedding_input"] != embedding_input:
            return False
        n["embedding"] = vector
        return True

    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        return [
            MatchableNode(
                id=n["id"], embedding=n["embedding"], embedding_input=n["embedding_input"]
            )
            for n in sorted(self.nodes.values(), key=lambda n: n["id"])
            if n["estimate_id"] == estimate_id
            and n["status"] in ("pending", "error", "no_match")
            and n["embedding"] is not None
            and n["review_status"] == "unreviewed"
        ]

    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        n = self.nodes[node_id]
        if n["review_status"] != "unreviewed":
            return  # CAS: человек тронул строку — AI-снимок не затирает решение
        n["status"] = str(result.status)
        n["match_error"] = result.match_error
        n["matched_article_id"] = result.matched_id
        n["matched_code"] = result.matched_code
        n["matched_name"] = result.matched_name
        n["score"] = result.score
        n["candidates"] = [
            {"id": c.id, "code": c.code, "name": c.name, "score": c.score}
            for c in result.candidates
        ]

    def count_node_errors(self, estimate_id: int) -> int:
        return sum(
            1
            for n in self.nodes.values()
            if n["estimate_id"] == estimate_id and n["status"] == "error"
        )

    def count_unfinished_nodes(self, estimate_id: int) -> int:
        return sum(
            1
            for n in self.nodes.values()
            if n["estimate_id"] == estimate_id and n["status"] == "pending"
        )
