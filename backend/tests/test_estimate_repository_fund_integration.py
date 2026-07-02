"""Интеграционные тесты fund-методов SqlAlchemyEstimateRepository против реального Postgres.

Ревью PR #17 (CodeRabbit, 2026-07-02): фейк-зеркало (test_estimate_fund_methods.py) не ловит
регрессы SQL-предикатов/проекций — гоняем реальные is_reference / fetch_reference_estimate_ids /
fetch_promotable_rows / exists / fetch_pending_nodes / save_fund_hits. Гейт и изоляция — как в
test_decision_fund_repository_integration.py: skip без TEST_DATABASE_URL; чистка в finally
через DELETE sentinel-пользователя (estimates/rows уходят по ondelete=CASCADE).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.decision_fund import AppliedFundHit
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel, UserModel


def _test_db_url() -> str | None:
    val = os.environ.get("TEST_DATABASE_URL")
    if val:
        return val
    env_path = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
    return dotenv_values(env_path).get("TEST_DATABASE_URL")


_TEST_DB_URL = _test_db_url()
_SKIP_REASON = "нужен TEST_DATABASE_URL (backend/.env) — тест-Postgres со схемой 0007"
pytestmark = pytest.mark.skipif(_TEST_DB_URL is None, reason=_SKIP_REASON)

_SENTINEL_EMAIL = "it_estimate_fund@test.local"


@pytest.fixture()
def session():
    engine = create_engine(_TEST_DB_URL, pool_pre_ping=True, future=True)
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sess = maker()
    try:
        yield sess
    finally:
        sess.close()
        engine.dispose()


def _seed_user(session: Session) -> int:
    user = UserModel(email=_SENTINEL_EMAIL, password_hash="x")
    session.add(user)
    session.commit()
    return user.id


def _seed_estimate(session: Session, user_id: int, filename: str) -> int:
    est = EstimateModel(user_id=user_id, filename=filename, original_object_key=f"it/{filename}")
    session.add(est)
    session.commit()
    return est.id


def _seed_row(session: Session, estimate_id: int, source_index: int, **overrides) -> int:
    fields = {
        "estimate_id": estimate_id, "source_index": source_index,
        "code": f"1.{source_index}", "name": f"строка {source_index}",
        "parent_code": None, "section_type": None, "depth": 2,
        "embedding_input": f"крошка {source_index}",
    }
    fields.update(overrides)
    row = EstimateRowModel(**fields)
    session.add(row)
    session.commit()
    return row.id


def _cleanup(session: Session) -> None:
    # estimates/estimate_rows уходят каскадом (ondelete=CASCADE от users → estimates → rows)
    session.execute(sa.delete(UserModel).where(UserModel.email == _SENTINEL_EMAIL))
    session.commit()


def test_exists_reference_flag_and_ids(session: Session) -> None:
    repo = SqlAlchemyEstimateRepository(session)
    try:
        uid = _seed_user(session)
        e1 = _seed_estimate(session, uid, "a.xlsx")
        e2 = _seed_estimate(session, uid, "b.xlsx")

        # exists: владелец / чужой / админ / несуществующая
        assert repo.exists(e1, uid, is_admin=False) is True
        assert repo.exists(e1, uid + 1, is_admin=False) is False
        assert repo.exists(e1, uid + 1, is_admin=True) is True
        assert repo.exists(-1, uid, is_admin=True) is False

        # set_reference/is_reference/fetch_reference_estimate_ids (containment: БД общая)
        repo.set_reference(e1, True)
        assert repo.is_reference(e1) is True and repo.is_reference(e2) is False
        ids = repo.fetch_reference_estimate_ids()
        assert e1 in ids and e2 not in ids
        repo.set_reference(e1, False)
        assert repo.is_reference(e1) is False
        assert e1 not in repo.fetch_reference_estimate_ids()
    finally:
        _cleanup(session)


def test_pending_promotable_and_save_fund_hits(session: Session) -> None:
    repo = SqlAlchemyEstimateRepository(session)
    try:
        uid = _seed_user(session)
        eid = _seed_estimate(session, uid, "c.xlsx")
        r_pending = _seed_row(session, eid, 0)  # pending/unreviewed → кандидат фонда
        r_reviewed = _seed_row(  # человек уже решил → не pending-кандидат, но promotable
            session, eid, 1, status="needs_review", review_status="confirmed",
            final_article_id=77, final_code="7.7", final_name="Финал",
        )
        r_confident = _seed_row(session, eid, 2, status="confident")  # не pending-кандидат

        # fetch_pending_nodes: строго pending + unreviewed
        pend = repo.fetch_pending_nodes(eid)
        assert [p.row_id for p in pend] == [r_pending]
        assert pend[0].embedding_input == "крошка 0"

        # fetch_promotable_rows: все строки со статусами/финалами (предикат — в сервисе)
        by_id = {r.row_id: r for r in repo.fetch_promotable_rows(eid)}
        assert set(by_id) == {r_pending, r_reviewed, r_confident}
        assert by_id[r_reviewed].review_status == "confirmed"
        assert by_id[r_reviewed].final_article_id == 77
        assert by_id[r_confident].status == "confident"

        # save_fund_hits: снимок на unreviewed, CAS не даёт затереть решение человека
        repo.save_fund_hits([
            AppliedFundHit(r_pending, article_id=5, code="1.4", name="Мокап"),
            AppliedFundHit(r_reviewed, article_id=5, code="1.4", name="Мокап"),
        ])
        rows = {
            r.id: r
            for r in session.scalars(
                sa.select(EstimateRowModel).where(EstimateRowModel.estimate_id == eid)
            )
        }
        hit = rows[r_pending]
        assert hit.status == "matched_fund" and hit.matched_article_id == 5
        assert hit.matched_code == "1.4" and hit.matched_name == "Мокап"
        assert hit.candidates is None and hit.score is None and hit.match_error is None
        assert rows[r_reviewed].status == "needs_review"  # CAS по unreviewed сработал
    finally:
        _cleanup(session)
