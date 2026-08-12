"""Engine, session factory and the FastAPI session dependency."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    """Declarative base for every ORM model."""


# ``READ COMMITTED`` rather than MySQL's default ``REPEATABLE READ``.
#
# Two reasons, both about the booking transaction (see services/bookings.py):
#
#   1. Under REPEATABLE READ every plain SELECT reads from the snapshot taken at
#      the start of the transaction, so a booker that has just waited on a row
#      lock could still read a stale "seat is free" answer. Under READ COMMITTED
#      each statement takes a fresh snapshot, so once the lock is granted the
#      availability check sees whatever the previous booker committed.
#   2. REPEATABLE READ adds gap locks around the index ranges it scans. Two
#      bookings for *neighbouring* seats can then deadlock on each other's gaps.
#      READ COMMITTED locks only the rows actually matched.
#
# Correctness never depends on this setting -- the unique index in
# ``booking_seats`` is the real guarantee -- but it makes the common path both
# accurate and deadlock-free.
engine = create_engine(
    settings.sqlalchemy_url,
    isolation_level="READ COMMITTED",
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
