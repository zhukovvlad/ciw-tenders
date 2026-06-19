"""Тестовое окружение: задаём обязательные переменные ДО импорта приложения.

Settings.database_url обязателен, а реальная БД в тестах не нужна (SQLAlchemy
create_engine не подключается при создании). Ключи AI — пустые: тесты используют
фейки портов и dependency_overrides.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
os.environ.setdefault("GOOGLE_API_KEY", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")
