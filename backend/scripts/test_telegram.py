"""Test a live Telegram bot connection end to end.

    cd backend
    .venv\\Scripts\\python.exe scripts\\test_telegram.py

Checks the token, reports privacy mode, then polls for messages and runs each
one through the real scoring engine so you can see exactly what Signal would
make of it. Sends nothing.

Add --watch to keep polling until Ctrl+C, which is the useful mode: post into
the group yourself and watch the score appear.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.defaults import default_tuning  # noqa: E402
from app.integrations.telegram import TelegramConnector, TelegramError  # noqa: E402
from app.services.scoring_service import score_message  # noqa: E402

BAR = "=" * 66


def _fail(message: str, *hints: str) -> None:
    print(f"\n  [X] {message}")
    for hint in hints:
        print(f"      {hint}")
    print()
    sys.exit(1)


async def main(watch: bool, interval: float) -> None:
    settings = get_settings()

    print(f"\n{BAR}\n  Telegram connection test\n{BAR}")

    if not settings.telegram_bot_token:
        _fail(
            "TELEGRAM_BOT_TOKEN is not set.",
            "1. Message @BotFather on Telegram, send /newbot",
            "2. Copy the token it gives you",
            "3. Put it in backend\\.env as TELEGRAM_BOT_TOKEN=...",
            "",
            "Do not paste the token into a chat window. It is a password.",
        )

    salt = settings.pseudonym_salt
    if not salt:
        # Author pseudonymisation refuses to run unsalted, and silently using a
        # throwaway would produce ids that change on every run.
        _fail(
            "PSEUDONYM_SALT is not set.",
            "Generate one and add it to backend\\.env:",
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"',
            "",
            "Set it once and never change it: it is what makes an author's",
            "pseudonym stable, which is how 'one reply per person' is enforced.",
        )

    connector = TelegramConnector(settings.telegram_bot_token, salt)

    # --- 1. credentials ---
    print("\n  [1/2] Checking credentials...")
    status = await connector.health_check()
    if status.status != "connected":
        _fail(
            f"Could not connect: {status.error}",
            "If this says unauthorised, the token is wrong or was revoked.",
            "Regenerate it with /token in BotFather.",
        )
    print(f"  [ok] {status.detail}")

    # --- 2. messages ---
    print("\n  [2/2] Polling for messages...")
    print("        Add the bot to a group, then post something in it.")
    if watch:
        print(f"        Watching every {interval:g}s. Ctrl+C to stop.\n")
    else:
        print("        Reading anything already queued.\n")

    config = default_tuning()
    seen = 0

    try:
        while True:
            try:
                messages = await connector.fetch_messages(limit=50)
            except TelegramError as exc:
                print(f"  [warn] {exc}")
                if not watch:
                    break
                await asyncio.sleep(interval)
                continue

            for msg in messages:
                seen += 1
                result = score_message(msg.message, config, msg.country, msg.posted_at)
                print(f"  {'-' * 64}")
                print(f"  from     {msg.author_pseudonym}  in {msg.community}")
                print(f"  message  {msg.message[:200]}")
                print(f"  score    {result.score}  ({result.intent}, {result.confidence})")
                if result.matched_keywords:
                    print(f"  matched  {', '.join(result.matched_keywords)}")
                if result.risk_flags:
                    print(f"  RISK     {', '.join(result.risk_flags)}  -> no reply drafted")
                if msg.source_url:
                    print(f"  source   {msg.source_url}")

            if not watch:
                break
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("\n  Stopped.")

    print(f"\n{BAR}")
    if seen == 0:
        print("  No messages received.\n")
        print("  Most likely causes, in order:")
        print("   1. Privacy mode is still ON. In BotFather: /setprivacy ->")
        print("      Disable, then REMOVE and RE-ADD the bot to the group.")
        print("      The change does not apply to groups it is already in.")
        print("   2. The bot is not in any group yet.")
        print("   3. Nothing has been posted since the bot joined. It cannot")
        print("      see messages sent before it was added.")
        print("   4. For channels, the bot must be an administrator.")
    else:
        print(f"  Processed {seen} message(s). Nothing was sent.")
    print(f"{BAR}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="keep polling until Ctrl+C")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between polls")
    args = parser.parse_args()
    asyncio.run(main(args.watch, args.interval))
