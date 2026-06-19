"""Роуты аутентификации: логин, заведение пользователя (admin), текущий профиль."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user, require_admin
from app.api.schemas import LoginRequest, TokenResponse, UserCreateRequest, UserOut
from app.domain.entities import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    token = service.login(email=payload.email, password=payload.password)
    return TokenResponse(access_token=token)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_user(
    payload: UserCreateRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = service.create_user(
        email=payload.email, password=payload.password, role=payload.role
    )
    return UserOut.from_entity(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_entity(user)
