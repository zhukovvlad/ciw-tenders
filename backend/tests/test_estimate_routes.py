from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import replace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_current_user,
    get_decision_fund_service,
    get_estimate_repository,
    get_estimate_service,
    get_settings,
)
from app.core.config import Settings
from app.domain.entities import Role, User
from app.main import app
from app.services.decision_fund_service import DecisionFundService
from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService
from tests.fakes import (
    FakeDecisionFundRepository,
    FakeEstimateRepository,
    FakeObjectStorage,
    FakeTaskQueue,
    Row,
    seed_estimate_with_rows,
)

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(autouse=True)
def _clear_overrides():
    # teardown-чистка: изоляция НЕ зависит от того, дошёл ли тест до конца
    # (инлайн-clear после упавшего ассерта протекал бы в следующий тест).
    yield
    app.dependency_overrides.clear()


def _xlsx() -> bytes:
    df = pd.DataFrame(
        [("1", "Раздел", "СМР"), ("1.1", "Под", None), (None, "Позиция", None)],
        columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _user(uid: int = 2, role: Role = Role.USER) -> Callable[[], User]:
    return lambda: User(id=uid, email=f"u{uid}@mr.kz", password_hash="h", role=role)


def _svc_factory(repo: FakeEstimateRepository, storage: FakeObjectStorage):
    def _f() -> EstimateService:
        return EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue())

    return _f


_DEFAULT_USER = _user()


def _client(repo, storage, fund=None, user=_DEFAULT_USER) -> TestClient:
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_estimate_service] = _svc_factory(repo, storage)
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    if fund is not None:
        app.dependency_overrides[get_decision_fund_service] = lambda: DecisionFundService(
            repo, fund
        )
    return TestClient(app)


def _seed_reviewed(repo: FakeEstimateRepository) -> int:
    """Смета с одной confirmed-строкой владельца id=2 — готова к промоушену в фонд."""
    eid = seed_estimate_with_rows(
        repo, [Row("образец работы", "needs_review", "confirmed", final_article_id=5)]
    )
    est = repo.estimates[eid]
    repo.estimates[eid] = replace(est, user_id=2)
    return eid


def test_upload_creates_estimate() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 201
    body = resp.json()
    assert body["nodes_count"] == 2 and body["positions_count"] == 1
    assert len(storage.put_calls) == 1


def test_upload_rejects_bad_extension_without_storage() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post(
        "/api/estimates", files={"file": ("смета.txt", b"PK\x03\x04xx", "text/plain")}
    )
    assert resp.status_code == 422
    assert storage.put_calls == [] and repo.create_calls == 0


def test_upload_rejects_bad_signature() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", b"not a zip", _XLSX)})
    assert resp.status_code == 422
    assert storage.put_calls == []


def test_upload_rejects_oversize() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    app.dependency_overrides[get_settings] = lambda: Settings(estimate_max_upload_mb=0.0001)
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 413
    assert storage.put_calls == []


def test_upload_missing_column_422_without_storage() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    bad = io.BytesIO()
    pd.DataFrame({"X": [1]}).to_excel(bad, index=False, engine="openpyxl")
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", bad.getvalue(), _XLSX)})
    assert resp.status_code == 422
    assert storage.put_calls == []  # парс падает до put


def test_upload_storage_unavailable_503() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage(fail=True)
    client = _client(repo, storage)
    resp = client.post("/api/estimates", files={"file": ("смета.xlsx", _xlsx(), _XLSX)})
    assert resp.status_code == 503
    assert repo.create_calls == 0


def test_list_and_get_ownership() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2
    )
    client = _client(repo, storage)  # user id=2
    assert len(client.get("/api/estimates").json()) == 1
    other = _client(repo, storage, user=_user(uid=9))  # чужой
    assert other.get("/api/estimates/1").status_code == 404


def test_delete_removes_object() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2
    )
    client = _client(repo, storage)
    resp = client.delete("/api/estimates/1")
    assert resp.status_code == 204
    assert storage.delete_calls  # объект MinIO удалён


def test_requires_auth() -> None:
    client = TestClient(app)
    assert client.get("/api/estimates").status_code == 401


def test_retrigger_match_enqueues_for_owner() -> None:
    from app.api.deps import get_estimate_repository, get_task_queue
    from tests.fakes import FakeTaskQueue

    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2)
    queue = FakeTaskQueue()
    app.dependency_overrides[get_current_user] = _user(uid=2)
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    app.dependency_overrides[get_task_queue] = lambda: queue
    client = TestClient(app)
    resp = client.post("/api/estimates/1/match")
    assert resp.status_code == 202 and queue.match_calls == [1]


