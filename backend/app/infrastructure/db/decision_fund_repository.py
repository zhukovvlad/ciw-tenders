"""SQL-адаптер золотого фонда. Lookup фильтрует живые статьи JOIN-ом к каталогу (домен чист)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.decision_fund import FundEntry, FundHit
from app.infrastructure.db.models import DecisionFundModel, TemplateArticleModel


class SqlAlchemyDecisionFundRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(
        self, key_hashes: Sequence[str], crumb_version: int
    ) -> dict[str, list[FundHit]]:
        if not key_hashes:
            return {}
        stmt = (
            select(
                DecisionFundModel.cache_key_hash,
                TemplateArticleModel.id,
                TemplateArticleModel.article_code,
                TemplateArticleModel.name,
            )
            .join(TemplateArticleModel, TemplateArticleModel.id == DecisionFundModel.article_id)
            .where(
                DecisionFundModel.cache_key_hash.in_(list(key_hashes)),
                DecisionFundModel.crumb_version == crumb_version,
            )
        )
        out: dict[str, list[FundHit]] = {}
        for r in self._session.execute(stmt):
            out.setdefault(r.cache_key_hash, []).append(
                FundHit(article_id=r.id, code=r.article_code, name=r.name)
            )
        return out

    def upsert(self, entries: Sequence[FundEntry]) -> None:
        if not entries:
            return
        stmt = (
            pg_insert(DecisionFundModel)
            .values([
                {
                    "cache_key_hash": e.cache_key_hash, "cache_key": e.cache_key,
                    "crumb_version": e.crumb_version, "article_id": e.article_id,
                    "source_estimate_id": e.source_estimate_id, "source_row_id": e.source_row_id,
                }
                for e in entries
            ])
            .on_conflict_do_update(
                constraint="uq_decision_fund_key_version_article",
                set_={
                    "votes": DecisionFundModel.votes + 1,
                    "source_estimate_id": pg_insert(DecisionFundModel).excluded.source_estimate_id,
                    "source_row_id": pg_insert(DecisionFundModel).excluded.source_row_id,
                    "updated_at": text("now()"),
                },
            )
        )
        self._session.execute(stmt)
        self._session.commit()  # один commit на весь промоушен (атомарность + латентность)

    def clear(self) -> None:
        self._session.execute(delete(DecisionFundModel))
        self._session.commit()
