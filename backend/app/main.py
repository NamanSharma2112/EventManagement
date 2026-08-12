"""FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Docs at:   http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .database import Base, engine
from .errors import register_error_handlers
from .routers import bookings, events

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_tables:
        # Import so every model is registered on Base.metadata before create_all.
        from . import models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        logger.info("Schema ensured on %s", engine.url.render_as_string(hide_password=True))
    yield
    engine.dispose()


app = FastAPI(
    title="Event Seat Booking API",
    version="1.0.0",
    description=(
        "Seat booking for events, with double-booking prevented in the database.\n\n"
        "A booking is written inside a single transaction that locks the requested "
        "`seats` rows with `SELECT ... FOR UPDATE`, re-checks availability, and then "
        "inserts into `booking_seats` -- where a unique index on the active "
        "(event, seat) pair makes a second booking for the same seat impossible. "
        "Losers of a race get **409 Conflict** and nothing is written, so a "
        "multi-seat booking is all-or-nothing."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(events.router)
app.include_router(bookings.router)


@app.get("/health", tags=["meta"], summary="Liveness and database check")
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as exc:  # pragma: no cover - only hit when MySQL is down
        logger.exception("Health check failed")
        return {"status": "degraded", "database": f"error: {exc.__class__.__name__}"}


@app.get("/", tags=["meta"], include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "Event Seat Booking API", "docs": "/docs", "health": "/health"}
