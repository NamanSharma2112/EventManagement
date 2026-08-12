"""Test fixtures.

Tests run against a real MySQL database (``seatbooking_test`` by default).
That is deliberate: the concurrency guarantees under test are MySQL row locks
and a MySQL unique index, so an in-memory stand-in would prove nothing.
"""

from __future__ import annotations

import os

# Point the app at the test database before anything imports app.config.
os.environ.setdefault("MYSQL_DATABASE", "seatbooking_test")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
os.environ.setdefault("MOCK_EMAIL_ENABLED", "false")

from datetime import datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import models  # noqa: E402,F401  (registers the tables)
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Empty every table between tests, cheapest order first."""
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("booking_seats", "bookings", "seats", "sections", "events"):
            connection.execute(text(f"TRUNCATE TABLE {table}"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def event_payload():
    return {
        "name": "Test Event",
        "event_date": (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds"),
        "venue": "Test Arena",
        "rows": 4,
        "columns": 6,
        "default_price_cents": 50000,
    }


@pytest.fixture
def created_event(client, event_payload):
    response = client.post("/api/events", json=event_payload)
    assert response.status_code == 201, response.text
    return response.json()


def seat_ids_by_label(client, event_id: int) -> dict[str, int]:
    response = client.get(f"/api/events/{event_id}/seats")
    assert response.status_code == 200, response.text
    return {
        seat["label"]: seat["id"]
        for row in response.json()["rows"]
        for seat in row["seats"]
    }
