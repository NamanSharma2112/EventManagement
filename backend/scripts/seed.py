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
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.schemas import BookingCreate, EventCreate, SeatBlockRequest, SectionInput  # noqa: E402
from app.services.bookings import create_booking  # noqa: E402
from app.services.events import create_event, get_seat_map, set_seat_blocked  # noqa: E402


def seed(reset: bool) -> None:
    if reset:
        Base.metadata.drop_all(bind=engine)
        print("dropped every table")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
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

        demo_bookers = [
            ("Ada Lovelace", "ada@example.com", available[0:3]),
            ("Alan Turing", "alan@example.com", available[3:5]),
            ("Grace Hopper", "grace@example.com", available[20:24]),
        ]
        for name, email, seat_ids in demo_bookers:
            booking = create_booking(
                db,
                BookingCreate(
                    event_id=concert.id,
                    seat_ids=seat_ids,
                    booker_name=name,
                    booker_email=email,
                ),
            )
            print(f"  booked {len(seat_ids)} seat(s) for {name} -> {booking.reference}")

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
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="drop every table before seeding"
    )
    seed(parser.parse_args().reset)
