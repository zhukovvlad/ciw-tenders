"""Test ORM estimate models."""

from __future__ import annotations


def test_estimate_match_snapshot_columns() -> None:
    """Test that match snapshot columns are defined on ORM models."""
    from app.infrastructure.db.models import EstimateModel, EstimateRowModel

    rcols = set(EstimateRowModel.__table__.columns.keys())
    assert {
        "matched_article_id",
        "matched_code",
        "matched_name",
        "score",
        "candidates",
        "match_error",
    } <= rcols
    assert "status_detail" in EstimateModel.__table__.columns.keys()
