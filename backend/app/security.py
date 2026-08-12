"""Password hashing and token issuing.

Two token types, deliberately different:

* **Access token** -- a short-lived JWT. Stateless, so every request can be
  authorised without touching the database. Cannot be revoked before it expires,
  which is why it is short.
* **Refresh token** -- a long-lived opaque random string. Only its SHA-256 hash
  is stored, and it is rotated on every use, so a stolen refresh token stops
  working the moment the real owner refreshes. This is the revocable half.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings

# bcrypt only considers the first 72 bytes of a password. Silently truncating
# would mean two different long passwords could unlock the same account, so
# anything longer is rejected at the schema layer instead.
MAX_PASSWORD_BYTES = 72

ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of the wrong type."""


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # Malformed hash in the database -- treat as a failed login, never a 500.
        return False


# --------------------------------------------------------------------------- #
# Access tokens (JWT)
# --------------------------------------------------------------------------- #


def create_access_token(user_id: int, role: str, email: str) -> tuple[str, int]:
    """Return (token, seconds_until_expiry)."""
    expires_in = settings.access_token_ttl_minutes * 60
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Access token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Access token is not valid.") from exc

    if payload.get("type") != "access":
        raise TokenError("Wrong token type.")
    if not payload.get("sub"):
        raise TokenError("Access token is missing a subject.")
    return payload


# --------------------------------------------------------------------------- #
# Refresh tokens (opaque, stored hashed)
# --------------------------------------------------------------------------- #


def create_refresh_token() -> tuple[str, str, datetime]:
    """Return (plaintext, sha256_hash, expiry).

    Only the hash is persisted: a leaked database dump cannot be replayed as a
    session. SHA-256 rather than bcrypt is right here -- the token is 256 bits of
    CSPRNG output, so there is nothing to brute-force and refresh needs to be
    fast.
    """
    plaintext = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    return plaintext, hash_refresh_token(plaintext), expiry.replace(tzinfo=None)


def hash_refresh_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
