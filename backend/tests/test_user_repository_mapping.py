from __future__ import annotations

from datetime import UTC, datetime

from app.domain.entities import Role
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.user_repository import SqlAlchemyUserRepository


def test_to_entity_maps_fields() -> None:
    model = UserModel(
        id=5,
        email="ivan@mr.kz",
        password_hash="h",
        role="admin",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    entity = SqlAlchemyUserRepository._to_entity(model)
    assert entity.id == 5
    assert entity.email == "ivan@mr.kz"
    assert entity.role is Role.ADMIN
    assert entity.is_active is True
