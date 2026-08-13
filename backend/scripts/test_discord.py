"""Test a live Discord bot connection end to end.

    cd backend
    .venv\\Scripts\\python.exe scripts\\test_discord.py

Verifies the token, lists the servers and channels the bot can actually read,
diagnoses the MESSAGE CONTENT intent, then reads recent messages and runs each
through the real scoring engine. Sends nothing.

--watch keeps polling until Ctrl+C, which is the useful mode: post in the
server yourself and watch the score appear.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.defaults import default_tuning  # noqa: E402
from app.integrations.discord import DiscordConnector, DiscordError  # noqa: E402
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

    print(f"\n{BAR}\n  Discord connection test\n{BAR}")

    if not settings.discord_bot_token:
        _fail(
            "DISCORD_BOT_TOKEN is not set.",
            "1. https://discord.com/developers/applications -> your app",
            "2. Bot tab -> Reset Token -> copy it",
            "3. Put it in backend\\.env as DISCORD_BOT_TOKEN=...",
            "",
            "This is NOT the Application ID or the Public Key. Those are",
            "public and cannot authenticate anything. The token is a password;",
            "do not paste it into a chat window.",
        )

    if not settings.pseudonym_salt:
        _fail(
            "PSEUDONYM_SALT is not set.",
            "Generate one and add it to backend\\.env:",
            '  python -c "import secrets; print(secrets.token_urlsafe(32))"',
        )

    connector = DiscordConnector(settings.discord_bot_token, settings.pseudonym_salt)

    # --- 1. credentials + intent ---
    print("\n  [1/3] Checking credentials and permissions...")
    status = await connector.health_check()
    if status.status != "connected":
        _fail(
            f"Could not connect: {status.error}",
            "If this says unauthorised, the token is wrong or was reset.",
            "Reset it again in the Bot tab and update backend\\.env.",
        )
    print(f"  [ok] {status.detail}")

    # --- 2. what can it actually see ---
    print("\n  [2/3] Servers and channels the bot can read...")
    try:
        sources = await connector.list_sources()
    except DiscordError as exc:
        _fail(f"Could not list servers: {exc}")

    if not sources:
        _fail(
            "The bot is not in any server.",
            "A server admin must invite it. Build the invite URL under",
            "OAuth2 -> URL Generator: scope 'bot', permissions View Channels +",
            "Read Message History + Send Messages.",
            "",
            "There is no way around this. Discord has no global search; a bot",
            "can only ever see servers it has been invited to.",
        )

    total_channels = 0
    for source in sources:
        if source.get("error"):
            print(f"    {source['guild']}: {source['error']}")
            continue
        names = ", ".join(f"#{c['name']}" for c in source["channels"][:8]) or "(none readable)"
        total_channels += len(source["channels"])
        print(f"    {source['guild']}: {names}")

    if total_channels == 0:
        _fail(
            "No readable text channels.",
            "The bot's role needs View Channel and Read Message History on at",
            "least one channel.",
        )

    # --- 3. score real messages ---
    print(f"\n  [3/3] Reading messages from {total_channels} channel(s)...")
    if watch:
        print(f"        Watching every {interval:g}s. Ctrl+C to stop.\n")
    else:
        print("        Reading the most recent messages.\n")

    config = default_tuning()
    seen = 0

    try:
        while True:
            try:
                messages = await connector.fetch_messages(limit=25)
            except DiscordError as exc:
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
        print("  No messages with readable content.\n")
        print("  Most likely causes, in order:")
        print("   1. MESSAGE CONTENT intent is off. Developer portal -> Bot ->")
        print("      Privileged Gateway Intents -> enable MESSAGE CONTENT.")
        print("      Without it Discord returns every message with empty text.")
        print("   2. The channels are empty, or everything in them is from bots.")
        print("   3. The bot's role cannot read the channels people actually use.")
    else:
        print(f"  Processed {seen} message(s). Nothing was sent.")
    print(f"{BAR}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true", help="keep polling until Ctrl+C")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between polls")
    args = parser.parse_args()
    asyncio.run(main(args.watch, args.interval))
