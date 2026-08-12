"""Request and response models. These are the shapes documented at /docs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import BookingStatus, SeatStatus, UserRole
from .security import MAX_PASSWORD_BYTES

# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


class RegisterRequest(BaseModel):
    email: EmailStr
    # Lower bound is a real guard; the upper bound is bcrypt's 72-byte limit,
    # beyond which it silently ignores the rest of the password.
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded"
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class AuthSession(BaseModel):
    user: UserOut
    tokens: TokenPair


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


class SectionInput(BaseModel):
    """A price tier plus how many rows of the layout it covers.

    Sections are applied top-to-bottom: the first section takes the first
    ``row_count`` rows, the next takes the following rows, and so on.
    """

    name: str = Field(min_length=1, max_length=50)
    price_cents: int = Field(ge=0, default=0)
    row_count: int = Field(ge=1)


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    event_date: datetime
    description: str | None = Field(default=None, max_length=2000)
    venue: str | None = Field(default=None, max_length=200)

    rows: int = Field(ge=1, description="Number of seat rows (A, B, C, ...)")
    columns: int = Field(ge=1, description="Seats per row (1..columns)")

    # Optional tiers. When omitted every seat lands in one "General" section.
    sections: list[SectionInput] | None = None
    default_price_cents: int = Field(default=0, ge=0)

    # Seats to mark unavailable straight away, e.g. ["A1", "A2"].
    blocked_seats: list[str] = Field(default_factory=list)

    @field_validator("sections")
    @classmethod
    def _reject_duplicate_section_names(
        cls, value: list[SectionInput] | None
    ) -> list[SectionInput] | None:
        if value:
            names = [s.name.strip().lower() for s in value]
            if len(names) != len(set(names)):
                raise ValueError("section names must be unique")
        return value


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price_cents: int
    display_order: int


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    venue: str | None
    event_date: datetime
    row_count: int
    column_count: int
    created_at: datetime
    sections: list[SectionOut] = Field(default_factory=list)


class EventSummary(BaseModel):
    """Event plus seat counts -- what the event list and dashboard header show."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    venue: str | None
    event_date: datetime
    row_count: int
    column_count: int
    created_at: datetime
    total_seats: int
    booked_seats: int
    blocked_seats: int
    available_seats: int


# --------------------------------------------------------------------------- #
# Seat map
# --------------------------------------------------------------------------- #


class SeatOut(BaseModel):
    id: int
    label: str
    row_label: str
    row_index: int
    seat_number: int
    section_id: int
    section_name: str
    price_cents: int
    status: SeatStatus
    blocked_reason: str | None = None


class SeatRow(BaseModel):
    row_label: str
    row_index: int
    seats: list[SeatOut]


class SeatMapOut(BaseModel):
    event: EventOut
    rows: list[SeatRow]
    total_seats: int
    booked_seats: int
    blocked_seats: int
    available_seats: int
    # Server clock, so a polling client can tell how fresh a payload is.
    generated_at: datetime


class SeatBlockRequest(BaseModel):
    seat_ids: list[int] = Field(default_factory=list)
    seat_labels: list[str] = Field(default_factory=list)
    blocked: bool = True
    reason: str | None = Field(default=None, max_length=255)


class SeatBlockResult(BaseModel):
    updated_seat_ids: list[int]
    blocked: bool
    skipped_booked_seat_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Bookings
# --------------------------------------------------------------------------- #


class BookingCreate(BaseModel):
    event_id: int
    seat_ids: list[int] = Field(min_length=1)
    booker_name: str = Field(min_length=1, max_length=120)
    booker_email: EmailStr

    @field_validator("seat_ids")
    @classmethod
    def _dedupe(cls, value: list[int]) -> list[int]:
        # Deterministic order matters: the booking transaction locks seat rows in
        # ascending id order so two overlapping group bookings cannot deadlock.
        unique = sorted(set(value))
        if not unique:
            raise ValueError("at least one seat is required")
        return unique


class BookedSeatOut(BaseModel):
    seat_id: int
    label: str
    section_name: str
    price_cents: int


class BookingOut(BaseModel):
    id: int
    reference: str
    event_id: int
    event_name: str
    event_date: datetime | None = None
    venue: str | None = None
    user_id: int | None = None
    booker_name: str
    booker_email: str
    status: BookingStatus
    total_amount_cents: int
    created_at: datetime
    cancelled_at: datetime | None
    seats: list[BookedSeatOut]


# --------------------------------------------------------------------------- #
# Admin
# --------------------------------------------------------------------------- #


class AdminBookingRow(BaseModel):
    id: int
    reference: str
    user_id: int | None = None
    booker_name: str
    booker_email: str
    status: BookingStatus
    seat_labels: list[str]
    seat_count: int
    total_amount_cents: int
    created_at: datetime
    cancelled_at: datetime | None


class AdminSummaryOut(BaseModel):
    event: EventOut
    total_seats: int
    booked_seats: int
    blocked_seats: int
    available_seats: int
    total_bookings: int
    cancelled_bookings: int
    revenue_cents: int
    bookings: list[AdminBookingRow]


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ConflictSeat(BaseModel):
    seat_id: int
    label: str
    reason: str


class ErrorResponse(BaseModel):
    """Every 4xx from this API uses this envelope."""

    detail: str
    code: str
    conflicting_seats: list[ConflictSeat] | None = None
