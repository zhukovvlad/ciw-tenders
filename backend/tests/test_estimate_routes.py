from __future__ import annotations

import io
from collections.abc import Callable

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_estimate_service, get_settings
from app.core.config import Settings
from app.domain.entities import Role, User
from app.main import app
from app.services.estimate_parser import EstimateParser
from app.services.estimate_service import EstimateService
from tests.fakes import FakeEstimateRepository, FakeObjectStorage, FakeTaskQueue

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


def _client(repo, storage, user=_DEFAULT_USER) -> TestClient:
    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_estimate_service] = _svc_factory(repo, storage)
    return TestClient(app)


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
