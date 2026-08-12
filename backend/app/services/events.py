"""Event creation, seat-map reads and admin blocking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Integer, String, case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..errors import NotFoundError, ValidationError
from ..models import Booking, BookingSeat, BookingStatus, Event, SeatStatus, Seat, Section
from ..schemas import (
    AdminBookingRow,
    AdminSummaryOut,
    EventCreate,
    EventOut,
    EventSummary,
    SeatBlockRequest,
    SeatBlockResult,
    SeatMapOut,
    SeatOut,
    SeatRow,
)


def row_label_for(index: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA' -- spreadsheet-style row labels."""
    label = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def create_event(db: Session, payload: EventCreate) -> Event:
    """Create an event and materialise every seat in its layout."""
    _validate_layout(payload)

    event = Event(
        name=payload.name.strip(),
        description=payload.description,
        venue=payload.venue,
        event_date=payload.event_date,
        row_count=payload.rows,
        column_count=payload.columns,
    )
    db.add(event)
    db.flush()  # assigns event.id

    sections = _create_sections(db, event, payload)
    section_for_row = _map_rows_to_sections(payload, sections)

    blocked = {label.strip().upper() for label in payload.blocked_seats}

    seats: list[Seat] = []
    for row_index in range(payload.rows):
        label = row_label_for(row_index)
        section = section_for_row[row_index]
        for seat_number in range(1, payload.columns + 1):
            seats.append(
                Seat(
                    event_id=event.id,
                    section_id=section.id,
                    row_label=label,
                    row_index=row_index,
                    seat_number=seat_number,
                    is_blocked=f"{label}{seat_number}" in blocked,
                    blocked_reason=(
                        "Blocked at event creation"
                        if f"{label}{seat_number}" in blocked
                        else None
                    ),
                )
            )
    db.add_all(seats)
    db.flush()

    unknown = blocked - {f"{s.row_label}{s.seat_number}" for s in seats}
    if unknown:
        raise ValidationError(
            f"Unknown seat labels for this layout: {', '.join(sorted(unknown))}"
        )

    db.commit()
    db.refresh(event)
    return event


def _validate_layout(payload: EventCreate) -> None:
    if payload.rows > settings.max_rows_per_event:
        raise ValidationError(
            f"rows must be at most {settings.max_rows_per_event}"
        )
    if payload.columns > settings.max_columns_per_event:
        raise ValidationError(
            f"columns must be at most {settings.max_columns_per_event}"
        )
    if payload.rows * payload.columns > settings.max_seats_per_event:
        raise ValidationError(
            f"layout would create {payload.rows * payload.columns} seats; "
            f"the limit is {settings.max_seats_per_event}"
        )
    if payload.sections:
        covered = sum(section.row_count for section in payload.sections)
        if covered != payload.rows:
            raise ValidationError(
                f"section row_counts add up to {covered} but the layout has "
                f"{payload.rows} rows"
            )


def _create_sections(
    db: Session, event: Event, payload: EventCreate
) -> list[Section]:
    if payload.sections:
        sections = [
            Section(
                event_id=event.id,
                name=section.name.strip(),
                price_cents=section.price_cents,
                display_order=order,
            )
            for order, section in enumerate(payload.sections)
        ]
    else:
        sections = [
            Section(
                event_id=event.id,
                name="General",
                price_cents=payload.default_price_cents,
                display_order=0,
            )
        ]
    db.add_all(sections)
    db.flush()
    return sections


def _map_rows_to_sections(
    payload: EventCreate, sections: list[Section]
) -> dict[int, Section]:
    """Assign each row index to a section, filling sections top to bottom."""
    mapping: dict[int, Section] = {}
    if not payload.sections:
        for row_index in range(payload.rows):
            mapping[row_index] = sections[0]
        return mapping

    row_index = 0
    for section_input, section in zip(payload.sections, sections):
        for _ in range(section_input.row_count):
            mapping[row_index] = section
            row_index += 1
    return mapping


