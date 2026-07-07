"""Доменные исключения (без зависимостей от фреймворков).

Каждое пользовательское исключение несёт машинный код `code` — стабильный
идентификатор семантики для маппинга на локализованный текст на фронте
(этап 4 UX, спека 2026-07-06). Русские тексты сообщений остаются как
человекочитаемый fallback. Правило: код задаётся классовым атрибутом
(типовой случай) или аргументом конструктора (многопричинные классы —
код уточняется в точке raise).
"""

from __future__ import annotations


class DomainError(Exception):
    """Базовый класс доменных ошибок: несёт машинный код для API-контракта."""

    code: str = "error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class AuthError(DomainError):
    """Аутентификация не удалась (неверные данные / отключённая учётка)."""

    code = "invalid_credentials"


class DuplicateError(DomainError):
    """Нарушение уникальности (например, email уже существует)."""

    code = "user_email_exists"


class TokenError(DomainError):
    """Токен невалиден, повреждён или просрочен."""

    code = "not_authenticated"


class TemplateValidationError(DomainError):
    """Файл-шаблон структурно некорректен (дубликат кода, сирота-родитель).

    Многопричинный класс: код ОБЯЗАТЕЛЕН в точке raise
    (article_code_not_numeric / article_code_would_be_ancestor /
    article_parent_not_found / template_duplicate_code / template_orphan_parent).
    `code` — keyword-обязательный: пропуск на новой точке raise падает сразу,
    а не молча наследует базовый ``"error"`` (классовый атрибут остаётся ради
    контракта ``TemplateValidationError.code``).
    """

    def __init__(self, message: str = "", *, code: str) -> None:
        super().__init__(message, code=code)


class StorageError(DomainError):
    """Сбой объектного хранилища (MinIO/S3 недоступно или ошибка операции)."""

    code = "storage_unavailable"


class DeletionGuardError(DomainError):
    """Импорт удалил бы слишком много (порог) без явного force."""

    code = "template_deletion_guard"

    def __init__(self, deleted: int, roots_deleted: int) -> None:
        self.deleted = deleted
        self.roots_deleted = roots_deleted
        super().__init__(
            f"Импорт удалит {deleted} строк (из них корней: {roots_deleted}). "
            "Повторите с force=true, если это намеренно."
        )


class TransientError(DomainError):
    """Транзиентный сбой внешнего вызова (сеть/429/таймаут) — исчерпан инлайн-бюджет ретраев.

    Внутренний (гасится retry-обвязкой), до пользователя не доезжает — код не нужен.
    """


class DictionaryNotReadyError(DomainError):
    """Справочник не полностью заэмбежен — матчинг производить нельзя (gate)."""

    code = "matching_blocked_dictionary"

    def __init__(self, total: int, pending: int) -> None:
        self.total = total
        self.pending = pending
        super().__init__(f"справочник не готов: total={total} pending={pending}")


class RowNotMatchedError(DomainError):
    """Строка ещё не сматчена (status=pending) — ревью невозможно. → 409."""

    code = "row_not_matched"


class RowNotReviewableError(DomainError):
    """Строка-контекст (excluded) не решается в ревью. → 409."""

    code = "row_not_reviewable"


class InvalidReviewActionError(DomainError):
    """Действие не применимо к строке (confirm без matched_*, статья не найдена). → 422.

    Многопричинный: дефолт — review_unknown_action; прочие причины уточняют
    код в точке raise (см. спеку §3.4).
    """

    code = "review_unknown_action"


class EstimateNotCompletableError(DomainError):
    """Завершить можно только смету в терминально-успешном статусе (ready/partial_error)."""

    code = "estimate_not_completable"


class EstimateCompletedError(DomainError):
    """Смета завершена (completed_at) — решения ревью read-only до возобновления."""

    code = "estimate_completed_readonly"


class EstimateNotFoundError(DomainError):
    """Смета не существует или недоступна запрашивающему. → 404."""

    code = "estimate_not_found"


class EstimateRowNotFoundError(DomainError):
    """Строка сметы не найдена. → 404."""

    code = "estimate_row_not_found"
