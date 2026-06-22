from __future__ import annotations

from app.infrastructure.db.models import EstimateModel, EstimateRowModel


def test_estimate_tables_and_columns() -> None:
    assert EstimateModel.__tablename__ == "estimates"
    cols = set(EstimateModel.__table__.columns.keys())
    assert {"user_id", "filename", "original_object_key", "status"} <= cols

    assert EstimateRowModel.__tablename__ == "estimate_rows"
    rcols = set(EstimateRowModel.__table__.columns.keys())
    assert {"estimate_id", "source_index", "code", "embedding_input", "embedding"} <= rcols
