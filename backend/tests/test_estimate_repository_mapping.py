from __future__ import annotations

from datetime import datetime, timezone

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
        status="pending", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    entity = SqlAlchemyEstimateRepository._to_entity(est, [])
    assert entity.user_id == 7 and entity.filename == "смета.xlsx"
    assert not hasattr(entity, "original_object_key")