def get_event(db: Session, event_id: int) -> Event:
    event = db.execute(
        select(Event).options(selectinload(Event.sections)).where(Event.id == event_id)
    ).scalar_one_or_none()
    if event is None:
        raise NotFoundError(f"Event {event_id} does not exist.")
    return event


def _counts_query():
    """Per-event (total, booked, blocked) seat counts.

    The statuses are derived exactly the way ``get_seat_map`` derives them: a
    seat joined to an *active* booking_seats row is BOOKED, an unbooked seat
    with ``is_blocked`` is BLOCKED, everything else is AVAILABLE. Keeping the
    one definition means the dashboard totals can never drift from the map.

    Note the explicit ``Integer`` on the SUM results: summing a Boolean column
    directly would run the total back through SQLAlchemy's boolean converter
    and collapse any count above zero to 1.
    """
    return (
        select(
            Event.id.label("event_id"),
            func.count(Seat.id).label("total"),
            func.coalesce(
                func.sum(
                    case((BookingSeat.id.isnot(None), 1), else_=0).cast(Integer)
                ),
                0,
            ).label("booked"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            (BookingSeat.id.is_(None)) & (Seat.is_blocked.is_(True)),
                            1,
                        ),
                        else_=0,
                    ).cast(Integer)
                ),
                0,
            ).label("blocked"),
        )
        .select_from(Event)
        .outerjoin(Seat, Seat.event_id == Event.id)
        .outerjoin(
            BookingSeat,
            (BookingSeat.seat_id == Seat.id) & (BookingSeat.is_active.is_(True)),
        )
        .group_by(Event.id)
    )


def _seat_counts(db: Session, event_id: int) -> tuple[int, int, int]:
    """(total, booked, blocked) for one event, computed in the database."""
    row = db.execute(_counts_query().where(Event.id == event_id)).one_or_none()
    if row is None:
        return 0, 0, 0
    return int(row.total), int(row.booked), int(row.blocked)


def list_events(db: Session) -> list[EventSummary]:
    """All events, soonest first, each with its seat counts."""
    counts = {
        row.event_id: (int(row.total), int(row.booked), int(row.blocked))
        for row in db.execute(_counts_query()).all()
    }

    events = (
        db.execute(select(Event).order_by(Event.event_date.asc(), Event.id.desc()))
        .scalars()
        .all()
    )

    summaries: list[EventSummary] = []
    for event in events:
        total, booked, blocked = counts.get(event.id, (0, 0, 0))
        summaries.append(
            EventSummary(
                id=event.id,
                name=event.name,
                description=event.description,
                venue=event.venue,
                event_date=event.event_date,
                row_count=event.row_count,
                column_count=event.column_count,
                created_at=event.created_at,
                total_seats=total,
                booked_seats=booked,
                blocked_seats=blocked,
                available_seats=max(total - booked - blocked, 0),
            )
        )
    return summaries


def get_seat_map(db: Session, event_id: int) -> SeatMapOut:
    """The seat map: every seat with a derived AVAILABLE/BOOKED/BLOCKED status.

    Status is never stored on the seat -- it is derived from ``seats.is_blocked``
    and whether an *active* ``booking_seats`` row points at the seat. That keeps
    a single source of truth and makes cancellation a one-row update.
    """
    event = get_event(db, event_id)

    rows = db.execute(
        select(Seat, Section, BookingSeat.id)
        .join(Section, Section.id == Seat.section_id)
        .outerjoin(
            BookingSeat,
            (BookingSeat.seat_id == Seat.id) & (BookingSeat.is_active.is_(True)),
        )
        .where(Seat.event_id == event_id)
        .order_by(Seat.row_index.asc(), Seat.seat_number.asc())
    ).all()

    grouped: dict[int, SeatRow] = {}
    booked = blocked = 0

    for seat, section, active_booking_seat_id in rows:
        if active_booking_seat_id is not None:
            status = SeatStatus.BOOKED
            booked += 1
        elif seat.is_blocked:
            status = SeatStatus.BLOCKED
            blocked += 1
        else:
            status = SeatStatus.AVAILABLE

        seat_row = grouped.setdefault(
            seat.row_index,
            SeatRow(row_label=seat.row_label, row_index=seat.row_index, seats=[]),
        )
        seat_row.seats.append(
            SeatOut(
                id=seat.id,
                label=f"{seat.row_label}{seat.seat_number}",
                row_label=seat.row_label,
                row_index=seat.row_index,
                seat_number=seat.seat_number,
                section_id=section.id,
                section_name=section.name,
                price_cents=section.price_cents,
                status=status,
                blocked_reason=seat.blocked_reason if status == SeatStatus.BLOCKED else None,
            )
        )

    total = len(rows)
    return SeatMapOut(
        event=EventOut.model_validate(event),
        rows=[grouped[key] for key in sorted(grouped)],
        total_seats=total,
        booked_seats=booked,
        blocked_seats=blocked,
        available_seats=total - booked - blocked,
        generated_at=datetime.now(timezone.utc),
    )


