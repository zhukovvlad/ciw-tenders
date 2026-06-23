from __future__ import annotations

import datetime

from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository
from app.infrastructure.db.models import EstimateModel, EstimateRowModel


def test_row_mapping_has_embedding_flag() -> None:
    m = EstimateRowModel(
        id=5, estimate_id=1, source_index=33, code="1.1.5", name="МОКАП",
        parent_code="1.1", section_type="СМР", depth=3, embedding_input="...",
        embedding=None, status="pending",
    )
    row = SqlAlchemyEstimateRepository._row_to_entity(m)
    assert row.code == "1.1.5" and row.source_index == 33 and row.has_embedding is False


def test_estimate_mapping_excludes_object_key() -> None:
    est = EstimateModel(
        id=1, user_id=7, filename="смета.xlsx", original_object_key="k",
        status="pending", created_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
    )
    entity = SqlAlchemyEstimateRepository._to_entity(est, [])
    assert entity.user_id == 7 and entity.filename == "смета.xlsx"
    assert not hasattr(entity, "original_object_key")


def test_match_values_overwrites_full_snapshot() -> None:
    from app.domain.entities import EstimateRowStatus, MatchCandidate, NodeMatch
    from app.infrastructure.db.estimate_repository import SqlAlchemyEstimateRepository

    # успех обнуляет match_error
    ok = SqlAlchemyEstimateRepository._match_values(
        NodeMatch(EstimateRowStatus.CONFIDENT, 5, "1.1", "X", 0.95,
                  [MatchCandidate(5, "1.1", "X", 0.95)])
    )
    assert ok["status"] == "confident" and ok["match_error"] is None
    assert ok["candidates"] == [{"id": 5, "code": "1.1", "name": "X", "score": 0.95}]

    # пустой снимок (no_match) → candidates None, score None
    nm = SqlAlchemyEstimateRepository._match_values(NodeMatch(EstimateRowStatus.NO_MATCH))
    assert nm["candidates"] is None and nm["score"] is None and nm["matched_article_id"] is None
