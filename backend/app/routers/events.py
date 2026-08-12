"""Event, seat-map and admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..database import get_db
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


@router.post(
    "",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an event and generate its seat layout",
    responses={422: _ERRORS[422]},
)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventOut:
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
    responses=_ERRORS,
)
def block_seats(
    event_id: int, payload: SeatBlockRequest, db: Session = Depends(get_db)
) -> SeatBlockResult:
    return service.set_seat_blocked(db, event_id, payload)


@router.get(
    "/{event_id}/summary",
    response_model=AdminSummaryOut,
    summary="Admin dashboard: seat totals and every booking for the event",
    responses={404: _ERRORS[404]},
)
def admin_summary(event_id: int, db: Session = Depends(get_db)) -> AdminSummaryOut:
    return service.admin_summary(db, event_id)


@router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an event and everything under it (admin)",
    responses={404: _ERRORS[404]},
)
def delete_event(event_id: int, db: Session = Depends(get_db)) -> None:
    service.delete_event(db, event_id)
