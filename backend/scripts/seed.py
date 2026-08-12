#!/usr/bin/env python3
"""Populate the database with a couple of demo events and bookings.

    python scripts/seed.py            # add demo data
    python scripts/seed.py --reset    # drop every table first, then add it
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402,F401  (registers the tables)
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.schemas import (  # noqa: E402
    BookingCreate,
    EventCreate,
    RegisterRequest,
    SeatBlockRequest,
    SectionInput,
)
from app.services.auth import ensure_bootstrap_admin, register  # noqa: E402
from app.services.bookings import create_booking  # noqa: E402
from app.services.events import create_event, get_seat_map, set_seat_blocked  # noqa: E402


def seed(reset: bool) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
        print("dropped every table")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_bootstrap_admin(db)
        demo_user = _demo_user(db)
        concert = create_event(
            db,
            EventCreate(
                name="Coldplay: Music of the Spheres",
                description="World tour finale, with the full light show.",
                venue="DY Patil Stadium, Mumbai",
                event_date=datetime.now() + timedelta(days=45),
                rows=8,
                columns=12,
                sections=[
                    SectionInput(name="Gold", price_cents=450000, row_count=2),
                    SectionInput(name="Silver", price_cents=250000, row_count=3),
                    SectionInput(name="Bronze", price_cents=120000, row_count=3),
                ],
                blocked_seats=["A1", "A2", "A11", "A12"],
            ),
        )
        print(f"created event {concert.id}: {concert.name}")

        set_seat_blocked(
            db,
            concert.id,
            SeatBlockRequest(
                seat_labels=["H1", "H2", "H3"],
                blocked=True,
                reason="Sound desk",
            ),
        )

        seat_map = get_seat_map(db, concert.id)
        available = [
            seat.id
            for row in seat_map.rows
            for seat in row.seats
            if seat.status.value == "AVAILABLE"
        ]

        # The first booking is made *as* the demo account, so /account has
        # something in it; the rest are guest bookings.
        demo_bookers = [
            ("Demo User", "user@seatbook.dev", available[0:3], demo_user),
            ("Alan Turing", "alan@example.com", available[3:5], None),
            ("Grace Hopper", "grace@example.com", available[20:24], None),
        ]
        for name, email, seat_ids, owner in demo_bookers:
            booking = create_booking(
                db,
                BookingCreate(
                    event_id=concert.id,
                    seat_ids=seat_ids,
                    booker_name=name,
                    booker_email=email,
                ),
                user=owner,
            )
            kind = "account" if owner else "guest"
            print(f"  booked {len(seat_ids)} seat(s) for {name} ({kind}) -> {booking.reference}")

        talk = create_event(
            db,
            EventCreate(
                name="Tech Talk: Building for Concurrency",
                description="An evening on race conditions and how to lose to them.",
                venue="Auditorium 2",
                event_date=datetime.now() + timedelta(days=12),
                rows=5,
                columns=10,
                default_price_cents=0,
            ),
        )
        print(f"created event {talk.id}: {talk.name}")

        print("\nseed complete")
        print(f"  admin: {settings.bootstrap_admin_email} / {settings.bootstrap_admin_password}")
        print(f"  user:  {DEMO_USER_EMAIL} / {DEMO_USER_PASSWORD}")
    finally:
        db.close()


DEMO_USER_EMAIL = "user@seatbook.dev"
DEMO_USER_PASSWORD = "user12345"


def _demo_user(db):
    """A non-admin account, so the signed-in booking flow can be demonstrated."""
    from sqlalchemy import select

    from app.models import User

    existing = db.execute(
        select(User).where(User.email == DEMO_USER_EMAIL)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    return register(
        db,
        RegisterRequest(
            email=DEMO_USER_EMAIL, password=DEMO_USER_PASSWORD, full_name="Demo User"
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="drop every table before seeding"
    )
    seed(parser.parse_args().reset)
