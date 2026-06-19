"""Адаптер UserRepository на SQLAlchemy. Маппинг ORM-модель ↔ доменная сущность."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities import Role, User
from app.domain.ports import UserRepository
from app.infrastructure.db.models import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            password_hash=model.password_hash,
            role=Role(model.role),
            is_active=model.is_active,
            created_at=model.created_at,
        )

    def get_by_email(self, email: str) -> User | None:
        model = self._session.scalar(select(UserModel).where(UserModel.email == email))
        return self._to_entity(model) if model else None

    def get_by_id(self, user_id: int) -> User | None:
        model = self._session.get(UserModel, user_id)
        return self._to_entity(model) if model else None

    def add(self, user: User) -> User:
        model = UserModel(
            email=user.email,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
        )
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_entity(model)