def set_seat_blocked(
    db: Session, event_id: int, payload: SeatBlockRequest
) -> SeatBlockResult:
    """Block or unblock seats. Seats held by an active booking are left alone."""
    get_event(db, event_id)

    if not payload.seat_ids and not payload.seat_labels:
        raise ValidationError("Provide seat_ids or seat_labels.")

    conditions = []
    if payload.seat_ids:
        conditions.append(Seat.id.in_(payload.seat_ids))
    if payload.seat_labels:
        wanted = {label.strip().upper() for label in payload.seat_labels}
        conditions.append(
            func.concat(Seat.row_label, func.cast(Seat.seat_number, String)).in_(wanted)
        )

    seats = (
        db.execute(select(Seat).where(Seat.event_id == event_id, or_(*conditions)))
        .scalars()
        .all()
    )
    if not seats:
        raise NotFoundError("No matching seats in this event.")

    booked_ids = set(
        db.execute(
            select(BookingSeat.seat_id).where(
                BookingSeat.seat_id.in_([s.id for s in seats]),
                BookingSeat.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )

    updated: list[int] = []
    for seat in seats:
        if seat.id in booked_ids:
            continue
        seat.is_blocked = payload.blocked
        seat.blocked_reason = payload.reason if payload.blocked else None
        updated.append(seat.id)

    db.commit()
    return SeatBlockResult(
        updated_seat_ids=updated,
        blocked=payload.blocked,
        skipped_booked_seat_ids=sorted(booked_ids),
    )


def admin_summary(db: Session, event_id: int) -> AdminSummaryOut:
    """Totals plus the full booking list for the admin dashboard."""
    event = get_event(db, event_id)
    total, booked, blocked = _seat_counts(db, event_id)

    bookings = (
        db.execute(
            select(Booking)
            .options(selectinload(Booking.seats).selectinload(BookingSeat.seat))
            .where(Booking.event_id == event_id)
            .order_by(Booking.created_at.desc(), Booking.id.desc())
        )
        .scalars()
        .all()
    )

    rows: list[AdminBookingRow] = []
    revenue = 0
    cancelled = 0
    for booking in bookings:
        if booking.status == BookingStatus.CANCELLED:
            cancelled += 1
        else:
            revenue += booking.total_amount_cents
        labels = sorted(
            f"{bs.seat.row_label}{bs.seat.seat_number}" for bs in booking.seats
        )
        rows.append(
            AdminBookingRow(
                id=booking.id,
                reference=booking.reference,
                booker_name=booking.booker_name,
                booker_email=booking.booker_email,
                status=booking.status,
                seat_labels=labels,
                seat_count=len(labels),
                total_amount_cents=booking.total_amount_cents,
                created_at=booking.created_at,
                cancelled_at=booking.cancelled_at,
            )
        )

    return AdminSummaryOut(
        event=EventOut.model_validate(event),
        total_seats=total,
        booked_seats=booked,
        blocked_seats=blocked,
        available_seats=total - booked - blocked,
        total_bookings=len(rows) - cancelled,
        cancelled_bookings=cancelled,
        revenue_cents=revenue,
        bookings=rows,
    )


def delete_event(db: Session, event_id: int) -> None:
    event = get_event(db, event_id)
    db.delete(event)
    db.commit()
