r"""Create or update a platform user.

    .venv\Scripts\python.exe scripts\create_user.py --email you@example.com --role admin

The password is prompted for, never passed as an argument: anything on the
command line lands in shell history and in the process list, where other users
on the machine can read it. Pass --password only for non-interactive setup.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.models import ROLES, User  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--role", default="admin", choices=list(ROLES))
    parser.add_argument("--password", default=None, help="skip the prompt (CI/setup only)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if len(password) < 10:
        print("[X] Use at least 10 characters.")
        sys.exit(1)

    if not init_db():
        print("[X] No database configured. Set DATABASE_URL in backend/.env.")
        sys.exit(1)

    email = args.email.strip().lower()
    with session_scope() as db:
        existing = db.execute(
            select(User).where(func.lower(User.email) == email)
        ).scalar_one_or_none()
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = args.role
            existing.is_active = True
            if args.name:
                existing.name = args.name
            print(f"[ok] Updated {email} (role {args.role}).")
        else:
            db.add(
                User(
                    email=email,
                    name=args.name or email.split("@")[0],
                    password_hash=hash_password(password),
                    role=args.role,
                )
            )
            print(f"[ok] Created {email} (role {args.role}).")
        # session_scope() hands back a plain Session and leaves the transaction
        # to the caller -- exiting the `with` closes it WITHOUT committing, so
        # this commit is what actually persists the row.
        db.commit()


if __name__ == "__main__":
    main()
