"""Интеграционные тесты SqlAlchemyDecisionFundRepository против реального Postgres.

Track 3 (несводимое к фейку): реальный JOIN-живость в lookup, фильтр по
crumb_version, on_conflict_do_update (votes+1/source перезаписан). Гейт —
ПО НАЛИЧИЮ TEST_DATABASE_URL (не opt-in флаг): резолвим из os.environ или
backend/.env (conftest его в env не кладёт) и SKIP, если недоступен.

Изоляция: upsert/clear коммитят внутри репозитория (rollback outer-транзакции
не сработает) — чистим явно в finally по своим sentinel-хешам/id.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.decision_fund import FundEntry
from app.infrastructure.db.decision_fund_repository import SqlAlchemyDecisionFundRepository
from app.infrastructure.db.models import DecisionFundModel, TemplateArticleModel


def _test_db_url() -> str | None:
    val = os.environ.get("TEST_DATABASE_URL")
    if val:
        return val
    env_path = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
    return dotenv_values(env_path).get("TEST_DATABASE_URL")


_TEST_DB_URL = _test_db_url()
_SKIP_REASON = "нужен TEST_DATABASE_URL (backend/.env) — тест-Postgres со схемой 0007"
pytestmark = pytest.mark.skipif(_TEST_DB_URL is None, reason=_SKIP_REASON)


@pytest.fixture()
def session():
    # Свой engine/sessionmaker — общий engine (app.infrastructure.db.session) привязан
    # к заглушке DATABASE_URL из conftest и недостижим.
    engine = create_engine(_TEST_DB_URL, pool_pre_ping=True, future=True)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sess = maker()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _seed_article(session: Session, code: str, name: str) -> int:
    article = TemplateArticleModel(article_code=code, name=name, embedding_input=name)
    session.add(article)
    session.commit()
    return article.id


def _cleanup(session: Session, *, hashes: list[str], article_ids: list[int]) -> None:
    if hashes:
        session.execute(
            sa.delete(DecisionFundModel).where(DecisionFundModel.cache_key_hash.in_(hashes))
        )
    if article_ids:
        session.execute(
            sa.delete(TemplateArticleModel).where(TemplateArticleModel.id.in_(article_ids))
        )
    session.commit()


def test_lookup_returns_only_live_articles(session: Session) -> None:
    live = _seed_article(session, "it_fund_1.4", "Мокап")
    repo = SqlAlchemyDecisionFundRepository(session)
    key_hash = "it_fund_h1"
    try:
        repo.upsert(
            [
                FundEntry(key_hash, "k1", 1, live, 10, 100),
                FundEntry(key_hash, "k1", 1, 999999, 11, 101),  # мёртвый article_id
            ]
        )
        hits = repo.lookup([key_hash], crumb_version=1)
        assert [h.article_id for h in hits[key_hash]] == [live]
        assert hits[key_hash][0].name == "Мокап"
        assert hits[key_hash][0].code == "it_fund_1.4"
    finally:
        _cleanup(session, hashes=[key_hash], article_ids=[live])


def test_lookup_filters_by_version(session: Session) -> None:
    a = _seed_article(session, "it_fund_1.5", "Мокап2")
    repo = SqlAlchemyDecisionFundRepository(session)
    key_hash = "it_fund_h2"
    try:
        repo.upsert([FundEntry(key_hash, "k2", 1, a, 10, 100)])
        assert repo.lookup([key_hash], crumb_version=2) == {}
    finally:
        _cleanup(session, hashes=[key_hash], article_ids=[a])


def test_upsert_increments_votes_and_updates_source(session: Session) -> None:
    a = _seed_article(session, "it_fund_1.6", "Мокап3")
    repo = SqlAlchemyDecisionFundRepository(session)
    key_hash = "it_fund_h3"
    try:
        repo.upsert([FundEntry(key_hash, "k3", 1, a, 10, 100)])
        repo.upsert([FundEntry(key_hash, "k3", 1, a, 22, 222)])  # та же пара, другой источник
        row = session.execute(
            sa.text(
                "SELECT votes, source_estimate_id FROM decision_fund "
                "WHERE cache_key_hash=:h AND crumb_version=1 AND article_id=:a"
            ),
            {"h": key_hash, "a": a},
        ).one()
        assert row.votes == 2 and row.source_estimate_id == 22  # source_* = последний
    finally:
        _cleanup(session, hashes=[key_hash], article_ids=[a])
