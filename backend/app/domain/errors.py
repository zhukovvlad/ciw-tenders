"""Доменные исключения авторизации (без зависимостей от фреймворков)."""

from __future__ import annotations


class AuthError(Exception):
    """Аутентификация не удалась (неверные данные / отключённая учётка)."""


class DuplicateError(Exception):
    """Нарушение уникальности (например, email уже существует)."""


class TokenError(Exception):
    """Токен невалиден, повреждён или просрочен."""


class TemplateValidationError(Exception):
    """Файл-шаблон структурно некорректен (дубликат кода, сирота-родитель)."""


class DeletionGuardError(Exception):
    """Импорт удалил бы слишком много (порог) без явного force."""

    def __init__(self, deleted: int, roots_deleted: int) -> None:
        self.deleted = deleted
        self.roots_deleted = roots_deleted
        super().__init__(
            f"Импорт удалит {deleted} строк (из них корней: {roots_deleted}). "
            "Повторите с force=true, если это намеренно."
        )
