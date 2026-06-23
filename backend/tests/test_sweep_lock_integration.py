from __future__ import annotations

import os

import pytest

from app.api.deps import sweep_stale_running
from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.session import SessionLocal, engine

_RUN = os.environ.get("RUN_LOCK_INTEGRATION") == "1"
_SKIP = "нужен реальный Postgres: RUN_LOCK_INTEGRATION=1 + реальный DATABASE_URL"

_EID = 990_001
_UID = 990_001


def _setup_stale_running() -> None:
    # sweep трогает только таблицу estimates (advisory-лок — без таблиц). Нужна строка users
    # (FK estimates.user_id) + застрявшая running-смета (updated_at в прошлом). psycopg3 →
    # pyformat-параметры (%(name)s) в exec_driver_sql.
    conn = engine.connect()
    try:
        # идемпотентно: чистим остаток упавшего ранее прогона, иначе ON CONFLICT оставил бы
        # status='pending' от прошлого sweep → is_stale=False → assert ... is True упал бы.
        conn.exec_driver_sql("DELETE FROM estimates WHERE id = %(eid)s", {"eid": _EID})
        conn.exec_driver_sql(
            "INSERT INTO users(id, email, password_hash, role, is_active) "
            "VALUES (%(uid)s, %(email)s, 'x', 'user', true) ON CONFLICT (id) DO NOTHING",
            {"uid": _UID, "email": f"sweep-{_UID}@test.local"},
        )
        conn.exec_driver_sql(
            "INSERT INTO estimates(id, user_id, filename, original_object_key, status, "
            "created_at, updated_at) VALUES (%(eid)s, %(uid)s, 'f.xlsx', 'k', 'running', "
            "now(), now() - interval '1 hour')",
            {"eid": _EID, "uid": _UID},
        )
        conn.commit()
    finally:
        conn.close()


def _teardown() -> None:
    conn = engine.connect()
    try:
        conn.exec_driver_sql("DELETE FROM estimates WHERE id = %(eid)s", {"eid": _EID})
        conn.exec_driver_sql("DELETE FROM users WHERE id = %(uid)s", {"uid": _UID})
        conn.commit()
        conn.exec_driver_sql("SELECT pg_advisory_unlock_all()")
    finally:
        conn.close()


@pytest.mark.skipif(not _RUN, reason=_SKIP)
def test_sweep_resets_stale_running_and_releases_lock() -> None:
    # ПОЛНЫЙ сценарий: критическая секция try_lock → set_status(COMMIT) → release ДОЛЖНА
    # исполниться. На багованной версии (sweep на пуловой сессии / без bind=conn) release
    # ушёл бы на сменившийся коннект → лок остался бы занят → probe.try_lock=False → падёж.
    _setup_stale_running()
    try:
        assert sweep_stale_running(_EID, max_age_seconds=60) is True  # лок взят, pending, release
        probe = engine.connect()
        try:
            r = SqlAlchemyEstimateRepository(SessionLocal(bind=probe))
            assert r.try_matching_lock(_EID) is True   # лок СВОБОДЕН → release сработал
            r.release_matching_lock(_EID)
            assert r.get_status(_EID) == "pending"     # set_status закоммичен
        finally:
            probe.exec_driver_sql("SELECT pg_advisory_unlock_all()")
            probe.close()
    finally:
        _teardown()


@pytest.mark.skipif(not _RUN, reason=_SKIP)
def test_sweep_noop_does_not_strand_lock() -> None:
    # вторичный: на несуществующей смете is_stale=False → лок НЕ берётся, ничего не застревает.
    assert sweep_stale_running(999_999, max_age_seconds=0) is False
    probe = engine.connect()
    try:
        r = SqlAlchemyEstimateRepository(SessionLocal(bind=probe))
        assert r.try_matching_lock(999_999) is True
        r.release_matching_lock(999_999)
    finally:
        probe.exec_driver_sql("SELECT pg_advisory_unlock_all()")
        probe.close()
