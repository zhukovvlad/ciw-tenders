"""Реализация TokenService на PyJWT (HS256)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.domain.entities import TokenPayload, User
from app.domain.errors import TokenError
from app.domain.ports import TokenService


class JwtTokenService(TokenService):
    def __init__(self, secret: str, algorithm: str, expire_minutes: int) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    def issue(self, user: User) -> str:
        now = datetime.now(timezone.utc)  # noqa: UP017
        payload = {
            "sub": str(user.id),  # PyJWT >= 2.10 требует строку
            "iat": now,
            "exp": now + timedelta(minutes=self._expire_minutes),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode(self, token: str) -> TokenPayload:
        try:
            data = jwt.decode(token, self._secret, algorithms=[self._algorithm])
        except jwt.PyJWTError as exc:
            raise TokenError(str(exc)) from exc
        return TokenPayload(user_id=int(data["sub"]))
