"""FastAPI dependencies for authentication and authorisation."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .errors import AuthError, PermissionError_
from .models import User
from .security import TokenError, decode_access_token

# auto_error=False so a missing header reaches our own handler and produces the
# project's error envelope rather than FastAPI's bare {"detail": ...}.
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access token>")


def _user_from_credentials(
    credentials: HTTPAuthorizationCredentials | None, db: Session
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise AuthError(str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthError("The account on this token no longer exists.")
    if not user.is_active:
        raise AuthError("This account has been deactivated.")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Require a signed-in account. 401 when the token is missing or bad."""
    user = _user_from_credentials(credentials, db)
    if user is None:
        raise AuthError("Sign in to continue.")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Attach the account when one is signed in, without requiring it.

    This is what keeps guest booking working: the brief says users book without
    a login, so a booking request with no token is still valid -- it just does
    not get an owner.

    A token that is *present but invalid* is still an error. Silently treating a
    bad token as "guest" would hide expiry from the client.
    """
    return _user_from_credentials(credentials, db)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise PermissionError_("This action requires an admin account.")
    return user


def admin_guard(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Admin gate that can be switched off for a no-login demo.

    The brief states the admin side needs no authentication. `REQUIRE_ADMIN_AUTH`
    defaults to true because an open delete-event endpoint is not something to
    ship, but setting it false restores the brief's behaviour exactly.
    """
    if not settings.require_admin_auth:
        # Still attach the account when one is present, so audit-ish fields and
        # the UI can tell who is acting.
        try:
            return _user_from_credentials(credentials, db)
        except AuthError:
            return None

    user = _user_from_credentials(credentials, db)
    if user is None:
        raise AuthError("Sign in as an admin to continue.")
    if not user.is_admin:
        raise PermissionError_("This action requires an admin account.")
    return user
