"""Platform users (spec §38: the app must not be open to everyone).

One row per person who can sign in. Passwords are never stored -- only an
Argon2 hash, which is what ``argon2-cffi`` is in requirements.txt for.

``last_login_at`` exists so an unused account is visible: an operator who has
not signed in for months is usually one who should be disabled.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.types import UtcDateTime

# Roles are stored rather than inferred so that adding a read-only reviewer
# later is a data change, not a migration.
ROLES = ("admin", "operator")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Case-insensitivity is enforced by storing the lowercased form; a UNIQUE
    # index on a mixed-case column would let "Sam@x.com" and "sam@x.com" coexist.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), nullable=False, default=lambda: datetime.now(UTC)
    )
    last_login_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} ({self.role})>"
