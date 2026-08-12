"""The tests this assignment is really about.

Every test here uses real threads on real MySQL connections, so the thing under
test is InnoDB's locking and the unique index -- not Python.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, insert, select, text

from app.database import SessionLocal, engine
from app.errors import AppError, SeatUnavailableError
from app.models import Booking, BookingSeat, Seat
from app.schemas import BookingCreate, EventCreate
from app.services.bookings import create_booking
from app.services.events import create_event


@pytest.fixture
def event(db):
    """A 5x5 event created straight through the service layer."""
    return create_event(
        db,
        EventCreate(
            name="Concurrency Arena",
            event_date=datetime.now() + timedelta(days=10),
            rows=5,
            columns=5,
            default_price_cents=10000,
        ),
    )


def seats_for(db, event_id, labels=None):
    rows = (
        db.execute(select(Seat).where(Seat.event_id == event_id).order_by(Seat.id))
        .scalars()
        .all()
    )
    by_label = {f"{s.row_label}{s.seat_number}": s.id for s in rows}
    return by_label if labels is None else [by_label[label] for label in labels]


def book_in_own_session(event_id, seat_ids, email, barrier=None):
    """Run one booking on its own Session, i.e. its own MySQL connection.

    The barrier releases every worker at the same instant so the requests really
    do overlap inside the database rather than queuing up behind Python.
    """
    session = SessionLocal()
    try:
        if barrier is not None:
            barrier.wait(timeout=30)
        booking = create_booking(
            session,
            BookingCreate(
                event_id=event_id,
                seat_ids=seat_ids,
                booker_name=email.split("@")[0],
                booker_email=email,
            ),
        )
        return ("ok", booking.reference)
    except SeatUnavailableError as exc:
        return ("conflict", exc.detail)
    except AppError as exc:
        return ("error", f"{exc.code}: {exc.detail}")
    finally:
        session.close()


def active_rows(db, seat_id):
    return db.execute(
        select(func.count(BookingSeat.id)).where(
            BookingSeat.seat_id == seat_id, BookingSeat.is_active.is_(True)
        )
    ).scalar_one()


# --------------------------------------------------------------------------- #
# The headline case
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("racers", [2, 10])
def test_simultaneous_bookings_for_one_seat_leave_exactly_one_winner(db, event, racers):
    seat_id = seats_for(db, event.id, ["C3"])[0]
    barrier = Barrier(racers)

    with ThreadPoolExecutor(max_workers=racers) as pool:
        results = list(
            pool.map(
                lambda i: book_in_own_session(
                    event.id, [seat_id], f"racer{i}@example.com", barrier
                ),
                range(racers),
            )
        )

    outcomes = [status for status, _ in results]
    assert outcomes.count("ok") == 1, f"expected one winner, got {results}"
    assert outcomes.count("conflict") == racers - 1, results

    # And the database agrees: one active claim on the seat, one booking total.
    assert active_rows(db, seat_id) == 1
    assert db.execute(select(func.count(Booking.id))).scalar_one() == 1


def test_overlapping_group_bookings_never_partially_apply(db, event):
    """Two groups fight over one shared seat; the loser books nothing at all."""
    a1, a2, a3, a4, a5 = seats_for(db, event.id, ["A1", "A2", "A3", "A4", "A5"])
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(
            book_in_own_session, event.id, [a1, a2, a3], "left@example.com", barrier
        )
        right = pool.submit(
            book_in_own_session, event.id, [a3, a4, a5], "right@example.com", barrier
        )
        results = [left.result(timeout=30), right.result(timeout=30)]

    statuses = [status for status, _ in results]
    assert statuses.count("ok") == 1, results
    assert statuses.count("conflict") == 1, results

    # Exactly three seats are held, all from the winning request.
    held = (
        db.execute(
            select(BookingSeat.seat_id).where(
                BookingSeat.event_id == event.id, BookingSeat.is_active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    assert sorted(held) in (sorted([a1, a2, a3]), sorted([a3, a4, a5]))
    assert db.execute(select(func.count(Booking.id))).scalar_one() == 1


def test_stampede_over_a_small_seat_pool_never_double_books(db, event):
    """40 requests, 5 seats, every request wanting 2 random-ish seats."""
    pool_seats = seats_for(db, event.id, ["E1", "E2", "E3", "E4", "E5"])
    attempts = 40
    barrier = Barrier(attempts)

    def attempt(i: int):
        first = pool_seats[i % len(pool_seats)]
        second = pool_seats[(i + 1) % len(pool_seats)]
        return book_in_own_session(
            event.id, [first, second], f"stampede{i}@example.com", barrier
        )

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        results = list(executor.map(attempt, range(attempts)))

    wins = [r for r in results if r[0] == "ok"]
    assert wins, "at least one booking should have gone through"
    assert not [r for r in results if r[0] == "error"], results

    # No seat is claimed twice, and no more seats are held than were booked.
    duplicated = db.execute(
        select(BookingSeat.seat_id)
        .where(BookingSeat.is_active.is_(True))
        .group_by(BookingSeat.seat_id)
        .having(func.count(BookingSeat.id) > 1)
    ).all()
    assert duplicated == []

    held = db.execute(
        select(func.count(BookingSeat.id)).where(BookingSeat.is_active.is_(True))
    ).scalar_one()
    assert held == len(wins) * 2
    assert held <= len(pool_seats)


def test_freed_seat_can_be_won_by_exactly_one_racer(db, event):
    """After a cancellation the seat is contested again -- still one winner."""
    seat_id = seats_for(db, event.id, ["B2"])[0]

    status, reference = book_in_own_session(event.id, [seat_id], "first@example.com")
    assert status == "ok"

    from app.services.bookings import cancel_booking

    cancel_booking(db, reference)
    assert active_rows(db, seat_id) == 0

    barrier = Barrier(6)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda i: book_in_own_session(
                    event.id, [seat_id], f"round2-{i}@example.com", barrier
                ),
                range(6),
            )
        )

    assert [s for s, _ in results].count("ok") == 1, results
    assert active_rows(db, seat_id) == 1


# --------------------------------------------------------------------------- #
# The guarantee is in the database, not in the service layer
# --------------------------------------------------------------------------- #


def test_unique_index_rejects_a_duplicate_written_behind_the_services_back(db, event):
    """Insert straight into booking_seats, bypassing every application check.

    If the protection lived only in Python this would succeed. It must not.
    """
    seat_id = seats_for(db, event.id, ["D4"])[0]
    status, _ = book_in_own_session(event.id, [seat_id], "legit@example.com")
    assert status == "ok"

    booking = db.execute(select(Booking).limit(1)).scalar_one()

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError) as excinfo:
        with engine.begin() as connection:
            connection.execute(
                insert(BookingSeat).values(
                    booking_id=booking.id,
                    seat_id=seat_id,
                    event_id=event.id,
                    price_cents=0,
                    is_active=True,
                )
            )
    assert "uq_booking_seats_active" in str(excinfo.value)
    assert active_rows(db, seat_id) == 1


def test_cancelled_rows_leave_the_unique_index(db, event):
    """Two *inactive* claims on one seat are allowed; a second active one is not."""
    seat_id = seats_for(db, event.id, ["D5"])[0]
    status, reference = book_in_own_session(event.id, [seat_id], "one@example.com")
    assert status == "ok"

    from app.services.bookings import cancel_booking

    cancel_booking(db, reference)

    status, _ = book_in_own_session(event.id, [seat_id], "two@example.com")
    assert status == "ok"

    total = db.execute(
        select(func.count(BookingSeat.id)).where(BookingSeat.seat_id == seat_id)
    ).scalar_one()
    assert total == 2  # both rows survive as history
    assert active_rows(db, seat_id) == 1  # only one of them is active


def test_booking_transaction_takes_a_row_lock_on_the_seat(db, event):
    """Sanity check that the SELECT ... FOR UPDATE really locks the seat row.

    A second connection asking for the same row with NOWAIT must be refused
    while the first transaction is still open.
    """
    seat_id = seats_for(db, event.id, ["A1"])[0]

    holder = SessionLocal()
    try:
        holder.execute(
            select(Seat).where(Seat.id == seat_id).with_for_update()
        ).scalar_one()

        other = SessionLocal()
        try:
            with pytest.raises(Exception) as excinfo:
                other.execute(
                    text("SELECT id FROM seats WHERE id = :sid FOR UPDATE NOWAIT"),
                    {"sid": seat_id},
                ).all()
            # MySQL 3572: "Statement aborted because lock(s) could not be acquired"
            assert "3572" in str(excinfo.value) or "lock" in str(excinfo.value).lower()
        finally:
            other.rollback()
            other.close()
    finally:
        holder.rollback()
        holder.close()
