"""Сценарии аутентификации: логин и создание пользователя. Зависит только от портов."""

from __future__ import annotations

from functools import lru_cache

from app.domain.entities import Role, User
from app.domain.errors import AuthError, DuplicateError
from app.domain.ports import PasswordHasher, TokenService, UserRepository

_TIMING_PASSWORD = "timing-equalizer-not-a-real-password"


@lru_cache(maxsize=8)
def _dummy_hash(hasher: PasswordHasher) -> str:
    """Dummy-хэш для выравнивания тайминга. Кэшируется по hasher, поэтому полный
    argon2 считается один раз на процесс (get_password_hasher — @lru_cache singleton),
    а не на каждый запрос /login."""
    return hasher.hash(_TIMING_PASSWORD)


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._tokens = tokens
        # dummy-хэш теми же параметрами, что и боевые (один verify на обоих путях).
        self._dummy_hash = _dummy_hash(hasher)

    def login(self, email: str, password: str) -> str:
        email = email.strip().lower()
        user = self._users.get_by_email(email)
        if user is None:
            # Прогоняем verify против dummy-хэша, чтобы время ответа не выдавало
            # отсутствие email (защита от тайминг-перечисления).
            self._hasher.verify(password, self._dummy_hash)
            raise AuthError("Неверный email или пароль")
        if not self._hasher.verify(password, user.password_hash):
            raise AuthError("Неверный email или пароль")
        if not user.is_active:
            raise AuthError("Учётная запись отключена")
        return self._tokens.issue(user)

    def create_user(self, email: str, password: str, role: Role = Role.USER) -> User:
        email = email.strip().lower()
        if self._users.get_by_email(email) is not None:
            raise DuplicateError("Пользователь с таким email уже существует")
        user = User(
            email=email,
            password_hash=self._hasher.hash(password),
            role=role,
        )
        return self._users.add(user)
