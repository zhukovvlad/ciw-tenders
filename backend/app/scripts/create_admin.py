"""Разовый bootstrap первого администратора.

Идемпотентно: если email уже есть — только повышает роль до admin (пароль НЕ
ротирует); если нет — создаёт. Запуск: `uv run python -m app.scripts.create_admin`.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.logging_config import setup_logging
from app.domain.entities import Role
from app.infrastructure.auth.password_hasher import Argon2PasswordHasher
from app.infrastructure.db.models import UserModel
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def main() -> None:
    setup_logging()
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        raise SystemExit("Задайте ADMIN_EMAIL и ADMIN_PASSWORD в backend/.env")

    email = settings.admin_email.strip().lower()
    session = SessionLocal()
    try:
        existing = (
            session.query(UserModel).filter(UserModel.email == email).one_or_none()
        )
        if existing is not None:
            if existing.role != Role.ADMIN.value:
                existing.role = Role.ADMIN.value
                session.commit()
                logger.info(
                    "Роль пользователя %s повышена до admin (пароль не изменён).", email
                )
            else:
                logger.info("Админ %s уже существует — изменений нет.", email)
            return

        hasher = Argon2PasswordHasher()
        session.add(
            UserModel(
                email=email,
                password_hash=hasher.hash(settings.admin_password),
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
        session.commit()
        logger.info("Создан администратор %s.", email)
    finally:
        session.close()


if __name__ == "__main__":
    main()
