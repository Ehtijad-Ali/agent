r"""Sign in the dedicated Telegram account once and print its session string.

Run on the server (Telegram may be blocked on some home networks):

    cd /opt/signal/app/backend
    .venv/bin/python scripts/telegram_login.py

You need the account's phone number and the API id/hash from
https://my.telegram.org -> API development tools. Telegram sends a login code
to the account's Telegram app; type it here (and the 2FA password if set).

Put the printed string in backend/.env as TELEGRAM_SESSION, together with
TELEGRAM_API_ID and TELEGRAM_API_HASH, then restart the API. The string is a
login: keep it secret, never commit it.
"""

from __future__ import annotations

import asyncio
import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(input("API id: ").strip())
    api_hash = input("API hash: ").strip()
    phone = input("Phone number (with country code, e.g. +44...): ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start(
        phone=phone,
        code_callback=lambda: input("Login code from Telegram: ").strip(),
        password=lambda: getpass.getpass("Two-step verification password (blank if none): "),
    )
    me = await client.get_me()
    print(f"\nSigned in as {me.first_name} (@{me.username}).")
    print("\nTELEGRAM_SESSION=" + client.session.save())
    print("\nAdd that line, TELEGRAM_API_ID and TELEGRAM_API_HASH to backend/.env, then restart the API.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
