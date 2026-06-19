"""Реализация PasswordHasher на argon2 (pwdlib). За портом — выбор алгоритма обратим."""

from __future__ import annotations

from pwdlib import PasswordHash

from app.domain.ports import PasswordHasher


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._hasher = PasswordHash.recommended()

    def hash(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        return self._hasher.verify(plain, hashed)
