from __future__ import annotations

import os

import pytest

from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.session import SessionLocal, engine

_REAL_DB = os.environ.get("DATABASE_URL", "").startswith(("postgresql", "postgres"))


@pytest.mark.skipif(not _REAL_DB, reason="нужен реальный Postgres (advisory-lock не фейкается)")
def test_advisory_lock_is_exclusive_across_connections() -> None:
    c1, c2 = engine.connect(), engine.connect()
    try:
        r1 = SqlAlchemyEstimateRepository(SessionLocal(bind=c1))
        r2 = SqlAlchemyEstimateRepository(SessionLocal(bind=c2))
        assert r1.try_matching_lock(424242) is True
        r1.touch(424242)  # коммит на c1 (UPDATE по несущ. строке тоже коммитит) НЕ должен снять лок
        assert r2.try_matching_lock(424242) is False   # эксклюзивность держится ПОСЛЕ коммита
        r1.release_matching_lock(424242)
        assert r2.try_matching_lock(424242) is True
        r2.release_matching_lock(424242)
    finally:
        c1.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        c2.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        c1.close()
        c2.close()
