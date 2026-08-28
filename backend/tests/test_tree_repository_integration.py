"""Интеграционные тесты tree-методов SqlAlchemyEstimateRepository/SqlAlchemyArticleRepository
против реального Postgres.

Track 3 (несводимое к фейку): реальный SQL-предикат save_node_match_cas (status IN expected AND
review_status='unreviewed'), честная колонка-only проекция fetch_tree/refresh_tree_node (без
identity-map кэша сессии) и list_catalog через parent_id-JOIN, а не строковый сплит кода (как в
фейках — расхождение сознательное, см. план). Гейт и изоляция — как в
test_decision_fund_repository_integration.py / test_estimate_repository_fund_integration.py:
skip без TEST_DATABASE_URL; чистка в finally.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.entities import EstimateRowStatus, NodeMatch
from app.infrastructure.db.article_repository import SqlAlchemyArticleRepository
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import (
    EstimateModel,
    EstimateRowModel,
    TemplateArticleModel,
    UserModel,
)


def _test_db_url() -> str | None:
    val = os.environ.get("TEST_DATABASE_URL")
    if val:
        return val
    env_path = Path(__file__).resolve().parents[1] / ".env"  # backend/.env
    return dotenv_values(env_path).get("TEST_DATABASE_URL")


_TEST_DB_URL = _test_db_url()
_SKIP_REASON = "нужен TEST_DATABASE_URL (backend/.env) — тест-Postgres со схемой alembic head"
pytestmark = pytest.mark.skipif(_TEST_DB_URL is None, reason=_SKIP_REASON)

_SENTINEL_EMAIL = "it_tree_repo@test.local"
# ЧИСЛОВОЙ префикс: list_catalog сортирует ВЕСЬ справочник через
# string_to_array(code,'.')::int[] (_CODE_ORDER) — нечисловой сегмент кода уронит запрос для
# всей таблицы, а не только для тестовых строк.
_SENTINEL_CODE_PREFIX = "999888"


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


def _cleanup_estimate(session: Session) -> None:
    # estimates/estimate_rows уходят каскадом (ondelete=CASCADE от users → estimates → rows)
    session.execute(sa.delete(UserModel).where(UserModel.email == _SENTINEL_EMAIL))
    session.commit()


def _cleanup_articles(session: Session) -> None:
    session.execute(
        sa.delete(TemplateArticleModel).where(
            TemplateArticleModel.article_code.like(f"{_SENTINEL_CODE_PREFIX}%")
        )
    )
    session.commit()


def test_fetch_tree_orders_by_source_index(session: Session) -> None:
    repo = SqlAlchemyEstimateRepository(session)
    try:
        uid = _seed_user(session)
        eid = _seed_estimate(session, uid, "tree.xlsx")
        # сидируем в обратном порядке — fetch_tree обязан переупорядочить по source_index,
        # а не по порядку вставки/id
        r2 = _seed_row(session, eid, 1, code="1.1", name="Подраздел", depth=2)
        r1 = _seed_row(session, eid, 0, code="1", name="Раздел", depth=1)

        tree = repo.fetch_tree(eid)

        assert [n.id for n in tree] == [r1, r2]
        assert [n.code for n in tree] == ["1", "1.1"]
        assert tree[0].depth == 1 and tree[1].depth == 2
        assert tree[0].name == "Раздел" and tree[0].status == "pending"
        assert tree[0].review_status == "unreviewed"
    finally:
        _cleanup_estimate(session)


def test_save_node_match_cas_and_refresh_after_review(session: Session) -> None:
    repo = SqlAlchemyEstimateRepository(session)
    try:
        uid = _seed_user(session)
        eid = _seed_estimate(session, uid, "cas.xlsx")
        rid = _seed_row(session, eid, 0, code="1", depth=1, status="pending")
        result = NodeMatch(
            EstimateRowStatus.CONFIDENT, matched_id=1, matched_code="1", matched_name="x"
        )

        assert repo.save_node_match_cas(rid, result, ("pending",)) is True
        assert repo.save_node_match_cas(rid, result, ("pending",)) is False  # уже confident
        assert repo.save_node_match_cas(rid, result, ("pending", "confident")) is True

        # ревью оператора — CAS больше не проходит НИ ПРИ КАКОМ expected_statuses
        repo.save_review_decision(
            rid, review_status="overridden", final_article_id=9, final_code="9", final_name="z"
        )
        assert repo.save_node_match_cas(rid, result, ("confident",)) is False

        # refresh_tree_node обязан увидеть чужой (ревью) коммит — не кэш сессии
        fresh = repo.refresh_tree_node(rid)
        assert fresh.review_status == "overridden"
        assert fresh.final_article_id == 9 and fresh.final_code == "9"

        with pytest.raises(KeyError):
            repo.refresh_tree_node(-1)
    finally:
        _cleanup_estimate(session)


def test_list_catalog_resolves_parent_code_via_parent_id(session: Session) -> None:
    repo = SqlAlchemyArticleRepository(session)
    try:
        parent = TemplateArticleModel(
            article_code=_SENTINEL_CODE_PREFIX, name="Родитель", embedding_input="р",
        )
        session.add(parent)
        session.commit()
        child = TemplateArticleModel(
            article_code=f"{_SENTINEL_CODE_PREFIX}.1", name="Дочка", embedding_input="д",
            parent_id=parent.id,
        )
        session.add(child)
        session.commit()

        catalog = {
            a.code: a for a in repo.list_catalog() if a.code.startswith(_SENTINEL_CODE_PREFIX)
        }

        assert catalog[_SENTINEL_CODE_PREFIX].parent_code is None
        assert catalog[f"{_SENTINEL_CODE_PREFIX}.1"].parent_code == _SENTINEL_CODE_PREFIX
        assert catalog[f"{_SENTINEL_CODE_PREFIX}.1"].name == "Дочка"
    finally:
        _cleanup_articles(session)
