"""ORM models.

Four tables:

    events          one row per event
    sections        price/name tiers within an event ("Gold", "Silver", ...)
    seats           one row per physical seat, owned by an event and a section
    bookings        one row per submitted booking (the booker's details)
    booking_seats   one row per seat inside a booking -- the join table that
                    decides who holds which seat

``booking_seats`` is where double-booking is prevented, at the database layer:
a seat may appear in at most one *active* booking_seats row, enforced by a
unique index. See the long comment on that table below.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class RevokedReason(str, enum.Enum):
    """Why a refresh token stopped working.

    The distinction matters: replaying a token that was revoked by *rotation*
    means someone is using a token the real owner already spent -- treated as a
    suspected leak, and every session for that account is dropped. Replaying one
    that was revoked by an explicit *logout* is just a stale client, and must
    not log the user out of their other devices.
    """

    ROTATED = "ROTATED"
    LOGOUT = "LOGOUT"
    REUSE_DETECTED = "REUSE_DETECTED"


class BookingStatus(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class User(Base):
    """An account. Only the bcrypt hash of the password is ever stored."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=True, length=16),
        nullable=False,
        default=UserRole.USER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    bookings: Mapped[list[Booking]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    __table_args__ = (
        # Emails are normalised to lower case before they are written, so a
        # plain unique index is enough to make accounts case-insensitive.
        UniqueConstraint("email", name="uq_users_email"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class RefreshToken(Base):
    """A refresh token's *hash*, so a database leak cannot be replayed.

    Rotated on every use: refreshing revokes the presented token and issues a
    new one. If an attacker and the real owner both hold the same token, the
    second one to use it is rejected.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_reason: Mapped[RevokedReason | None] = mapped_column(
        Enum(RevokedReason, native_enum=True, length=20), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),
        Index("ix_refresh_tokens_user", "user_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class SeatStatus(str, enum.Enum):
    """Derived per-seat status returned by the API (never stored)."""

    AVAILABLE = "AVAILABLE"
    BOOKED = "BOOKED"
    BLOCKED = "BLOCKED"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Snapshot of the generated layout, so the seat map can be rendered as a
    # grid without deriving the dimensions from the seat rows every time.
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list[Section]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="Section.display_order",
    )
    seats: Mapped[list[Seat]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    bookings: Mapped[list[Booking]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_events_event_date", "event_date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class Section(Base):
    """A named tier inside an event: gives seats a name and a price.

    Every seat belongs to exactly one section. Events created without explicit
    tiers get a single auto-generated "General" section, which keeps the seat
    -> section relationship mandatory instead of nullable.
    """

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    event: Mapped[Event] = relationship(back_populates="sections")
    seats: Mapped[list[Seat]] = relationship(back_populates="section")

    __table_args__ = (
        UniqueConstraint("event_id", "name", name="uq_sections_event_name"),
        CheckConstraint("price_cents >= 0", name="ck_sections_price_non_negative"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class Seat(Base):
    """One physical seat. Identified to humans as row_label + seat_number (A1)."""

    __tablename__ = "seats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )

    row_label: Mapped[str] = mapped_column(String(4), nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Admin-controlled unavailability (VIP hold, broken seat, ...). Independent
    # of bookings: a seat can be blocked while nobody has booked it.
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    event: Mapped[Event] = relationship(back_populates="seats")
    section: Mapped[Section] = relationship(back_populates="seats")
    booking_seats: Mapped[list[BookingSeat]] = relationship(
        back_populates="seat", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.row_label}{self.seat_number}"

    __table_args__ = (
        # No two seats in an event can share a coordinate.
        UniqueConstraint(
            "event_id", "row_label", "seat_number", name="uq_seats_event_row_number"
        ),
        Index("ix_seats_event_order", "event_id", "row_index", "seat_number"),
        CheckConstraint("seat_number >= 1", name="ck_seats_number_positive"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class Booking(Base):
    """A booking request that succeeded: one booker, one or more seats."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    reference: Mapped[str] = mapped_column(String(16), nullable=False)

    # NULL for guest bookings. The brief requires booking without a login, so
    # the account is an optional owner rather than a requirement: signed-in
    # bookings gain "my bookings" and ownership checks on cancellation, guest
    # bookings keep working exactly as before.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    booker_name: Mapped[str] = mapped_column(String(120), nullable=False)
    booker_email: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, native_enum=True, length=16),
        nullable=False,
        default=BookingStatus.CONFIRMED,
    )
    total_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    event: Mapped[Event] = relationship(back_populates="bookings")
    user: Mapped[User | None] = relationship(back_populates="bookings")
    seats: Mapped[list[BookingSeat]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_bookings_reference"),
        Index("ix_bookings_event_created", "event_id", "created_at"),
        Index("ix_bookings_email", "booker_email"),
        Index("ix_bookings_user_created", "user_id", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )


class BookingSeat(Base):
    """One seat inside one booking -- and the double-booking guard.

    ``is_active`` is 1 while the parent booking is CONFIRMED and 0 once it is
    cancelled. The two ``active_*`` columns are MySQL generated columns that
    mirror ``event_id``/``seat_id`` only while the row is active, and are NULL
    otherwise::

        active_event_id = IF(is_active = 1, event_id, NULL)
        active_seat_id  = IF(is_active = 1, seat_id,  NULL)

    The unique index ``uq_booking_seats_active`` on that pair is what actually
    prevents double-booking. Because MySQL's unique indexes ignore rows with a
    NULL key part, cancelled rows drop out of the index and the seat becomes
    bookable again -- while at most one *active* row per (event, seat) can ever
    exist, no matter how many requests race.

    This is a hard database guarantee, not an application check: it holds even
    if the service layer is bypassed, and it is the last line of defence behind
    the ``SELECT ... FOR UPDATE`` in ``services/bookings.py``.

    ``event_id`` is denormalised here (it is reachable via ``seats``) purely so
    the unique key can be expressed on (event, seat) as a single index.
    """

    __tablename__ = "booking_seats"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    seat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("seats.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )

    # Price captured at booking time so later tier changes cannot rewrite history.
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # VIRTUAL rather than STORED: MySQL forbids ON DELETE CASCADE on a column
    # that a *stored* generated column is derived from, and the cascades from
    # events/seats are worth keeping. A unique index on a virtual column is
    # still materialised in the index and enforced exactly the same way.
    active_event_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("(CASE WHEN is_active = 1 THEN event_id ELSE NULL END)", persisted=False),
        nullable=True,
    )
    active_seat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        Computed("(CASE WHEN is_active = 1 THEN seat_id ELSE NULL END)", persisted=False),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    booking: Mapped[Booking] = relationship(back_populates="seats")
    seat: Mapped[Seat] = relationship(back_populates="booking_seats")

    __table_args__ = (
        UniqueConstraint(
            "active_event_id", "active_seat_id", name="uq_booking_seats_active"
        ),
        Index("ix_booking_seats_seat", "seat_id"),
        Index("ix_booking_seats_booking", "booking_id"),
        Index("ix_booking_seats_event_active", "event_id", "is_active"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )
