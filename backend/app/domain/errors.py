"""Доменные исключения авторизации (без зависимостей от фреймворков)."""

from __future__ import annotations


class AuthError(Exception):
    """Аутентификация не удалась (неверные данные / отключённая учётка)."""


class DuplicateError(Exception):
    """Нарушение уникальности (например, email уже существует)."""


class TokenError(Exception):
    """Токен невалиден, повреждён или просрочен."""
