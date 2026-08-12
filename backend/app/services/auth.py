"""Registration, login, refresh rotation and logout."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..errors import AuthError, ConflictError, NotFoundError
from ..models import RefreshToken, RevokedReason, User, UserRole
from ..schemas import LoginRequest, RegisterRequest, TokenPair
from ..security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

logger = logging.getLogger("app.auth")


def normalise_email(email: str) -> str:
    return email.strip().lower()


def register(db: Session, payload: RegisterRequest) -> User:
    """Create a USER account. Role is never taken from the request body."""
    email = normalise_email(str(payload.email))

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role=UserRole.USER,  # deliberately not client-controllable
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The unique index is the authority here, not a prior SELECT -- two
        # simultaneous registrations for one address cannot both succeed.
        raise ConflictError("An account with that email already exists.") from exc

    db.refresh(user)
    return user


def authenticate(db: Session, payload: LoginRequest) -> User:
    email = normalise_email(str(payload.email))
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    # Same message and roughly the same work either way, so the response cannot
    # be used to enumerate which addresses have accounts.
    if user is None:
        verify_password(payload.password, _DUMMY_HASH)
        raise AuthError("Email or password is incorrect.")
    if not verify_password(payload.password, user.password_hash):
        raise AuthError("Email or password is incorrect.")
    if not user.is_active:
        raise AuthError("This account has been deactivated.")

    return user


# A real bcrypt hash of a random value, compared against when the account does
# not exist so that a missing user costs the same time as a wrong password.
_DUMMY_HASH = hash_password("not-a-real-password-placeholder")


def issue_tokens(db: Session, user: User) -> TokenPair:
    access_token, expires_in = create_access_token(user.id, user.role.value, user.email)
    plaintext, token_hash, expires_at = create_refresh_token()

    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()

    return TokenPair(
        access_token=access_token,
        refresh_token=plaintext,
        expires_in=expires_in,
    )


def refresh(db: Session, refresh_token: str) -> tuple[User, TokenPair]:
    """Exchange a refresh token for a new pair, revoking the one presented."""
    record = db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token)
        )
    ).scalar_one_or_none()

    if record is None:
        raise AuthError("Refresh token is not valid.")

    now = datetime.now()
    if record.revoked_at is not None:
        if record.revoked_reason == RevokedReason.ROTATED:
            # Someone is replaying a token the real owner already spent. That
            # is the signature of a stolen token, so every session for the
            # account is dropped and both parties must sign in again.
            _revoke_all_for_user(db, record.user_id, RevokedReason.REUSE_DETECTED)
            db.commit()
            logger.warning(
                "Reused rotated refresh token for user %s; revoked all sessions",
                record.user_id,
            )
            raise AuthError(
                "Refresh token has already been used. Please sign in again."
            )
        # Revoked by an explicit logout (or a previous reuse sweep). Just a
        # stale client -- reject this one and leave other devices alone.
        raise AuthError("Refresh token is no longer valid. Please sign in again.")
    if record.expires_at <= now:
        raise AuthError("Refresh token has expired. Please sign in again.")

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        raise AuthError("This account is no longer active.")

    record.revoked_at = now
    record.revoked_reason = RevokedReason.ROTATED
    db.flush()

    return user, issue_tokens(db, user)


def logout(db: Session, refresh_token: str) -> None:
    """Revoke a single session. Unknown tokens are a no-op, not an error."""
    record = db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token)
        )
    ).scalar_one_or_none()

    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now()
        record.revoked_reason = RevokedReason.LOGOUT
        db.commit()


def logout_everywhere(db: Session, user_id: int) -> int:
    count = _revoke_all_for_user(db, user_id, RevokedReason.LOGOUT)
    db.commit()
    return count


def _revoke_all_for_user(db: Session, user_id: int, reason: RevokedReason) -> int:
    records = (
        db.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now()
    for record in records:
        record.revoked_at = now
        record.revoked_reason = reason
    return len(records)


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("Account not found.")
    return user


def ensure_bootstrap_admin(db: Session) -> None:
    """Create the seeded admin on first startup, so a fresh install has a way in.

    Skipped entirely once any account with that email exists, so it can never
    reset a password an operator has changed.
    """
    if not settings.create_bootstrap_admin:
        return

    email = normalise_email(settings.bootstrap_admin_email)
    exists = db.execute(select(User.id).where(User.email == email)).scalar_one_or_none()
    if exists is not None:
        return

    db.add(
        User(
            email=email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            full_name=settings.bootstrap_admin_name,
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    try:
        db.commit()
        logger.info("Created bootstrap admin account %s", email)
    except IntegrityError:
        db.rollback()  # another worker won the race; fine
