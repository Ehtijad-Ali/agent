"""User administration (spec §38).

Every route here is admin-only. An operator can work the inbox and approve
replies, but cannot create accounts, change roles or disable colleagues --
otherwise "two types of user" is a label rather than a boundary.

Accounts are deactivated, never deleted. Replies and activity entries reference
the person who approved them, and removing the row would strip the audit trail
of exactly the records that matter most.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.routes.auth import current_user, require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import ROLES, User

router = APIRouter(prefix="/users", tags=["users"])

MIN_PASSWORD = 10


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    isActive: bool
    createdAt: datetime | None = None
    lastLoginAt: datetime | None = None


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(default="", max_length=120)
    password: str = Field(min_length=MIN_PASSWORD)
    role: str = Field(default="operator")


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    role: str | None = None
    isActive: bool | None = None
    password: str | None = Field(default=None, min_length=MIN_PASSWORD)


def _out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        isActive=u.is_active,
        createdAt=u.created_at,
        lastLoginAt=u.last_login_at,
    )


def _check_role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"role must be one of: {', '.join(ROLES)}",
        )
    return role


def _admin_count(db: Session, exclude_id: str | None = None) -> int:
    """Active admins, optionally ignoring one row that is about to change."""
    q = select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True)
    )
    if exclude_id:
        q = q.where(User.id != exclude_id)
    return db.execute(q).scalar_one()


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> list[UserOut]:
    rows = db.execute(select(User).order_by(User.created_at)).scalars().all()
    return [_out(u) for u in rows]


@router.get("/roles")
def list_roles(_: User = Depends(current_user)) -> dict:
    """What the two roles actually mean, so the UI does not invent its own wording."""
    return {
        "roles": [
            {
                "id": "admin",
                "label": "Administrator",
                "description": "Full access, and the only role that can manage users.",
            },
            {
                "id": "operator",
                "label": "Operator",
                "description": (
                    "Can review conversations, approve and send replies, and run "
                    "scans. Cannot manage users."
                ),
            },
        ]
    }


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)
) -> UserOut:
    email = body.email.strip().lower()
    exists = db.execute(
        select(User).where(func.lower(User.email) == email)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")

    user = User(
        email=email,
        name=body.name.strip() or email.split("@")[0],
        password_hash=hash_password(body.password),
        role=_check_role(body.role),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user.")

    # Locking yourself out is the one mistake this screen can make that cannot
    # be undone from this screen.
    if user.id == actor.id:
        if body.isActive is False:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You cannot deactivate your own account."
            )
        if body.role is not None and body.role != "admin":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "You cannot remove your own admin access."
            )

    # Nor can the last administrator be removed by anyone, including another
    # admin: that would leave the platform with no one able to manage users.
    losing_admin = (body.isActive is False) or (body.role is not None and body.role != "admin")
    if user.role == "admin" and user.is_active and losing_admin:
        if _admin_count(db, exclude_id=user.id) == 0:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "This is the last administrator. Promote someone else first.",
            )

    if body.name is not None:
        user.name = body.name.strip()
    if body.role is not None:
        user.role = _check_role(body.role)
    if body.isActive is not None:
        user.is_active = body.isActive
    if body.password:
        user.password_hash = hash_password(body.password)

    db.commit()
    db.refresh(user)
    return _out(user)
