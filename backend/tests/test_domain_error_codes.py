"""Контракт кодов доменных ошибок (спека этапа 4, §3.4)."""

from __future__ import annotations

import pytest

from app.domain import errors as de


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (de.AuthError, "invalid_credentials"),
        (de.TokenError, "not_authenticated"),
        (de.DuplicateError, "user_email_exists"),
        (de.StorageError, "storage_unavailable"),
        (de.DeletionGuardError, "template_deletion_guard"),
        (de.DictionaryNotReadyError, "matching_blocked_dictionary"),
        (de.RowNotMatchedError, "row_not_matched"),
        (de.RowNotReviewableError, "row_not_reviewable"),
        (de.InvalidReviewActionError, "review_unknown_action"),
        (de.EstimateNotCompletableError, "estimate_not_completable"),
        (de.EstimateCompletedError, "estimate_completed_readonly"),
        (de.EstimateNotFoundError, "estimate_not_found"),
        (de.EstimateRowNotFoundError, "estimate_row_not_found"),
    ],
)
def test_default_codes(cls: type[de.DomainError], code: str) -> None:
    assert issubclass(cls, de.DomainError)
    assert cls.code == code


def test_ctor_overrides_code() -> None:
    exc = de.AuthError("Учётная запись отключена", code="account_disabled")
    assert exc.code == "account_disabled"
    assert str(exc) == "Учётная запись отключена"


def test_ctor_without_code_keeps_class_default() -> None:
    exc = de.RowNotMatchedError("Строка ещё не сматчена")
    assert exc.code == "row_not_matched"


def test_deletion_guard_keeps_payload_attrs() -> None:
    exc = de.DeletionGuardError(deleted=7, roots_deleted=2)
    assert exc.deleted == 7
    assert exc.roots_deleted == 2
    assert exc.code == "template_deletion_guard"
    assert "Импорт удалит 7 строк" in str(exc)


def test_dictionary_not_ready_keeps_payload_attrs() -> None:
    exc = de.DictionaryNotReadyError(total=10, pending=3)
    assert (exc.total, exc.pending) == (10, 3)
    assert str(exc) == "справочник не готов: total=10 pending=3"


def test_template_validation_requires_explicit_code() -> None:
    # multi-причинный класс: дефолт — базовый "error", код обязателен в точке raise
    exc = de.TemplateValidationError("x", code="template_duplicate_code")
    assert exc.code == "template_duplicate_code"
    assert de.TemplateValidationError.code == "error"
