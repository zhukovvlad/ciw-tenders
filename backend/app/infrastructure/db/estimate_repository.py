"""SQL-реализация EstimateRepository (Postgres). Создание сметы + узлов в транзакции."""

from __future__ import annotations

from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.orm import Session

from app.domain.entities import (
    ClassifiableNode,
    Estimate,
    EstimateNode,
    EstimateRowStatus,
    EstimateStatus,
    EstimateSummary,
    MatchableNode,
    MatchCandidate,
    NewEstimate,
    NodeClassification,
    NodeMatch,
    PendingEmbedding,
    PendingNode,
    PromotableRow,
    StoredEstimateRow,
)
from app.domain.ports import EstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel

_NS_MATCH = 0x4D415443  # "MATC" — namespace advisory-лока матчинга сметы


class SqlAlchemyEstimateRepository(EstimateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _row_to_entity(m: EstimateRowModel) -> StoredEstimateRow:
        return StoredEstimateRow(
            id=m.id,
            code=m.code,
            name=m.name,
            parent_code=m.parent_code,
            section_type=m.section_type,
            depth=m.depth,
            embedding_input=m.embedding_input,
            source_index=m.source_index,
            status=m.status,
            has_embedding=m.embedding is not None,
            matched_article_id=m.matched_article_id,
            matched_code=m.matched_code,
            matched_name=m.matched_name,
            score=m.score,
            candidates=[
                MatchCandidate(id=c.get("id"), code=c["code"], name=c["name"], score=c["score"])
                for c in (m.candidates or [])
            ],
            review_status=m.review_status,
            final_article_id=m.final_article_id,
            final_code=m.final_code,
            final_name=m.final_name,
            reviewed_at=m.reviewed_at,
        )

    @classmethod
    def _to_entity(cls, m: EstimateModel, rows: list[EstimateRowModel]) -> Estimate:
        return Estimate(
            id=m.id,
            user_id=m.user_id,
            filename=m.filename,
            status=m.status,
            created_at=m.created_at,
            rows=[cls._row_to_entity(r) for r in rows],
            status_detail=m.status_detail,
        )

    def create(self, new: NewEstimate, nodes: list[EstimateNode]) -> Estimate:
        try:
            est = EstimateModel(
                user_id=new.user_id,
                filename=new.filename,
                original_object_key=new.original_object_key,
                status="pending",
            )
            self._session.add(est)
            self._session.flush()  # получить est.id
            row_models = [
                EstimateRowModel(
                    estimate_id=est.id,
                    source_index=n.source_index,
                    code=n.code,
                    name=n.name,
                    parent_code=n.parent_code,
                    section_type=n.section_type,
                    depth=n.depth,
                    embedding_input=n.embedding_input,
                    embedding=None,
                    status="pending",
                )
                for n in nodes
            ]
            self._session.add_all(row_models)
            self._session.commit()
            # SessionLocal: expire_on_commit=False (session.py) — атрибуты не истекают после
            # commit, поэтому _to_entity читает row_models из памяти БЕЗ перезагрузок (нет N+1
            # на 809 строк). Единственный пост-коммит запрос — refresh(est) ради created_at.
            self._session.refresh(est)
            return self._to_entity(est, sorted(row_models, key=lambda r: r.source_index))
        except Exception:
            self._session.rollback()
            raise

    def list_for_owner(self, owner_id: int, *, is_admin: bool) -> list[EstimateSummary]:
        counts = (
            select(
                EstimateRowModel.estimate_id,
                func.count().label("n"),
            )
            .where(EstimateRowModel.status != "excluded")
            .group_by(EstimateRowModel.estimate_id)
            .subquery()
        )
        stmt = select(EstimateModel, func.coalesce(counts.c.n, 0)).outerjoin(
            counts, counts.c.estimate_id == EstimateModel.id
        )
        if not is_admin:
            stmt = stmt.where(EstimateModel.user_id == owner_id)
        stmt = stmt.order_by(EstimateModel.created_at.desc())
        return [
            EstimateSummary(
                id=m.id,
                filename=m.filename,
                status=m.status,
                nodes_count=int(n),
                created_at=m.created_at,
            )
            for m, n in self._session.execute(stmt)
        ]

    def get(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> Estimate | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        rows = list(
            self._session.scalars(
                select(EstimateRowModel)
                .where(EstimateRowModel.estimate_id == estimate_id)
                .order_by(EstimateRowModel.source_index)
            )
        )
        return self._to_entity(est, rows)

    def delete(self, estimate_id: int, requester_id: int, *, is_admin: bool) -> str | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        key = est.original_object_key
        self._session.execute(delete(EstimateModel).where(EstimateModel.id == estimate_id))
        self._session.commit()
        return key

    def try_matching_lock(self, estimate_id: int) -> bool:
        # ИНВАРИАНТ: сессия ДОЛЖНА быть на пиннутом коннекте (SessionLocal(bind=conn) в Celery-
        # обёртке) — иначе commit() в save_*/set_status вернёт коннект в пул, лок утечёт и потеряет
        # эксклюзивность на prefork concurrency>1. Session-level (не xact): переживает коммиты на
        # ОДНОМ коннекте; release_matching_lock + conn.close() в обёртке снимают лок.
        return bool(
            self._session.scalar(select(func.pg_try_advisory_lock(_NS_MATCH, estimate_id)))
        )

    def release_matching_lock(self, estimate_id: int) -> None:
        self._session.scalar(select(func.pg_advisory_unlock(_NS_MATCH, estimate_id)))

    def set_status(
        self, estimate_id: int, status: EstimateStatus, detail: str | None = None
    ) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(
                status=str(status), status_detail=detail, updated_at=func.now()
            )
        )
        self._session.commit()

    def touch(self, estimate_id: int) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(
                updated_at=func.now()
            )
        )
        self._session.commit()

    def get_status(self, estimate_id: int) -> str | None:
        return self._session.scalar(
            select(EstimateModel.status).where(EstimateModel.id == estimate_id)
        )

    def is_stale_running(self, estimate_id: int, max_age_seconds: int) -> bool:
        stmt = select(EstimateModel.id).where(
            EstimateModel.id == estimate_id,
            EstimateModel.status == "running",
            EstimateModel.updated_at
            < func.now() - (text(":age * interval '1 second'").bindparams(age=max_age_seconds)),
        )
        return self._session.scalar(stmt) is not None

    def fetch_unembedded_nodes(
        self, estimate_id: int, after_id: int, limit: int
    ) -> list[PendingEmbedding]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.embedding_input)
            .where(
                EstimateRowModel.estimate_id == estimate_id,
                EstimateRowModel.embedding.is_(None),
                EstimateRowModel.id > after_id,
                EstimateRowModel.status != "excluded",
            )
            .order_by(EstimateRowModel.id)
            .limit(limit)
        )
        return [
            PendingEmbedding(id=r.id, embedding_input=r.embedding_input)
            for r in self._session.execute(stmt)
        ]

    def save_node_embedding(
        self, node_id: int, embedding_input: str, vector: list[float]
    ) -> bool:
        result = self._session.execute(
            update(EstimateRowModel)
            .where(
                EstimateRowModel.id == node_id,
                EstimateRowModel.embedding_input == embedding_input,
            )
            .values(embedding=vector)
        )
        self._session.commit()
        return result.rowcount > 0

    def fetch_matchable_nodes(self, estimate_id: int) -> list[MatchableNode]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.embedding,
                   EstimateRowModel.embedding_input)
            .where(
                EstimateRowModel.estimate_id == estimate_id,
                EstimateRowModel.status.in_(("pending", "error", "no_match")),
                EstimateRowModel.embedding.is_not(None),
                EstimateRowModel.review_status == "unreviewed",
            )
            .order_by(EstimateRowModel.id)
        )
        return [
            MatchableNode(id=r.id, embedding=list(r.embedding), embedding_input=r.embedding_input)
            for r in self._session.execute(stmt)
        ]

    def save_node_match(self, node_id: int, result: NodeMatch) -> None:
        # CAS: пишем AI-снимок только если строку ещё не тронул человек. Закрывает гонку
        # read(matchable)→write с правкой ревью (SP3): нулевой rowcount → решение сохранено.
        self._session.execute(
            update(EstimateRowModel)
            .where(
                EstimateRowModel.id == node_id,
                EstimateRowModel.review_status == "unreviewed",
            )
            .values(**self._match_values(result))
        )
        self._session.commit()

    @staticmethod
    def _match_values(result: NodeMatch) -> dict:
        # перезаписывает ВЕСЬ снимок-набор (на успехе match_error=None → обнуляется)
        return {
            "status": str(result.status),
            "matched_article_id": result.matched_id,
            "matched_code": result.matched_code,
            "matched_name": result.matched_name,
            "score": result.score,
            "candidates": [
                {"id": c.id, "code": c.code, "name": c.name, "score": c.score}
                for c in result.candidates
            ] or None,
            "match_error": result.match_error,
        }

    def save_review_decision(
        self,
        node_id: int,
        *,
        review_status: str,
        final_article_id: int | None,
        final_code: str | None,
        final_name: str | None,
    ) -> None:
        self._session.execute(
            update(EstimateRowModel).where(EstimateRowModel.id == node_id).values(
                review_status=review_status,
                final_article_id=final_article_id,
                final_code=final_code,
                final_name=final_name,
                reviewed_at=func.now(),
            )
        )
        self._session.commit()

    def count_node_errors(self, estimate_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(EstimateRowModel).where(
                    EstimateRowModel.estimate_id == estimate_id,
                    EstimateRowModel.status == "error",
                )
            ) or 0
        )

    def count_unfinished_nodes(self, estimate_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count()).select_from(EstimateRowModel).where(
                    EstimateRowModel.estimate_id == estimate_id,
                    EstimateRowModel.status == "pending",
                )
            ) or 0
        )

    def get_object_key(
        self, estimate_id: int, requester_id: int, *, is_admin: bool
    ) -> str | None:
        est = self._session.get(EstimateModel, estimate_id)
        if est is None or (not is_admin and est.user_id != requester_id):
            return None
        return est.original_object_key

    def fetch_all_nodes(self, estimate_id: int) -> list[ClassifiableNode]:
        stmt = (
            select(EstimateRowModel.id, EstimateRowModel.code, EstimateRowModel.name)
            .where(EstimateRowModel.estimate_id == estimate_id)
            .order_by(EstimateRowModel.source_index)
        )
        return [
            ClassifiableNode(id=r.id, code=r.code, name=r.name)
            for r in self._session.execute(stmt)
        ]

    def save_node_classifications(self, results: list[NodeClassification]) -> None:
        # Охрана: pending/excluded + retryable error/no_match (они матчабельны → орг среди них
        # должен переехать в excluded). Терминальные/ревью-статусы (confident/needs_review/
        # confirmed/overridden) неприкосновенны.
        # Вектор сбрасываем ТОЛЬКО при смене крошки: иначе уже сэмбедженный узел остался бы со
        # старым вектором при новом embedding_input (дрейф на ре-прогоне после флипа вердикта).
        for r in results:
            target = EstimateRowStatus.EXCLUDED if r.excluded else EstimateRowStatus.PENDING
            self._session.execute(
                update(EstimateRowModel)
                .where(
                    EstimateRowModel.id == r.node_id,
                    EstimateRowModel.status.in_(("pending", "excluded", "error", "no_match")),
                )
                .values(
                    status=str(target),
                    embedding_input=r.embedding_input,
                    embedding=case(
                        (EstimateRowModel.embedding_input != r.embedding_input, None),
                        else_=EstimateRowModel.embedding,
                    ),
                )
            )
        self._session.commit()  # один commit на весь проход (атомарность + латентность)

    def set_reference(self, estimate_id: int, value: bool) -> None:
        self._session.execute(
            update(EstimateModel).where(EstimateModel.id == estimate_id).values(is_reference=value)
        )
        self._session.commit()

    def is_reference(self, estimate_id: int) -> bool:
        return bool(
            self._session.scalar(
                select(EstimateModel.is_reference).where(EstimateModel.id == estimate_id)
            )
        )

    def fetch_reference_estimate_ids(self) -> list[int]:
        return list(
            self._session.scalars(
                select(EstimateModel.id).where(EstimateModel.is_reference.is_(True))
            )
        )

    def fetch_promotable_rows(self, estimate_id: int) -> list[PromotableRow]:
        stmt = select(
            EstimateRowModel.id, EstimateRowModel.embedding_input,
            EstimateRowModel.status, EstimateRowModel.review_status,
            EstimateRowModel.final_article_id,
        ).where(EstimateRowModel.estimate_id == estimate_id)
        return [
            PromotableRow(r.id, r.embedding_input, r.status, r.review_status, r.final_article_id)
            for r in self._session.execute(stmt)
        ]

    def fetch_pending_nodes(self, estimate_id: int) -> list[PendingNode]:
        stmt = select(EstimateRowModel.id, EstimateRowModel.embedding_input).where(
            EstimateRowModel.estimate_id == estimate_id,
            EstimateRowModel.status == "pending",
            EstimateRowModel.review_status == "unreviewed",  # защитный: pending ⟹ unreviewed
        )
        return [PendingNode(r.id, r.embedding_input) for r in self._session.execute(stmt)]

    def save_fund_hit(self, node_id: int, article_id: int, code: str, name: str) -> None:
        # CAS по unreviewed — как save_node_match; candidates/score обнуляем (снимок без кандидатов)
        self._session.execute(
            update(EstimateRowModel)
            .where(EstimateRowModel.id == node_id, EstimateRowModel.review_status == "unreviewed")
            .values(status="matched_fund", matched_article_id=article_id,
                    matched_code=code, matched_name=name, candidates=None, score=None,
                    match_error=None)
        )
        self._session.commit()
