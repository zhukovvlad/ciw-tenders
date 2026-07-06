"""HTTP-ошибка с машинным кодом и общие хендлеры единой формы тела (этап 4, PR-1).

Форма тела любой пользовательской ошибки: {"detail": <русский текст>, "code": <snake_case>}.
detail — прежний человекочитаемый текст (инвариант совместимости), code — добавка.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import AuthError, DuplicateError


class ApiError(HTTPException):
    """HTTPException, несущий машинный код для тела ErrorOut."""

    def __init__(
        self,
        status_code: int,
        code: str,
        detail: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code


def register_error_handlers(app: FastAPI) -> None:
    """Хендлеры регистрируются в create_app(); Starlette ищет по __mro__ —
    ApiError-хендлер перекрывает дефолтный HTTPException-хендлер."""

    @app.exception_handler(ApiError)
    def _on_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
            headers=exc.headers,
        )

    @app.exception_handler(AuthError)
    def _on_auth_error(_: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc), "code": exc.code},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(DuplicateError)
    def _on_duplicate(_: Request, exc: DuplicateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc), "code": exc.code})

    @app.exception_handler(RequestValidationError)
    def _on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder обязателен: в ctx pydantic-ошибок бывают ValueError (спека §3.2)
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Некорректные данные запроса",
                "code": "validation_error",
                "errors": jsonable_encoder(exc.errors()),
            },
        )
