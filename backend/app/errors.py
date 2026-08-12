"""Domain errors and the handlers that turn them into JSON responses."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base for errors that map onto a specific HTTP status."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(self, detail: str, **extra: object) -> None:
        super().__init__(detail)
        self.detail = detail
        self.extra = extra

    def to_payload(self) -> dict[str, object]:
        return {"detail": self.detail, "code": self.code, **self.extra}


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class AuthError(AppError):
    """Bad or missing credentials -- 401."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthenticated"


class PermissionError_(AppError):
    """Authenticated, but not allowed to do this -- 403."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class SeatUnavailableError(AppError):
    """At least one requested seat is already booked or blocked.

    409 Conflict, with the offending seats named so the UI can highlight them.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "seat_unavailable"

    def __init__(
        self, detail: str, conflicting_seats: list[dict[str, object]] | None = None
    ) -> None:
        super().__init__(detail, conflicting_seats=conflicting_seats or [])


class BookingStateError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "invalid_booking_state"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=jsonable_encoder(exc.to_payload())
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc.detail), "code": _code_for(exc.status_code)},
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "detail": "Request body failed validation.",
                "code": "validation_error",
                "errors": jsonable_encoder(exc.errors()),
            },
        )


def _code_for(status_code: int) -> str:
    return {
        status.HTTP_401_UNAUTHORIZED: "unauthenticated",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    }.get(status_code, "error")
