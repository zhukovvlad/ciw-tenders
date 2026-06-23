from __future__ import annotations

import os

import pytest

from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.session import SessionLocal, engine

# Opt-in: requires a REAL reachable Postgres. conftest sets a FAKE DATABASE_URL
# (postgresql+psycopg://test:test@localhost/test) that is unreachable, so gating on
# DATABASE_URL alone would make this test FAIL (ConnectionTimeout) instead of skip.
# Run deliberately:
#   RUN_LOCK_INTEGRATION=1 DATABASE_URL=<real-postgres> uv run pytest \
#       tests/test_estimate_lock_integration.py
_RUN_INTEGRATION = os.environ.get("RUN_LOCK_INTEGRATION") == "1"

_SKIP_REASON = "нужен реальный Postgres: RUN_LOCK_INTEGRATION=1 + реальный DATABASE_URL"


@pytest.mark.skipif(not _RUN_INTEGRATION, reason=_SKIP_REASON)
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
