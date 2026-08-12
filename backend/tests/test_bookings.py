"""Booking behaviour: happy path, conflicts, atomicity, cancellation."""

from __future__ import annotations

from tests.conftest import seat_ids_by_label


def _book(client, event_id, seat_ids, name="Booker", email="booker@example.com"):
    return client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "seat_ids": seat_ids,
            "booker_name": name,
            "booker_email": email,
        },
    )


def test_booking_multiple_seats_succeeds(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    response = _book(client, event_id, [seats["A1"], seats["A2"], seats["A3"]])
    assert response.status_code == 201, response.text

    booking = response.json()
    assert booking["status"] == "CONFIRMED"
    assert booking["reference"].startswith("BK-")
    assert [s["label"] for s in booking["seats"]] == ["A1", "A2", "A3"]
    assert booking["total_amount_cents"] == 150000

    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    booked = {
        s["label"] for row in seat_map["rows"] for s in row["seats"] if s["status"] == "BOOKED"
    }
    assert booked == {"A1", "A2", "A3"}


def test_booked_seat_is_rejected_with_409(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    assert _book(client, event_id, [seats["A1"]]).status_code == 201

    response = _book(client, event_id, [seats["A1"]], email="second@example.com")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "seat_unavailable"
    assert body["conflicting_seats"] == [
        {"seat_id": seats["A1"], "label": "A1", "reason": "Seat has already been booked."}
    ]


def test_multi_seat_booking_is_all_or_nothing(client, created_event):
    """One taken seat must fail the whole request -- no partial booking."""
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    _book(client, event_id, [seats["B2"]], email="first@example.com")

    response = _book(
        client,
        event_id,
        [seats["B1"], seats["B2"], seats["B3"]],
        email="second@example.com",
    )
    assert response.status_code == 409
    assert [c["label"] for c in response.json()["conflicting_seats"]] == ["B2"]

    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    statuses = {s["label"]: s["status"] for row in seat_map["rows"] for s in row["seats"]}
    assert statuses["B1"] == "AVAILABLE"  # not partially booked
    assert statuses["B2"] == "BOOKED"
    assert statuses["B3"] == "AVAILABLE"
    assert seat_map["booked_seats"] == 1

    summary = client.get(f"/api/events/{event_id}/summary").json()
    assert summary["total_bookings"] == 1


def test_blocked_seat_cannot_be_booked(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)
    client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_ids": [seats["C1"]], "blocked": True, "reason": "Out of service"},
    )

    response = _book(client, event_id, [seats["C1"], seats["C2"]])
    assert response.status_code == 409
    assert response.json()["conflicting_seats"][0]["reason"] == "Out of service"

    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    statuses = {s["label"]: s["status"] for row in seat_map["rows"] for s in row["seats"]}
    assert statuses["C2"] == "AVAILABLE"


def test_seat_from_another_event_is_rejected(client, created_event, event_payload):
    other = client.post("/api/events", json={**event_payload, "name": "Other"}).json()
    other_seats = seat_ids_by_label(client, other["id"])

    response = _book(client, created_event["id"], [other_seats["A1"]])
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_unknown_event_is_404(client):
    response = _book(client, 999999, [1])
    assert response.status_code == 404


def test_duplicate_seat_ids_are_collapsed(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    response = _book(client, event_id, [seats["A1"], seats["A1"], seats["A2"]])
    assert response.status_code == 201
    assert len(response.json()["seats"]) == 2


def test_empty_seat_list_is_rejected(client, created_event):
    assert _book(client, created_event["id"], []).status_code == 422


def test_invalid_email_is_rejected(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    response = _book(client, created_event["id"], [seats["A1"]], email="not-an-email")
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_booking_size_is_capped(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    response = _book(client, created_event["id"], list(seats.values())[:11])
    assert response.status_code == 422


def test_booking_can_be_looked_up_by_reference(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    reference = _book(client, created_event["id"], [seats["A1"]]).json()["reference"]

    response = client.get(f"/api/bookings/{reference}")
    assert response.status_code == 200
    assert response.json()["reference"] == reference
    assert response.json()["event_name"] == created_event["name"]

    assert client.get("/api/bookings/BK-NOPE").status_code == 404


def test_cancelling_a_booking_releases_its_seats(client, created_event):
    """Cancelled rows drop out of the unique index, so the seats come back."""
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    reference = _book(client, event_id, [seats["A1"], seats["A2"]]).json()["reference"]

    cancelled = client.post(f"/api/bookings/{reference}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancelled_at"] is not None

    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    statuses = {s["label"]: s["status"] for row in seat_map["rows"] for s in row["seats"]}
    assert statuses["A1"] == "AVAILABLE"
    assert statuses["A2"] == "AVAILABLE"
    assert seat_map["booked_seats"] == 0

    # And the freed seat really can be booked again.
    assert _book(client, event_id, [seats["A1"]], email="new@example.com").status_code == 201

    summary = client.get(f"/api/events/{event_id}/summary").json()
    assert summary["cancelled_bookings"] == 1
    assert summary["total_bookings"] == 1
    assert summary["revenue_cents"] == 50000  # cancelled booking excluded


def test_cancelling_twice_is_a_409(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    reference = _book(client, created_event["id"], [seats["A1"]]).json()["reference"]

    assert client.post(f"/api/bookings/{reference}/cancel").status_code == 200
    repeat = client.post(f"/api/bookings/{reference}/cancel")
    assert repeat.status_code == 409
    assert repeat.json()["code"] == "invalid_booking_state"
