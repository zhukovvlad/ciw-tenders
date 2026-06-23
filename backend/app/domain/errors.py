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


class StorageError(Exception):
    """Сбой объектного хранилища (MinIO/S3 недоступно или ошибка операции)."""


class DeletionGuardError(Exception):
    """Импорт удалил бы слишком много (порог) без явного force."""

    def __init__(self, deleted: int, roots_deleted: int) -> None:
        self.deleted = deleted
        self.roots_deleted = roots_deleted
        super().__init__(
            f"Импорт удалит {deleted} строк (из них корней: {roots_deleted}). "
            "Повторите с force=true, если это намеренно."
        )


class TransientError(Exception):
    """Транзиентный сбой внешнего вызова (сеть/429/таймаут) — исчерпан инлайн-бюджет ретраев."""


class DictionaryNotReadyError(Exception):
    """Справочник не полностью заэмбежен — матчинг производить нельзя (gate)."""

    def __init__(self, total: int, pending: int) -> None:
        self.total = total
        self.pending = pending
        super().__init__(f"справочник не готов: total={total} pending={pending}")
