"""Тестовое окружение: задаём обязательные переменные ДО импорта приложения.

Settings.database_url обязателен, а реальная БД в тестах не нужна (SQLAlchemy
create_engine не подключается при создании). Ключи AI — пустые: тесты используют
фейки портов и dependency_overrides.
"""

from __future__ import annotations

import io
import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("GOOGLE_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("S3_BUCKET", "estimates")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/0")
os.environ.setdefault("LOG_TO_FILE", "0")  # тесты не пишут лог-файлы (только в память/консоль)

# ---------------------------------------------------------------------------
# SP3 shared fixtures — used by test_estimate_detail_review.py and later tasks
# ---------------------------------------------------------------------------


def _make_user(uid: int = 1):
    """Фабрика фейк-пользователя для override get_current_user."""
    from app.domain.entities import Role, User

    return lambda: User(id=uid, email=f"u{uid}@mr.kz", password_hash="h", role=Role.USER)


def _xlsx_one_row() -> bytes:
    """Минимальная смета: один узел СМР, одна позиция."""
    df = pd.DataFrame(
        [("1", "Узел", "СМР"), (None, "Позиция", None)],
        columns=["№ раздела", "Наименование раздела / позиции", "Вид раздела"],
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


@pytest.fixture()
def estimate_repo():
    """Изолированный FakeEstimateRepository для одного теста."""
    from tests.fakes import FakeEstimateRepository

    return FakeEstimateRepository()


@pytest.fixture()
def client(estimate_repo):
    """TestClient с переопределёнными get_estimate_service, get_estimate_review_service
    и get_current_user (uid=1).

    Чтобы добавить второго пользователя (other_auth_headers) в последующих задачах:
    используй _make_user(uid=2) и отдельный override get_current_user в нужном тесте.
    Чтобы подменить article_repo для get_estimate_review_service — используй фикстуру
    article_repo (она переопределяет get_estimate_review_service с нужным репо).
    """
    from app.api.deps import (
        _do_sweep,
        get_current_user,
        get_estimate_repository,
        get_estimate_review_service,
        get_estimate_service,
        get_stale_sweeper,
        get_task_queue,
    )
    from app.main import app
    from app.services.estimate_parser import EstimateParser
    from app.services.estimate_review_service import EstimateReviewService
    from app.services.estimate_service import EstimateService
    from tests.fakes import FakeArticleRepository, FakeObjectStorage, FakeTaskQueue

    storage = FakeObjectStorage()
    queue = FakeTaskQueue()
    default_article_repo = FakeArticleRepository()

    def _svc() -> EstimateService:
        return EstimateService(EstimateParser(), estimate_repo, storage, task_queue=queue)

    def _review_svc() -> EstimateReviewService:
        return EstimateReviewService(estimates=estimate_repo, articles=default_article_repo)

    app.dependency_overrides[get_current_user] = _make_user(uid=1)
    app.dependency_overrides[get_estimate_service] = _svc
    app.dependency_overrides[get_estimate_review_service] = _review_svc
    app.dependency_overrides[get_estimate_repository] = lambda: estimate_repo
    app.dependency_overrides[get_task_queue] = lambda: queue
    app.dependency_overrides[get_stale_sweeper] = lambda: (
        lambda eid, age: _do_sweep(estimate_repo, eid, age)
    )
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers():
    """Заголовки авторизации для пользователя uid=1 (совпадает с override в `client`)."""
    return {"Authorization": "Bearer fake-token-uid-1"}


@pytest.fixture()
def article_repo(estimate_repo):
    """FakeArticleRepository для одного теста (SP3).

    Переопределяет get_estimate_review_service и get_article_service, чтобы
    сервис ревью и роут поиска использовали тот же article_repo.
    """
    from app.api.deps import get_article_service, get_estimate_review_service
    from app.main import app
    from app.services.article_service import ArticleService
    from app.services.estimate_review_service import EstimateReviewService
    from tests.fakes import FakeArticleRepository

    repo = FakeArticleRepository()

    def _review_svc() -> EstimateReviewService:
        return EstimateReviewService(estimates=estimate_repo, articles=repo)

    def _article_svc() -> ArticleService:
        return ArticleService(repository=repo)

    app.dependency_overrides[get_estimate_review_service] = _review_svc
    app.dependency_overrides[get_article_service] = _article_svc
    yield repo
    app.dependency_overrides.pop(get_estimate_review_service, None)
    app.dependency_overrides.pop(get_article_service, None)


@pytest.fixture()
def other_auth_headers():
    """Переопределяет get_current_user на uid=2 и возвращает заголовки (SP3 — 404-тест)."""
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = _make_user(uid=2)
    yield {"Authorization": "Bearer fake-token-uid-2"}
    # client-фикстура сделает clear() при своём teardown; здесь восстанавливаем uid=1
    # на случай если other_auth_headers используется без client
    app.dependency_overrides[get_current_user] = _make_user(uid=1)


@pytest.fixture()
def seed_estimate(estimate_repo):
    """Создаёт смету с одним узлом, возвращает (estimate_id, node_id)."""
    from app.domain.entities import NewEstimate
    from app.services.estimate_parser import EstimateParser

    nodes = EstimateParser().parse(_xlsx_one_row()).nodes
    est = estimate_repo.create(
        NewEstimate(user_id=1, filename="seed.xlsx", original_object_key="k/seed.xlsx"),
        nodes,
    )
    eid = est.id
    nid = est.rows[0].id
    return eid, nid


@pytest.fixture()
def object_storage(client, estimate_repo):
    """FakeObjectStorage смонтированная через get_estimate_export_service override.

    Контракт ObjectStorage.get: кидает StorageError на сбой/отсутствие объекта
    (FakeObjectStorage.get реализует это через try/except KeyError → StorageError).
    """
    from app.api.deps import get_estimate_export_service
    from app.main import app
    from app.services.estimate_export_service import EstimateExportService
    from tests.fakes import FakeObjectStorage

    storage = FakeObjectStorage()

    def _export_svc() -> EstimateExportService:
        return EstimateExportService(estimates=estimate_repo, storage=storage)

    app.dependency_overrides[get_estimate_export_service] = _export_svc
    yield storage
    app.dependency_overrides.pop(get_estimate_export_service, None)


@pytest.fixture()
def seed_estimate_with_source_index(estimate_repo):
    """Фабрика: создаёт смету с одним узлом с заданным source_index.

    Строит EstimateNode напрямую (минуя парсер), чтобы получить произвольный source_index.
    Ключ объекта = "key" (тесты кладут данные в object_storage.store["key"]).
    Возвращает callable(source_index) → (estimate_id, node_id).
    """
    from app.domain.entities import EstimateNode, NewEstimate

    def _factory(*, source_index: int) -> tuple[int, int]:
        node = EstimateNode(
            code="1",
            name="Тестовый узел",
            parent_code=None,
            section_type="СМР",
            embedding_input="1 Тестовый узел",
            source_index=source_index,
            depth=1,
        )
        est = estimate_repo.create(
            NewEstimate(user_id=1, filename="export_test.xlsx", original_object_key="key"),
            [node],
        )
        return est.id, est.rows[0].id

    return _factory
