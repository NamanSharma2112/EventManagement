"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user
from ..models import Booking, BookingSeat, User
from ..schemas import (
    AuthSession,
    BookingOut,
    ErrorResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)
from ..services import auth as service
from ..services.bookings import to_booking_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

_UNAUTHENTICATED = {
    "model": ErrorResponse,
    "description": "Missing, expired or invalid credentials",
}


@router.post(
    "/register",
    response_model=AuthSession,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
    responses={
        409: {"model": ErrorResponse, "description": "Email is already registered"},
        422: {"model": ErrorResponse, "description": "Invalid email or weak password"},
    },
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthSession:
    user = service.register(db, payload)
    return AuthSession(user=UserOut.model_validate(user), tokens=service.issue_tokens(db, user))


@router.post(
    "/login",
    response_model=AuthSession,
    summary="Exchange email and password for tokens",
    responses={401: _UNAUTHENTICATED},
)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthSession:
    user = service.authenticate(db, payload)
    return AuthSession(user=UserOut.model_validate(user), tokens=service.issue_tokens(db, user))


@router.post(
    "/refresh",
    response_model=AuthSession,
    summary="Rotate a refresh token for a fresh pair",
    responses={401: _UNAUTHENTICATED},
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AuthSession:
    user, tokens = service.refresh(db, payload.refresh_token)
    return AuthSession(user=UserOut.model_validate(user), tokens=tokens)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one refresh token",
)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> None:
    # Unknown tokens are a no-op: logging out should never fail.
    service.logout(db, payload.refresh_token)


@router.post(
    "/logout-all",
    summary="Revoke every session for the signed-in account",
    responses={401: _UNAUTHENTICATED},
)
def logout_all(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, int]:
    return {"revoked_sessions": service.logout_everywhere(db, user.id)}


@router.get(
    "/me",
    response_model=UserOut,
    summary="The signed-in account",
    responses={401: _UNAUTHENTICATED},
)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get(
    "/me/bookings",
    response_model=list[BookingOut],
    summary="Every booking made while signed in to this account",
    responses={401: _UNAUTHENTICATED},
)
def my_bookings(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[BookingOut]:
    bookings = (
        db.execute(
            select(Booking)
            .options(
                selectinload(Booking.seats).selectinload(BookingSeat.seat),
                selectinload(Booking.event),
            )
            .where(Booking.user_id == user.id)
            .order_by(Booking.created_at.desc(), Booking.id.desc())
        )
        .scalars()
        .all()
    )
    return [to_booking_out(db, booking) for booking in bookings]
