"""Booking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import BookingCreate, BookingOut, ErrorResponse
from ..services import bookings as service

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book one or more seats (atomic, all-or-nothing)",
    responses={
        404: {"model": ErrorResponse, "description": "Event or seat not found"},
        409: {
            "model": ErrorResponse,
            "description": (
                "At least one seat is already booked or blocked. Nothing was "
                "written; `conflicting_seats` names the seats that clashed."
            ),
        },
        422: {"model": ErrorResponse, "description": "Invalid request"},
    },
)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> BookingOut:
    booking = service.create_booking(db, payload)
    return service.to_booking_out(db, booking)


@router.get(
    "/{reference}",
    response_model=BookingOut,
    summary="Look up a booking by its reference",
    responses={404: {"model": ErrorResponse, "description": "Booking not found"}},
)
def get_booking(reference: str, db: Session = Depends(get_db)) -> BookingOut:
    booking = service.get_booking(db, reference)
    return service.to_booking_out(db, booking)


@router.post(
    "/{reference}/cancel",
    response_model=BookingOut,
    summary="Cancel a booking and release its seats",
    responses={
        404: {"model": ErrorResponse, "description": "Booking not found"},
        409: {"model": ErrorResponse, "description": "Booking is already cancelled"},
    },
)
def cancel_booking(reference: str, db: Session = Depends(get_db)) -> BookingOut:
    booking = service.cancel_booking(db, reference)
    return service.to_booking_out(db, booking)
