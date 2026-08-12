"""Event, seat-map and admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import admin_guard
from ..models import User
from ..schemas import (
    AdminSummaryOut,
    ErrorResponse,
    EventCreate,
    EventOut,
    EventSummary,
    SeatBlockRequest,
    SeatBlockResult,
    SeatMapOut,
)
from ..services import events as service

router = APIRouter(prefix="/api/events", tags=["events"])

_ERRORS = {
    404: {"model": ErrorResponse, "description": "Event not found"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
}

# Applied to every write and to the admin dashboard. Reads that a booker needs
# -- the event list, the seat map -- stay public.
_ADMIN_ERRORS = {
    401: {"model": ErrorResponse, "description": "Not signed in"},
    403: {"model": ErrorResponse, "description": "Not an admin account"},
    **_ERRORS,
}


@router.post(
    "",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an event and generate its seat layout (admin)",
    responses={422: _ERRORS[422], 401: _ADMIN_ERRORS[401], 403: _ADMIN_ERRORS[403]},
)
def create_event(
    payload: EventCreate,
    db: Session = Depends(get_db),
    _: User | None = Depends(admin_guard),
) -> EventOut:
    event = service.create_event(db, payload)
    return EventOut.model_validate(event)


@router.get("", response_model=list[EventSummary], summary="List events with seat counts")
def list_events(db: Session = Depends(get_db)) -> list[EventSummary]:
    return service.list_events(db)


@router.get(
    "/{event_id}",
    response_model=EventOut,
    summary="Fetch a single event",
    responses={404: _ERRORS[404]},
)
def get_event(event_id: int, db: Session = Depends(get_db)) -> EventOut:
    return EventOut.model_validate(service.get_event(db, event_id))


@router.get(
    "/{event_id}/seats",
    response_model=SeatMapOut,
    summary="Fetch the seat map with derived seat statuses",
    responses={404: _ERRORS[404]},
)
def get_seat_map(event_id: int, db: Session = Depends(get_db)) -> SeatMapOut:
    return service.get_seat_map(db, event_id)


@router.post(
    "/{event_id}/seats/block",
    response_model=SeatBlockResult,
    summary="Block or unblock seats (admin)",
    responses=_ADMIN_ERRORS,
)
def block_seats(
    event_id: int,
    payload: SeatBlockRequest,
    db: Session = Depends(get_db),
    _: User | None = Depends(admin_guard),
) -> SeatBlockResult:
    return service.set_seat_blocked(db, event_id, payload)


@router.get(
    "/{event_id}/summary",
    response_model=AdminSummaryOut,
    summary="Admin dashboard: seat totals and every booking for the event (admin)",
    responses=_ADMIN_ERRORS,
)
def admin_summary(
    event_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(admin_guard),
) -> AdminSummaryOut:
    return service.admin_summary(db, event_id)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event and everything under it (admin)",
    responses=_ADMIN_ERRORS,
)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(admin_guard),
) -> None:
    service.delete_event(db, event_id)
