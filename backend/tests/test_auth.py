"""Authentication, authorisation and booking ownership."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import RefreshToken, User, UserRole
from app.security import hash_password, verify_password
from tests.conftest import seat_ids_by_label


def register(client, email="user@example.com", password="hunter2hunter2", name="Test User"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": name},
    )


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def test_password_hashes_are_salted_and_verifiable():
    first = hash_password("correct horse battery")
    second = hash_password("correct horse battery")

    assert first != second  # per-hash salt
    assert "correct horse battery" not in first
    assert verify_password("correct horse battery", first)
    assert not verify_password("wrong password", first)


def test_password_longer_than_bcrypts_limit_is_rejected(client):
    response = register(client, password="a" * 73)
    assert response.status_code == 422


def test_short_password_is_rejected(client):
    assert register(client, password="short").status_code == 422


def test_malformed_hash_fails_closed():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


# --------------------------------------------------------------------------- #
# Register and login
# --------------------------------------------------------------------------- #


def test_register_returns_a_session_and_never_the_hash(client):
    response = register(client)
    assert response.status_code == 201

    body = response.json()
    assert body["user"]["email"] == "user@example.com"
    assert body["user"]["role"] == "USER"
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["expires_in"] == settings.access_token_ttl_minutes * 60
    assert "password" not in str(body)
    assert "hash" not in str(body)


def test_registration_cannot_self_assign_admin(client, db):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "sneaky@example.com",
            "password": "hunter2hunter2",
            "full_name": "Sneaky",
            "role": "ADMIN",  # ignored: not part of the schema
        },
    )
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "USER"

    user = db.execute(
        select(User).where(User.email == "sneaky@example.com")
    ).scalar_one()
    assert user.role == UserRole.USER


def test_emails_are_case_insensitive_and_duplicates_are_409(client):
    assert register(client, email="Person@Example.com").status_code == 201

    duplicate = register(client, email="person@example.COM")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"


def test_login_succeeds_and_wrong_password_is_401(client):
    register(client)

    ok = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "hunter2hunter2"},
    )
    assert ok.status_code == 200
    assert ok.json()["tokens"]["access_token"]

    bad = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "not-the-password"},
    )
    assert bad.status_code == 401
    assert bad.json()["code"] == "unauthenticated"


def test_login_does_not_leak_whether_an_account_exists(client):
    register(client)

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "not-the-password"},
    )
    no_such_user = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "not-the-password"},
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json()["detail"] == no_such_user.json()["detail"]


def test_deactivated_account_cannot_log_in(client, db):
    register(client)
    user = db.execute(select(User).where(User.email == "user@example.com")).scalar_one()
    user.is_active = False
    db.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "hunter2hunter2"},
    )
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #


def test_me_requires_a_valid_token(client):
    tokens = register(client).json()["tokens"]

    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth_header("garbage")).status_code == 401

    ok = client.get("/api/auth/me", headers=auth_header(tokens["access_token"]))
    assert ok.status_code == 200
    assert ok.json()["email"] == "user@example.com"


def test_a_token_signed_with_another_secret_is_rejected(client):
    import jwt

    forged = jwt.encode(
        {"sub": "1", "role": "ADMIN", "email": "x@y.z", "type": "access"},
        "not-the-real-secret",
        algorithm="HS256",
    )
    assert client.get("/api/auth/me", headers=auth_header(forged)).status_code == 401


def test_refresh_token_rotates_and_the_old_one_stops_working(client):
    tokens = register(client).json()["tokens"]
    original = tokens["refresh_token"]

    # A second of separation, so the new access token is genuinely different.
    time.sleep(1)
    rotated = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert rotated.status_code == 200

    new_tokens = rotated.json()["tokens"]
    assert new_tokens["refresh_token"] != original
    assert client.get(
        "/api/auth/me", headers=auth_header(new_tokens["access_token"])
    ).status_code == 200

    replay = client.post("/api/auth/refresh", json={"refresh_token": original})
    assert replay.status_code == 401


def test_replaying_a_used_refresh_token_kills_every_session(client, db):
    """Reuse means the token probably leaked, so all sessions are revoked."""
    tokens = register(client).json()["tokens"]
    original = tokens["refresh_token"]

    rotated = client.post(
        "/api/auth/refresh", json={"refresh_token": original}
    ).json()["tokens"]

    # Attacker replays the already-spent token.
    assert client.post("/api/auth/refresh", json={"refresh_token": original}).status_code == 401

    # The legitimate rotated token is now dead too.
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    ).status_code == 401

    live = db.execute(
        select(RefreshToken).where(RefreshToken.revoked_at.is_(None))
    ).scalars().all()
    assert live == []


def test_refresh_tokens_are_only_stored_hashed(client, db):
    tokens = register(client).json()["tokens"]
    stored = db.execute(select(RefreshToken)).scalars().all()

    assert len(stored) == 1
    assert stored[0].token_hash != tokens["refresh_token"]
    assert len(stored[0].token_hash) == 64  # sha256 hex


def test_logout_revokes_only_that_session(client):
    first = register(client).json()["tokens"]
    second = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "hunter2hunter2"},
    ).json()["tokens"]

    assert client.post(
        "/api/auth/logout", json={"refresh_token": first["refresh_token"]}
    ).status_code == 204

    assert client.post(
        "/api/auth/refresh", json={"refresh_token": first["refresh_token"]}
    ).status_code == 401
    assert client.post(
        "/api/auth/refresh", json={"refresh_token": second["refresh_token"]}
    ).status_code == 200


def test_logout_all_revokes_every_session(client):
    tokens = register(client).json()["tokens"]
    other = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "hunter2hunter2"},
    ).json()["tokens"]

    response = client.post(
        "/api/auth/logout-all", headers=auth_header(tokens["access_token"])
    )
    assert response.status_code == 200
    assert response.json()["revoked_sessions"] == 2

    assert client.post(
        "/api/auth/refresh", json={"refresh_token": other["refresh_token"]}
    ).status_code == 401


def test_logging_out_an_unknown_token_is_not_an_error(client):
    assert client.post(
        "/api/auth/logout", json={"refresh_token": "never-existed"}
    ).status_code == 204


# --------------------------------------------------------------------------- #
# Authorisation on admin routes
# --------------------------------------------------------------------------- #


@pytest.fixture
def admin_token(client, db):
    register(client, email="boss@example.com", password="hunter2hunter2", name="Boss")
    user = db.execute(select(User).where(User.email == "boss@example.com")).scalar_one()
    user.role = UserRole.ADMIN
    db.commit()

    return client.post(
        "/api/auth/login",
        json={"email": "boss@example.com", "password": "hunter2hunter2"},
    ).json()["tokens"]["access_token"]


def test_admin_routes_reject_anonymous_and_plain_users(client, event_payload):
    assert client.post("/api/events", json=event_payload).status_code == 401

    user_token = register(client).json()["tokens"]["access_token"]
    forbidden = client.post(
        "/api/events", json=event_payload, headers=auth_header(user_token)
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "forbidden"


def test_admin_can_run_the_whole_admin_surface(client, admin_token, event_payload):
    headers = auth_header(admin_token)

    created = client.post("/api/events", json=event_payload, headers=headers)
    assert created.status_code == 201
    event_id = created.json()["id"]

    assert client.get(f"/api/events/{event_id}/summary", headers=headers).status_code == 200
    assert client.post(
        f"/api/events/{event_id}/seats/block",
        json={"seat_labels": ["A1"], "blocked": True},
        headers=headers,
    ).status_code == 200
    assert client.delete(f"/api/events/{event_id}", headers=headers).status_code == 204


def test_public_reads_stay_public(client, admin_token, event_payload):
    event = client.post(
        "/api/events", json=event_payload, headers=auth_header(admin_token)
    ).json()

    # No token at all -- a booker must be able to browse and see the seat map.
    assert client.get("/api/events").status_code == 200
    assert client.get(f"/api/events/{event['id']}").status_code == 200
    assert client.get(f"/api/events/{event['id']}/seats").status_code == 200


def test_admin_auth_can_be_switched_off_for_the_no_login_demo(
    client, event_payload, monkeypatch
):
    """The brief says the admin side needs no auth; the flag restores that."""
    monkeypatch.setattr(settings, "require_admin_auth", False)
    assert client.post("/api/events", json=event_payload).status_code == 201


# --------------------------------------------------------------------------- #
# Booking ownership
# --------------------------------------------------------------------------- #


def test_booking_without_signing_in_still_works(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    response = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Guest",
            "booker_email": "guest@example.com",
        },
    )
    assert response.status_code == 201
    assert response.json()["user_id"] is None


def test_booking_while_signed_in_links_it_to_the_account(client, created_event):
    session = register(client).json()
    seats = seat_ids_by_label(client, created_event["id"])

    booking = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"], seats["A2"]],
            "booker_name": "Test User",
            "booker_email": "user@example.com",
        },
        headers=auth_header(session["tokens"]["access_token"]),
    )
    assert booking.status_code == 201
    assert booking.json()["user_id"] == session["user"]["id"]

    mine = client.get(
        "/api/auth/me/bookings", headers=auth_header(session["tokens"]["access_token"])
    )
    assert mine.status_code == 200
    assert [b["reference"] for b in mine.json()] == [booking.json()["reference"]]


def test_my_bookings_never_shows_someone_elses(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])

    alice = register(client, email="alice@example.com").json()
    bob = register(client, email="bob@example.com").json()

    client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Alice",
            "booker_email": "alice@example.com",
        },
        headers=auth_header(alice["tokens"]["access_token"]),
    )

    assert (
        client.get(
            "/api/auth/me/bookings",
            headers=auth_header(bob["tokens"]["access_token"]),
        ).json()
        == []
    )


def test_a_stranger_cannot_cancel_an_account_booking(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])

    alice = register(client, email="alice@example.com").json()
    bob = register(client, email="bob@example.com").json()

    reference = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Alice",
            "booker_email": "alice@example.com",
        },
        headers=auth_header(alice["tokens"]["access_token"]),
    ).json()["reference"]

    # Knowing the reference is not enough once a booking has an owner.
    anonymous = client.post(f"/api/bookings/{reference}/cancel")
    assert anonymous.status_code == 403

    as_bob = client.post(
        f"/api/bookings/{reference}/cancel",
        headers=auth_header(bob["tokens"]["access_token"]),
    )
    assert as_bob.status_code == 403

    as_alice = client.post(
        f"/api/bookings/{reference}/cancel",
        headers=auth_header(alice["tokens"]["access_token"]),
    )
    assert as_alice.status_code == 200
    assert as_alice.json()["status"] == "CANCELLED"


def test_an_admin_can_cancel_anyones_booking(client, created_event, admin_token):
    seats = seat_ids_by_label(client, created_event["id"])
    alice = register(client, email="alice@example.com").json()

    reference = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Alice",
            "booker_email": "alice@example.com",
        },
        headers=auth_header(alice["tokens"]["access_token"]),
    ).json()["reference"]

    response = client.post(
        f"/api/bookings/{reference}/cancel", headers=auth_header(admin_token)
    )
    assert response.status_code == 200


def test_guest_bookings_stay_cancellable_by_reference(client, created_event):
    seats = seat_ids_by_label(client, created_event["id"])
    reference = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Guest",
            "booker_email": "guest@example.com",
        },
    ).json()["reference"]

    assert client.post(f"/api/bookings/{reference}/cancel").status_code == 200


def test_an_invalid_token_is_an_error_even_where_auth_is_optional(client, created_event):
    """A bad token must not be silently downgraded to 'guest'."""
    seats = seat_ids_by_label(client, created_event["id"])
    response = client.post(
        "/api/bookings",
        json={
            "event_id": created_event["id"],
            "seat_ids": [seats["A1"]],
            "booker_name": "Someone",
            "booker_email": "someone@example.com",
        },
        headers=auth_header("expired-or-forged"),
    )
    assert response.status_code == 401
