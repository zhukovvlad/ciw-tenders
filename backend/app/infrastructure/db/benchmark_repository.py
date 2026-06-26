"""SqlAlchemy-репозиторий бенчмарков (gold-разметка). Маппинг seed↔ORM локализован тут."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import BenchmarkNodeSeed
from app.domain.ports import BenchmarkRepository
from app.infrastructure.db.models import BenchmarkModel, BenchmarkNodeModel


def seed_to_model(seed: BenchmarkNodeSeed, benchmark_id: int) -> BenchmarkNodeModel:
    return BenchmarkNodeModel(
        benchmark_id=benchmark_id,
        source_index=seed.source_index,
        code=seed.code,
        name=seed.name,
        expected_kind=seed.expected_kind,
        expected_article_code=seed.expected_article_code,
        expected_article_name=seed.expected_article_name,
    )


def model_to_seed(m: BenchmarkNodeModel) -> BenchmarkNodeSeed:
    return BenchmarkNodeSeed(
        code=m.code,
        name=m.name,
        source_index=m.source_index,
        expected_kind=m.expected_kind,
        expected_article_code=m.expected_article_code,
        expected_article_name=m.expected_article_name,
    )


class SqlAlchemyBenchmarkRepository(BenchmarkRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, nodes: list[BenchmarkNodeSeed]) -> int:
        try:
            bench = BenchmarkModel(name=name)
            self._session.add(bench)
            self._session.flush()  # bench.id
            self._session.add_all([seed_to_model(n, bench.id) for n in nodes])
            self._session.commit()
            return bench.id
        except Exception:
            self._session.rollback()
            raise

    def get_by_name(self, name: str) -> int | None:
        return self._session.execute(
            select(BenchmarkModel.id).where(BenchmarkModel.name == name)
        ).scalar_one_or_none()

    def list_benchmarks(self) -> list[tuple[int, str]]:
        rows = self._session.execute(
            select(BenchmarkModel.id, BenchmarkModel.name).order_by(BenchmarkModel.id)
        ).all()
        return [(r[0], r[1]) for r in rows]

    def fetch_nodes(self, benchmark_id: int) -> list[BenchmarkNodeSeed]:
        rows = self._session.execute(
            select(BenchmarkNodeModel)
            .where(BenchmarkNodeModel.benchmark_id == benchmark_id)
            .order_by(BenchmarkNodeModel.source_index)
        ).scalars().all()
        return [model_to_seed(m) for m in rows]
