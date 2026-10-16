"""Clear the outbound reply ledger so a send can be tested again.

    cd backend
    .venv\\Scripts\\python.exe scripts\\reset_replies.py --list
    .venv\\Scripts\\python.exe scripts\\reset_replies.py --author user_13bf
    .venv\\Scripts\\python.exe scripts\\reset_replies.py --all

WHY THIS EXISTS
---------------
"One reply per person, ever" is one of the five non-negotiable rules, enforced
by a UNIQUE constraint on (platform, author_pseudonym) in reply_sends. That is
correct in production and is NOT relaxed anywhere in the application.

It does, however, make the send path a one-shot on any given author, which
makes testing it impossible after the first go. This script is the testing
escape hatch: it removes ledger rows so the same author can be replied to
again, and it refuses to run outside development.

WHAT IT CANNOT DO
-----------------
It cannot unsend anything. Messages already posted stay public on the platform.
Clearing the ledger only lets the app post *another* one, so anyone the ledger
is cleared for may receive a second reply. That is acceptable in a throwaway
test server and is not acceptable anywhere else -- which is why the environment
check is not optional.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.session import session_scope  # noqa: E402
from app.models import ActivityEntry, Conversation, ReplySend  # noqa: E402

BAR = "=" * 66


def _guard() -> None:
    settings = get_settings()
    if settings.environment != "development":
        print(
            f"\n  [X] ENVIRONMENT is '{settings.environment}'. This script only "
            "runs in development.\n"
            "      Clearing the ledger in production would let real people be "
            "replied to twice.\n"
        )
        sys.exit(1)
    if not settings.database_url:
        print("\n  [X] DATABASE_URL is not set; there is no ledger to clear.\n")
        sys.exit(1)


def _list(db) -> None:
    rows = db.execute(select(ReplySend).order_by(ReplySend.sent_at.desc())).scalars().all()
    print(f"\n{BAR}\n  Reply ledger: {len(rows)} row(s)\n{BAR}")
    if not rows:
        print("\n  Nothing sent yet. Any author may be replied to.\n")
        return
    for row in rows:
        print(f"\n  {row.author_pseudonym} on {row.platform}")
        print(f"    sent        {row.sent_at.isoformat()}")
        print(f"    message id  {row.external_message_id}")
        print(f"    text        {row.text[:70]}...")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="show the ledger and exit")
    parser.add_argument("--author", help="clear one author's pseudonym")
    parser.add_argument("--all", action="store_true", help="clear every row")
    parser.add_argument(
        "--keep-status",
        action="store_true",
        help="leave conversations at 'sent' instead of reopening them to 'approved'",
    )
    args = parser.parse_args()

    _guard()
    db = session_scope()
    try:
        if args.list or not (args.author or args.all):
            _list(db)
            if not (args.author or args.all):
                print("  Pass --author <pseudonym> or --all to clear.\n")
            return

        stmt = select(ReplySend)
        if args.author:
            stmt = stmt.where(ReplySend.author_pseudonym == args.author)
        targets = db.execute(stmt).scalars().all()

        if not targets:
            print(f"\n  Nothing to clear for {args.author or 'any author'}.\n")
            return

        print(f"\n{BAR}\n  Clearing {len(targets)} ledger row(s)\n{BAR}\n")
        print("  Note: messages already posted stay public. This only allows")
        print("  another reply to be sent.\n")

        conversation_ids = {row.conversation_id for row in targets}
        authors = sorted({row.author_pseudonym for row in targets})

        for row in targets:
            print(f"  - {row.author_pseudonym} ({row.external_message_id})")
            db.execute(delete(ReplySend).where(ReplySend.id == row.id))

        reopened = 0
        if not args.keep_status:
            for conversation_id in conversation_ids:
                conversation = db.get(Conversation, conversation_id)
                if conversation is not None and conversation.status == "sent":
                    conversation.status = "approved"
                    reopened += 1

        db.add(
            ActivityEntry(
                actor="system",
                action="reply ledger cleared",
                item=", ".join(authors),
                before=f"{len(targets)} send(s) recorded",
                after="cleared for testing",
            )
        )
        db.commit()

        print(f"\n  Cleared {len(targets)} row(s); reopened {reopened} conversation(s).")
        print("  Restart is not needed -- the check reads the table on each send.\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
