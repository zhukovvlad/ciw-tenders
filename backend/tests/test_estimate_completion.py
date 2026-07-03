"""Тесты жизненного цикла завершения сметы (этап 1 UX-роадмапа)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_article_service,
    get_current_user,
    get_estimate_repository,
    get_estimate_review_service,
    get_estimate_service,
)
from app.api.schemas import EstimateDetailOut, EstimateSummaryOut
from app.domain.entities import Estimate, EstimateNode, EstimateSummary, NewEstimate, Role, User
from app.domain.errors import EstimateCompletedError, EstimateNotCompletableError
from app.main import app
from app.services.article_service import ArticleService
from app.services.estimate_parser import EstimateParser
from app.services.estimate_review_service import EstimateReviewService
from app.services.estimate_service import EstimateService
from tests.fakes import (
    FakeArticleRepository,
    FakeEstimateRepository,
    FakeObjectStorage,
    FakeTaskQueue,
)

_TS = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


def test_detail_out_carries_completed_at() -> None:
    est = Estimate(
        id=1, user_id=1, filename="a.xlsx", status="ready",
        created_at=_TS, completed_at=_TS,
    )
    out = EstimateDetailOut.from_entity(est)
    assert out.completed_at == _TS


def test_detail_out_completed_at_defaults_none() -> None:
    est = Estimate(id=1, user_id=1, filename="a.xlsx", status="ready", created_at=_TS)
    assert EstimateDetailOut.from_entity(est).completed_at is None


def test_summary_out_carries_completed_at() -> None:
    s = EstimateSummary(
        id=1, filename="a.xlsx", status="ready", nodes_count=3,
        created_at=_TS, completed_at=_TS,
    )
    assert EstimateSummaryOut.from_entity(s).completed_at == _TS


# ---------------------------------------------------------------------------
# Сервис: set_completed (Step 1-4)
# ---------------------------------------------------------------------------


def _node(code: str) -> EstimateNode:
    return EstimateNode(code, f"имя {code}", None, "СМР", f"ei {code}", 0, len(code.split(".")))


def _seed_estimate(repo: FakeEstimateRepository, status: str) -> Estimate:
    """Хелпер: создать смету через repo.create + set_status (см. tests/test_estimate_service.py)."""
    est = repo.create(NewEstimate(1, "a.xlsx", "k1"), [_node("1")])
    repo.set_status(est.id, status)
    return est


def _make_estimate_service(repo: FakeEstimateRepository) -> EstimateService:
    return EstimateService(EstimateParser(), repo, FakeObjectStorage(), task_queue=FakeTaskQueue())


def _service_with_ready_estimate() -> tuple[EstimateService, Estimate]:
    """EstimateService + смета в статусе ready (см. паттерн test_estimate_service.py)."""
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="ready")  # хелпер: repo.create + set_status
    service = _make_estimate_service(repo)
    return service, est


def _service_with_running_estimate() -> tuple[EstimateService, Estimate]:
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="running")
    service = _make_estimate_service(repo)
    return service, est


def test_complete_sets_timestamp() -> None:
    service, est = _service_with_ready_estimate()
    ts = service.set_completed(est.id, 1, is_admin=False, completed=True)
    assert ts is not None


def test_reopen_clears_timestamp() -> None:
    service, est = _service_with_ready_estimate()
    service.set_completed(est.id, 1, is_admin=False, completed=True)
    ts = service.set_completed(est.id, 1, is_admin=False, completed=False)
    assert ts is None


def test_complete_running_estimate_rejected() -> None:
    service, est = _service_with_running_estimate()  # status="running"
    with pytest.raises(EstimateNotCompletableError):
        service.set_completed(est.id, 1, is_admin=False, completed=True)


def test_complete_unknown_estimate_raises_lookup() -> None:
    service, _ = _service_with_ready_estimate()
    with pytest.raises(LookupError):
        service.set_completed(9999, 1, is_admin=False, completed=True)


def test_complete_foreign_estimate_raises_lookup_for_non_admin() -> None:
    service, est = _service_with_ready_estimate()  # владелец user_id=1
    with pytest.raises(LookupError):
        service.set_completed(est.id, 2, is_admin=False, completed=True)


def _review_service_with_ready_estimate() -> (
    tuple[EstimateReviewService, FakeEstimateRepository, Estimate]
):
    """EstimateReviewService + фейк-репозиторий + смета в статусе ready (владелец user_id=1).

    По паттерну tests/test_estimate_review.py (article_repo + estimate_repo фикстуры).
    """
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="ready")
    review_service = EstimateReviewService(estimates=repo, articles=FakeArticleRepository())
    return review_service, repo, est


def _first_row_id(est: Estimate) -> int:
    return est.rows[0].id


def test_review_patch_rejected_for_completed_estimate() -> None:
    """Инвариант: завершённая смета read-only и на сервере, не только в UI.

    Иначе вторая вкладка с живым экраном ревью (или прямой запрос) молча
    перезапишет решения после того, как оператор закрыл смету.
    """
    # хелпер по паттерну test_estimate_review.py
    review_service, repo, est = _review_service_with_ready_estimate()
    repo.set_completed(est.id, 1, is_admin=False, completed=True)
    with pytest.raises(EstimateCompletedError):
        review_service.apply(est.id, _first_row_id(est), "confirm", None, 1, is_admin=False)


# ---------------------------------------------------------------------------
# Роут: PATCH /estimates/{id}/completion (Step 5-7)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_overrides():
    # teardown-чистка (см. test_estimate_routes.py): изоляция не зависит от того,
    # дошёл ли тест до конца.
    yield
    app.dependency_overrides.clear()


def _route_client(repo: FakeEstimateRepository) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1, email="u1@mr.kz", password_hash="h", role=Role.USER
    )
    app.dependency_overrides[get_estimate_service] = lambda: _make_estimate_service(repo)
    app.dependency_overrides[get_estimate_review_service] = lambda: EstimateReviewService(
        estimates=repo, articles=FakeArticleRepository()
    )
    app.dependency_overrides[get_estimate_repository] = lambda: repo
    app.dependency_overrides[get_article_service] = lambda: ArticleService(
        FakeArticleRepository()
    )
    return TestClient(app)


@pytest.fixture()
def client_with_ready_estimate() -> tuple[TestClient, int]:
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="ready")
    return _route_client(repo), est.id


@pytest.fixture()
def client_with_running_estimate() -> tuple[TestClient, int]:
    repo = FakeEstimateRepository()
    est = _seed_estimate(repo, status="running")
    return _route_client(repo), est.id


def _first_row_id_of(client: TestClient, est_id: int) -> int:
    resp = client.get(f"/api/estimates/{est_id}")
    return resp.json()["rows"][0]["id"]


def test_patch_completion_route_ok(client_with_ready_estimate) -> None:
    client, est_id = client_with_ready_estimate
    resp = client.patch(f"/api/estimates/{est_id}/completion", json={"completed": True})
    assert resp.status_code == 200
    assert resp.json()["completed_at"] is not None


def test_patch_completion_route_conflict_for_running(client_with_running_estimate) -> None:
    client, est_id = client_with_running_estimate
    resp = client.patch(f"/api/estimates/{est_id}/completion", json={"completed": True})
    assert resp.status_code == 409


def test_patch_completion_route_404(client_with_ready_estimate) -> None:
    client, _ = client_with_ready_estimate
    resp = client.patch("/api/estimates/9999/completion", json={"completed": True})
    assert resp.status_code == 404


def test_review_row_conflict_when_estimate_completed(client_with_ready_estimate) -> None:
    """Read-only инвариант сквозь роут: PATCH решения по завершённой смете → 409."""
    client, est_id = client_with_ready_estimate
    client.patch(f"/api/estimates/{est_id}/completion", json={"completed": True})
    resp = client.patch(
        f"/api/estimates/{est_id}/rows/{_first_row_id_of(client, est_id)}/review",
        json={"action": "confirm", "article_id": None},
    )
    assert resp.status_code == 409
