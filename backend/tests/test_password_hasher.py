from __future__ import annotations

from app.infrastructure.auth.password_hasher import Argon2PasswordHasher


def test_hash_is_not_plaintext_and_verifies() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("Пароль-123")
    assert hashed != "Пароль-123"
    assert hasher.verify("Пароль-123", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    hasher = Argon2PasswordHasher()
    hashed = hasher.hash("correct")
    assert hasher.verify("wrong", hashed) is False
