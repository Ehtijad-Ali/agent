r"""Sign the discovery Telegram account in, once, on the server.

    .venv\Scripts\python.exe -m pip install telethon
    .venv\Scripts\python.exe scripts\telegram_login.py

Needs TELEGRAM_API_ID and TELEGRAM_API_HASH in backend/.env (from
my.telegram.org -> API development tools). Telegram sends a login code to the
account; type it here. The resulting session file sits next to the backend and
is gitignored -- treat it like a password, because it is one.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.integrations.telegram_account import BACKEND_ROOT, telethon_available  # noqa: E402


async def main() -> None:
    settings = get_settings()
    if not (settings.telegram_api_id and settings.telegram_api_hash):
        print("[X] Set TELEGRAM_API_ID and TELEGRAM_API_HASH in backend/.env first.")
        sys.exit(1)
    if not telethon_available():
        print("[X] Telethon is not installed: .venv\\Scripts\\python.exe -m pip install telethon")
        sys.exit(1)

    from telethon import TelegramClient

    client = TelegramClient(
        str(BACKEND_ROOT / settings.telegram_session),
        int(settings.telegram_api_id),
        settings.telegram_api_hash,
    )
    await client.start()  # prompts for phone number, code and 2FA password
    me = await client.get_me()
    print(f"[ok] Signed in as @{me.username or me.id}. Restart the backend to use it.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
