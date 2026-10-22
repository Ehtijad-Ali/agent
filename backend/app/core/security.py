"""Password hashing and session tokens (spec §38).

Argon2id for passwords: it is memory-hard, so an attacker with the hash cannot
trade cheap parallel hardware for speed the way they can against bcrypt or a
plain SHA. The parameters are argon2-cffi's defaults, which track the current
OWASP guidance.

Tokens are signed JWTs carrying the user id and role. They are handed to the
browser as an httpOnly cookie rather than returned in the response body: a
token readable from JavaScript is a token any XSS on the page can steal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
# Argon2Error is the base of VerifyMismatchError, InvalidHashError and
# VerificationError -- a malformed stored hash raises different ones
# depending on how it is malformed, and all of them mean "not a match".
from argon2.exceptions import Argon2Error

from app.core.config import get_settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
COOKIE_NAME = "signal_session"


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """False rather than raising: a bad password is an expected outcome, and
    a malformed stored hash must not 500 the login endpoint."""
    try:
        return _hasher.verify(hashed, plain)
    except (Argon2Error, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the stored hash predates the current parameters."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except (Argon2Error, ValueError):
        return False


def _secret() -> str:
    settings = get_settings()
    # jwt_secret is the dedicated one; fall back to secret_key so a deployment
    # that only set one of them still signs tokens rather than failing open.
    secret = settings.jwt_secret or settings.secret_key
    if not secret:
        raise RuntimeError(
            "JWT_SECRET (or SECRET_KEY) is not set; refusing to issue unsigned tokens."
        )
    return secret


def create_access_token(user_id: str, role: str) -> tuple[str, int]:
    """Returns (token, max_age_seconds)."""
    settings = get_settings()
    ttl = timedelta(minutes=settings.jwt_access_ttl_minutes or 30)
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM), int(ttl.total_seconds())


def decode_access_token(token: str) -> dict[str, Any] | None:
    """None for anything not currently valid -- expired, tampered or malformed.

    The caller turns that into a 401; it must never be able to mistake a
    failure for a valid anonymous session.
    """
    try:
        return jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
