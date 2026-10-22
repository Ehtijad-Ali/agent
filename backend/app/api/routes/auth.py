"""Sign-in, sign-out and "who am I" (spec §38).

The session token travels as an httpOnly cookie. The browser attaches it to
same-origin requests automatically, so the frontend never handles the token --
which means an XSS on any page cannot read it.

Login failures are deliberately indistinguishable: a wrong password, an unknown
address and a disabled account all return the same message. Saying which one it
was tells an attacker whether an address is worth attacking.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    COOKIE_NAME,
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.db.session import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID = "Email or password is incorrect."


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str


def _as_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, role=user.role)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """The signed-in user, or 401.

    Every protected route depends on this. It re-reads the user on each request
    rather than trusting the token's claims alone, so disabling an account takes
    effect immediately instead of whenever the token happens to expire.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Sign in again.")

    user = db.get(User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is no longer active.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required.")
    return user


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> UserOut:
    email = body.email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()

    # Verify even when the user is missing, against a throwaway hash, so the
    # response time does not reveal whether the address exists.
    stored = user.password_hash if user else hash_password("timing-equaliser")
    ok = verify_password(body.password, stored)

    if user is None or not ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    user.last_login_at = datetime.now(UTC)
    db.commit()

    token, max_age = create_access_token(user.id, user.role)
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        # Secure only in production: a Secure cookie is dropped over plain HTTP,
        # which would make local development impossible to sign into.
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )
    return _as_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return _as_out(user)
