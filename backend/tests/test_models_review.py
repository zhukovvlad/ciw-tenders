from __future__ import annotations

from app.domain.entities import ReviewStatus, StoredEstimateRow
from app.infrastructure.db.models import EstimateRowModel


def test_review_status_values() -> None:
    assert ReviewStatus.UNREVIEWED == "unreviewed"
    assert {s.value for s in ReviewStatus} == {
        "unreviewed", "confirmed", "overridden", "rejected"
    }


def test_stored_row_review_defaults() -> None:
    row = StoredEstimateRow(
        id=1, code="1", name="n", parent_code=None, section_type=None,
        depth=0, embedding_input="x", source_index=0, status="pending",
    )
    assert row.review_status == "unreviewed"
    assert row.final_code is None
    assert row.candidates == []


def test_model_has_review_columns() -> None:
    cols = set(EstimateRowModel.__table__.columns.keys())
    assert {"review_status", "final_article_id", "final_code",
            "final_name", "reviewed_at"} <= cols
