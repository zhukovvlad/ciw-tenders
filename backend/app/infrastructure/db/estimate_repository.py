"""SQL-реализация EstimateRepository (Postgres). Создание сметы + узлов в транзакции."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.domain.entities import (
    Estimate,
    EstimateNode,
    EstimateSummary,
    NewEstimate,
    StoredEstimateRow,
)
from app.domain.ports import EstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel


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
