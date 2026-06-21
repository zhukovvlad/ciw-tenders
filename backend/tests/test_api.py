"""Smoke-тест API через httpx + dependency_overrides (без реальных БД/AI)."""

from __future__ import annotations

import io

import pandas as pd
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_matching_service, get_parser
from app.domain.entities import ArticleCandidate, Role, TemplateArticle, User
from app.main import app
from app.services.excel_parser import ExcelEstimateParser
from app.services.matching_service import MatchingService
from tests.fakes import FakeEmbedder, FakeLLMMatcher, FakeRepository


def _fake_admin() -> User:
    return User(id=1, email="admin@mr.kz", password_hash="h", role=Role.ADMIN)


def _fake_matching_service() -> MatchingService:
    candidates = [
        ArticleCandidate(
            article=TemplateArticle(
                id=1, article_code="A", name="Фундамент", embedding_input="Бетон. Фундамент"
            ),
            score=0.97,
        )
    ]
    return MatchingService(
        repository=FakeRepository(candidates),
        embedder=FakeEmbedder(),
        llm_matcher=FakeLLMMatcher(),
        confidence_threshold=0.90,
    )


def test_health() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_match_endpoint() -> None:
    app.dependency_overrides[get_current_user] = _fake_admin
    app.dependency_overrides[get_parser] = ExcelEstimateParser
    app.dependency_overrides[get_matching_service] = _fake_matching_service

    df = pd.DataFrame({"Вид раздела": ["СМР"], "Наименование": ["Устройство фундамента"]})
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")

    client = TestClient(app)
    response = client.post(
        "/api/estimates/match",
        files={
            "file": (
                "estimate.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "Уверенное совпадение"
    assert body[0]["matched_code"] == "A"