def test_retrigger_foreign_estimate_404() -> None:
    from app.api.deps import get_estimate_repository, get_task_queue
    from tests.fakes import FakeTaskQueue

    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    EstimateService(EstimateParser(), repo, storage, task_queue=FakeTaskQueue()).ingest(
        _xlsx(), "a.xlsx", owner_id=2)
    app.dependency_overrides[get_current_user] = _user(uid=9)  # чужой
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    app.dependency_overrides[get_task_queue] = lambda: FakeTaskQueue()
    client = TestClient(app)
    assert client.post("/api/estimates/1/match").status_code == 404


def test_old_match_route_removed() -> None:
    app.dependency_overrides[get_current_user] = _user()
    client = TestClient(app)
    resp = client.post("/api/estimates/match", files={"file": ("a.xlsx", _xlsx(), _XLSX)})
    # FastAPI совпадает с /{estimate_id} и отдаёт 405 (нет POST для этого паттерна) —
    # оба кода (404/405) подтверждают, что синхронный stateless-матч снят.
    assert resp.status_code in (404, 405, 422)


def _xlsx_rows(rows: list[tuple[object, object, object]]) -> bytes:
    """Вспомогательный xlsx с произвольным набором строк (для тестов аномалий)."""
    df = pd.DataFrame(rows, columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def test_upload_response_carries_anomalies_and_outline_overrides() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    client = _client(repo, storage)
    # Дублирующийся код 1.1 → парсер должен создать аномалию duplicate_code
    content = _xlsx_rows([("1", "A", "СМР"), ("1.1", "B", None), ("1.1", "C", None)])
    resp = client.post("/api/estimates", files={"file": ("e.xlsx", content, _XLSX)})
    assert resp.status_code == 201
    body = resp.json()
    assert any(a["kind"] == "duplicate_code" for a in body["anomalies"])
    assert "outline_overrides" in body


def test_toggle_reference_promotes_and_sets_flag() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    # смета с confirmed-строкой; тумблер ON → is_reference + промоушен
    client = _client(repo, storage, fund)
    eid = _seed_reviewed(repo)  # хелпер: смета с confirmed-строкой
    resp = client.patch(f"/api/estimates/{eid}/reference", json={"is_reference": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"is_reference": True, "promoted": 1}
    assert repo.is_reference(eid) is True and fund.entries  # запромоутилось


def test_toggle_reference_on_already_reference_empty_repromote_reports_db_fact() -> None:
    # смета уже в фонде (is_reference=True); повторный ON с 0 промоутабельных строк —
    # ответ обязан отражать ФАКТ БД (True), а не promoted>0 (иначе расхождение с реальным флагом)
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    client = _client(repo, storage, fund)
    eid = seed_estimate_with_rows(repo, [Row("образец работы", "no_match", "unreviewed")])
    repo.estimates[eid] = replace(repo.estimates[eid], user_id=2)
    repo.set_reference(eid, True)
    resp = client.patch(f"/api/estimates/{eid}/reference", json={"is_reference": True})
    assert resp.status_code == 200
    assert resp.json() == {"is_reference": True, "promoted": 0}
    assert repo.is_reference(eid) is True


def test_toggle_reference_off_unreferences() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    client = _client(repo, storage, fund)
    eid = _seed_reviewed(repo)
    repo.set_reference(eid, True)
    resp = client.patch(f"/api/estimates/{eid}/reference", json={"is_reference": False})
    assert resp.status_code == 200
    assert resp.json() == {"is_reference": False, "promoted": 0}
    assert repo.is_reference(eid) is False


def test_toggle_reference_foreign_estimate_404() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    eid = _seed_reviewed(repo)  # владелец id=2
    client = _client(repo, storage, fund, user=_user(uid=9))  # чужой, не админ
    resp = client.patch(f"/api/estimates/{eid}/reference", json={"is_reference": True})
    assert resp.status_code == 404


def test_rebuild_requires_admin() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    client = _client(repo, storage, fund, user=_user(role=Role.USER))
    assert client.post("/api/estimates/fund/rebuild").status_code == 403


def test_rebuild_as_admin_rebuilds_fund() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    fund = FakeDecisionFundRepository()
    eid = _seed_reviewed(repo)
    repo.set_reference(eid, True)
    client = _client(repo, storage, fund, user=_user(role=Role.ADMIN))
    resp = client.post("/api/estimates/fund/rebuild")
    assert resp.status_code == 200
    assert resp.json() == {"status": "rebuilt"}
    assert fund.entries  # rebuild пере-запромоутил reference-сметы


def test_row_status_matched_fund_serializes() -> None:
    repo, storage = FakeEstimateRepository(), FakeObjectStorage()
    eid = seed_estimate_with_rows(
        repo, [Row("образец работы", "matched_fund", "unreviewed")]
    )
    repo.estimates[eid] = replace(repo.estimates[eid], user_id=2)
    client = _client(repo, storage)
    resp = client.get(f"/api/estimates/{eid}")
    assert resp.status_code == 200
    assert resp.json()["rows"][0]["status"] == "matched_fund"
