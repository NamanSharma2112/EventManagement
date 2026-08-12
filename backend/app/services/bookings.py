"""Booking creation and cancellation.

Everything interesting about this assignment lives in ``create_booking``.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..errors import (
    BookingStateError,
    NotFoundError,
    SeatUnavailableError,
    ValidationError,
)
from ..models import Booking, BookingSeat, BookingStatus, Event, Seat, Section
from ..schemas import BookedSeatOut, BookingCreate, BookingOut

logger = logging.getLogger("app.bookings")

_REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alikes


def _new_reference() -> str:
    return "BK-" + "".join(secrets.choice(_REFERENCE_ALPHABET) for _ in range(8))


def create_booking(db: Session, payload: BookingCreate) -> Booking:
    """Book one or more seats, atomically.

    Concurrency, in the order the safeguards apply:

    1. ``SELECT ... FOR UPDATE`` on the requested ``seats`` rows, ordered by id.
       This is what serialises two bookers who want the same seat: the second
       transaction blocks on the row lock until the first commits or rolls back.
       Locking in a fixed (ascending id) order means two overlapping group
       bookings -- {5, 9} and {9, 5} -- can never deadlock against each other.

    2. Availability is re-checked *after* the lock is held. The session runs at
       READ COMMITTED (see database.py), so this read sees everything committed
       while we were waiting, including a booking that just took our seat. This
       is what produces the friendly "seats A3, A4 were just taken" message.

    3. The insert into ``booking_seats`` hits the unique index on
       (active_event_id, active_seat_id). That index -- not steps 1 and 2 -- is
       the actual guarantee. If anything ever bypasses the lock, MySQL rejects
       the duplicate and we translate the IntegrityError into the same 409.

    All of it runs in one transaction, so a group booking is all-or-nothing: if
    seat 3 of 3 is gone, the rollback undoes seats 1 and 2 as well and no
    partial booking is ever visible.
    """
    if len(payload.seat_ids) > settings.max_seats_per_booking:
        raise ValidationError(
            f"A single booking may hold at most {settings.max_seats_per_booking} seats."
        )

    event = db.get(Event, payload.event_id)
    if event is None:
        raise NotFoundError(f"Event {payload.event_id} does not exist.")

    try:
        # ---- 1. lock the seat rows, in a deterministic order -------------- #
        seats = (
            db.execute(
                select(Seat)
                .where(Seat.event_id == event.id, Seat.id.in_(payload.seat_ids))
                .order_by(Seat.id.asc())
                .with_for_update()
            )
            .scalars()
            .all()
        )

        found_ids = {seat.id for seat in seats}
        missing = [sid for sid in payload.seat_ids if sid not in found_ids]
        if missing:
            raise NotFoundError(
                "These seat ids do not belong to this event: "
                + ", ".join(str(sid) for sid in missing)
            )

        # ---- 2. re-check availability while holding the locks ------------- #
        conflicts: list[dict[str, object]] = []

        for seat in seats:
            if seat.is_blocked:
                conflicts.append(
                    {
                        "seat_id": seat.id,
                        "label": seat.label,
                        "reason": seat.blocked_reason or "Seat is blocked by the organiser.",
                    }
                )

        taken_ids = set(
            db.execute(
                select(BookingSeat.seat_id).where(
                    BookingSeat.seat_id.in_(found_ids),
                    BookingSeat.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        seats_by_id = {seat.id: seat for seat in seats}
        for seat_id in sorted(taken_ids):
            conflicts.append(
                {
                    "seat_id": seat_id,
                    "label": seats_by_id[seat_id].label,
                    "reason": "Seat has already been booked.",
                }
            )

        if conflicts:
            labels = ", ".join(str(c["label"]) for c in conflicts)
            raise SeatUnavailableError(
                f"Seats no longer available: {labels}. No seats were booked.",
                conflicting_seats=conflicts,
            )

        # ---- 3. write the booking; the unique index has the final say ----- #
        prices = dict(
            db.execute(
                select(Section.id, Section.price_cents).where(
                    Section.event_id == event.id
                )
            ).all()
        )

        booking = Booking(
            event_id=event.id,
            reference=_new_reference(),
            booker_name=payload.booker_name.strip(),
            booker_email=str(payload.booker_email).strip().lower(),
            status=BookingStatus.CONFIRMED,
            total_amount_cents=sum(prices.get(seat.section_id, 0) for seat in seats),
        )
        db.add(booking)
        db.flush()

        db.add_all(
            BookingSeat(
                booking_id=booking.id,
                seat_id=seat.id,
                event_id=event.id,
                price_cents=prices.get(seat.section_id, 0),
                is_active=True,
            )
            for seat in seats
        )
        db.flush()
        db.commit()

    except IntegrityError as exc:
        # The unique index rejected a seat that slipped past the checks above.
        # Same outcome as a detected conflict: nothing is written, caller gets 409.
        db.rollback()
        logger.warning("Booking rejected by unique index: %s", exc.orig)
        raise SeatUnavailableError(
            "One or more of those seats was booked by someone else a moment ago. "
            "No seats were booked -- please refresh and try again."
        ) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(booking)
    _send_mock_confirmation(db, booking)
    return booking


def cancel_booking(db: Session, reference: str) -> Booking:
    """Cancel a booking and release its seats.

    Deactivating the ``booking_seats`` rows drops them out of the partial unique
    index, which is what makes the seats bookable again while keeping the
    cancelled booking on record for the admin dashboard.
    """
    booking = _load_booking(db, reference)
    if booking.status == BookingStatus.CANCELLED:
        raise BookingStateError(f"Booking {reference} is already cancelled.")

    try:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = datetime.now(timezone.utc)
        for booking_seat in booking.seats:
            booking_seat.is_active = False
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(booking)
    return booking


def get_booking(db: Session, reference: str) -> Booking:
    return _load_booking(db, reference)


def _load_booking(db: Session, reference: str) -> Booking:
    booking = db.execute(
        select(Booking)
        .options(
            selectinload(Booking.seats).selectinload(BookingSeat.seat),
            selectinload(Booking.event),
        )
        .where(Booking.reference == reference.strip().upper())
    ).scalar_one_or_none()
    if booking is None:
        raise NotFoundError(f"No booking found with reference {reference}.")
    return booking


def to_booking_out(db: Session, booking: Booking) -> BookingOut:
    seat_rows = db.execute(
        select(BookingSeat, Seat, Section)
        .join(Seat, Seat.id == BookingSeat.seat_id)
        .join(Section, Section.id == Seat.section_id)
        .where(BookingSeat.booking_id == booking.id)
        .order_by(Seat.row_index.asc(), Seat.seat_number.asc())
    ).all()

    event_name = booking.event.name if booking.event else ""
    return BookingOut(
        id=booking.id,
        reference=booking.reference,
        event_id=booking.event_id,
        event_name=event_name,
        booker_name=booking.booker_name,
        booker_email=booking.booker_email,
        status=booking.status,
        total_amount_cents=booking.total_amount_cents,
        created_at=booking.created_at,
        cancelled_at=booking.cancelled_at,
        seats=[
            BookedSeatOut(
                seat_id=seat.id,
                label=f"{seat.row_label}{seat.seat_number}",
                section_name=section.name,
                price_cents=booking_seat.price_cents,
            )
            for booking_seat, seat, section in seat_rows
        ],
    )


def _send_mock_confirmation(db: Session, booking: Booking) -> None:
    """Bonus: a stand-in for a confirmation email. Logged, never sent."""
    if not settings.mock_email_enabled:
        return
    detail = to_booking_out(db, booking)
    labels = ", ".join(seat.label for seat in detail.seats)
    logger.info(
        "[mock-email] To: %s | Subject: Booking %s confirmed | "
        "Event: %s | Seats: %s | Total: %.2f",
        booking.booker_email,
        booking.reference,
        detail.event_name,
        labels,
        booking.total_amount_cents / 100,
    )
