from __future__ import annotations

import io

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_template_ingest_service
from app.domain.entities import Role, User
from app.main import app
from app.services.template_ingest_service import TemplateIngestService
from app.services.template_parser import TemplateParser
from tests.fakes import FakeImportRepository

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(values: list[str]) -> bytes:
    df = pd.DataFrame({0: values})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, header=False, engine="openpyxl")
    return buffer.getvalue()


def _admin() -> User:
    return User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)


def _user() -> User:
    return User(id=2, email="user@mr.kz", password_hash="h", role=Role.USER)


def _service_factory(repo: FakeImportRepository):
    def _factory() -> TemplateIngestService:
        return TemplateIngestService(parser=TemplateParser(), repository=repo)

    return _factory


def test_import_creates_and_reports() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел", "(1.1.) Под"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert body["pending_embeddings"] == 2
    assert body["dry_run"] is False


def test_import_root_deletion_returns_409() -> None:
    repo = FakeImportRepository()
    TemplateIngestService(parser=TemplateParser(), repository=repo).import_template(
        _xlsx(["(1.) Раздел", "(2.) Второй"])
    )
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 409
    assert resp.json()["detail"]["force_required"] is True


def test_import_invalid_file_returns_400() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _admin
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел", "(1.) Дубль"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 400


def test_import_requires_admin() -> None:
    repo = FakeImportRepository()
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_template_ingest_service] = _service_factory(repo)

    client = TestClient(app)
    resp = client.post(
        "/api/articles/import",
        files={"file": ("Шаблон.xlsx", _xlsx(["(1.) Раздел"]), _XLSX)},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 403
