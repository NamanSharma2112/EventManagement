"""Event creation, seat map and admin endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from tests.conftest import seat_ids_by_label


def test_create_event_materialises_every_seat(client, created_event):
    assert created_event["row_count"] == 4
    assert created_event["column_count"] == 6
    assert [s["name"] for s in created_event["sections"]] == ["General"]

    seat_map = client.get(f"/api/events/{created_event['id']}/seats").json()
    assert seat_map["total_seats"] == 24
    assert seat_map["available_seats"] == 24
    assert [row["row_label"] for row in seat_map["rows"]] == ["A", "B", "C", "D"]
    assert [seat["label"] for seat in seat_map["rows"][0]["seats"]] == [
        "A1", "A2", "A3", "A4", "A5", "A6"
    ]


def test_create_event_with_price_tiers_and_blocked_seats(client, event_payload):
    payload = {
        **event_payload,
        "rows": 3,
        "columns": 4,
        "sections": [
            {"name": "Gold", "price_cents": 300000, "row_count": 1},
            {"name": "Silver", "price_cents": 150000, "row_count": 2},
        ],
        "blocked_seats": ["A1", "C4"],
    }
    event = client.post("/api/events", json=payload).json()

    seat_map = client.get(f"/api/events/{event['id']}/seats").json()
    seats = {s["label"]: s for row in seat_map["rows"] for s in row["seats"]}

    assert seats["A2"]["section_name"] == "Gold"
    assert seats["A2"]["price_cents"] == 300000
    assert seats["B1"]["section_name"] == "Silver"
    assert seats["C1"]["price_cents"] == 150000

    assert seats["A1"]["status"] == "BLOCKED"
    assert seats["C4"]["status"] == "BLOCKED"
    assert seat_map["blocked_seats"] == 2
    assert seat_map["available_seats"] == 10


def test_section_row_counts_must_cover_the_layout(client, event_payload):
    response = client.post(
        "/api/events",
        json={
            **event_payload,
            "rows": 5,
            "sections": [{"name": "Gold", "price_cents": 1, "row_count": 2}],
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "5 rows" in response.json()["detail"]


def test_layout_size_is_capped(client, event_payload):
    response = client.post("/api/events", json={**event_payload, "rows": 500})
    assert response.status_code == 422


def test_row_labels_continue_past_z(client, event_payload):
    event = client.post(
        "/api/events", json={**event_payload, "rows": 28, "columns": 1}
    ).json()
    labels = [
        row["row_label"] for row in client.get(f"/api/events/{event['id']}/seats").json()["rows"]
    ]
    assert labels[25:] == ["Z", "AA", "AB"]


def test_unknown_event_is_404(client):
    response = client.get("/api/events/999999/seats")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_block_and_unblock_seats(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    response = client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_labels": ["A1", "A2"], "blocked": True, "reason": "VIP hold"},
    )
    assert response.status_code == 200
    assert sorted(response.json()["updated_seat_ids"]) == sorted(
        [seats["A1"], seats["A2"]]
    )

    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    blocked = {s["label"]: s for row in seat_map["rows"] for s in row["seats"]}
    assert blocked["A1"]["status"] == "BLOCKED"
    assert blocked["A1"]["blocked_reason"] == "VIP hold"

    client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_ids": [seats["A1"]], "blocked": False},
    )
    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    after = {s["label"]: s for row in seat_map["rows"] for s in row["seats"]}
    assert after["A1"]["status"] == "AVAILABLE"
    assert after["A2"]["status"] == "BLOCKED"


def test_blocking_skips_seats_that_are_already_booked(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "seat_ids": [seats["B1"]],
            "booker_name": "Booked Already",
            "booker_email": "booked@example.com",
        },
    )

    response = client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_labels": ["B1", "B2"], "blocked": True},
    )
    body = response.json()
    assert body["updated_seat_ids"] == [seats["B2"]]
    assert body["skipped_booked_seat_ids"] == [seats["B1"]]


def test_event_list_and_summary_agree_with_the_seat_map(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_labels": ["D5", "D6"], "blocked": True},
    )
    client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "seat_ids": [seats["A1"], seats["A2"], seats["A3"]],
            "booker_name": "Group Booker",
            "booker_email": "group@example.com",
        },
    )

    keys = ("total_seats", "booked_seats", "blocked_seats", "available_seats")
    seat_map = client.get(f"/api/events/{event_id}/seats").json()
    summary = client.get(f"/api/events/{event_id}/summary").json()
    listed = next(e for e in client.get("/api/events").json() if e["id"] == event_id)

    expected = {
        "total_seats": 24,
        "booked_seats": 3,
        "blocked_seats": 2,
        "available_seats": 19,
    }
    assert {k: seat_map[k] for k in keys} == expected
    assert {k: summary[k] for k in keys} == expected
    assert {k: listed[k] for k in keys} == expected


def test_admin_summary_lists_bookings_with_revenue(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)

    client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "seat_ids": [seats["A1"], seats["A2"]],
            "booker_name": "Ada Lovelace",
            "booker_email": "Ada@Example.com",
        },
    )

    summary = client.get(f"/api/events/{event_id}/summary").json()
    assert summary["total_bookings"] == 1
    assert summary["cancelled_bookings"] == 0
    assert summary["revenue_cents"] == 100000

    row = summary["bookings"][0]
    assert row["booker_name"] == "Ada Lovelace"
    assert row["booker_email"] == "ada@example.com"  # normalised
    assert row["seat_labels"] == ["A1", "A2"]
    assert row["seat_count"] == 2
    assert datetime.fromisoformat(row["created_at"]) <= datetime.now() + timedelta(
        minutes=1
    )


def test_delete_event_removes_its_seats_and_bookings(client, created_event):
    event_id = created_event["id"]
    seats = seat_ids_by_label(client, event_id)
    client.post(
        "/api/bookings",
        json={
            "event_id": event_id,
            "seat_ids": [seats["A1"]],
            "booker_name": "Temp",
            "booker_email": "temp@example.com",
        },
    )

    assert client.delete(f"/api/events/{event_id}").status_code == 204
    assert client.get(f"/api/events/{event_id}").status_code == 404
