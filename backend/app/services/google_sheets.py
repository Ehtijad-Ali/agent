"""Writing backlink-audit results back into the operator's Google Sheet.

Reading a sheet only needs it shared by link. Writing needs an identity Google
trusts, so this uses a **service account**: a robot Google account whose key
file sits on the server (GOOGLE_SERVICE_ACCOUNT_FILE). The operator shares the
sheet with that account's email as an Editor, and nothing else is reachable.

Uses the Sheets REST API directly with a signed JWT, so no Google SDK is needed.
"""

from __future__ import annotations

import json
import re
import time
from functools import lru_cache
from pathlib import Path

import httpx
import jwt

from app.core.config import get_settings

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
API = "https://sheets.googleapis.com/v4/spreadsheets"

_SHEET_ID = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_GID = re.compile(r"[#&?]gid=(\d+)")
_COLUMN = re.compile(r"^[A-Za-z]{1,3}$")

RESULT_LABELS = {
    "dofollow": "Dofollow",
    "nofollow": "Nofollow",
    "not_found": "No link",
    "error": "Error",
}


class SheetsError(RuntimeError):
    """Writing failed; the message is safe to show."""


@lru_cache
def _credentials() -> dict | None:
    path = get_settings().google_service_account_file
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("type") != "service_account" or not data.get("private_key"):
        return None
    return data


def configured() -> bool:
    return _credentials() is not None


def service_account_email() -> str | None:
    creds = _credentials()
    return creds.get("client_email") if creds else None


async def _access_token(client: httpx.AsyncClient) -> str:
    creds = _credentials()
    if creds is None:
        raise SheetsError(
            "Writing to Google Sheets is not set up: GOOGLE_SERVICE_ACCOUNT_FILE is missing or invalid."
        )
    token_uri = creds.get("token_uri", "https://oauth2.googleapis.com/token")
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": creds["client_email"], "scope": SCOPE, "aud": token_uri, "iat": now, "exp": now + 3600},
        creds["private_key"],
        algorithm="RS256",
    )
    response = await client.post(
        token_uri,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
    )
    if response.status_code != 200:
        raise SheetsError("Google rejected the service account key. Check the key file on the server.")
    return response.json()["access_token"]


async def _tab_title(client: httpx.AsyncClient, sheet_id: str, gid: str | None, headers: dict) -> str:
    response = await client.get(
        f"{API}/{sheet_id}", params={"fields": "sheets.properties(sheetId,title)"}, headers=headers
    )
    if response.status_code in (403, 404):
        raise SheetsError(
            f"Signal cannot open this sheet. Share it with {service_account_email()} as an Editor."
        )
    if response.status_code != 200:
        raise SheetsError(f"Google Sheets returned HTTP {response.status_code}.")
    sheets = [s["properties"] for s in response.json().get("sheets", [])]
    if not sheets:
        raise SheetsError("The spreadsheet has no tabs.")
    if gid is not None:
        for props in sheets:
            if str(props.get("sheetId")) == gid:
                return props["title"]
    return sheets[0]["title"]


async def write_column(sheet_url: str, column: str, values: list[tuple[int, str]]) -> int:
    """Write ``(row, value)`` pairs into one column of the linked tab.

    Only the given cells change; the URLs and anything else stay untouched.
    Returns how many cells were written.
    """
    match = _SHEET_ID.search(sheet_url or "")
    if not match:
        raise SheetsError("That is not a Google Sheets link.")
    if not _COLUMN.match(column or ""):
        raise SheetsError(f"'{column}' is not a column letter.")
    if not values:
        return 0
    gid = _GID.search(sheet_url)

    async with httpx.AsyncClient(timeout=30) as client:
        token = await _access_token(client)
        headers = {"Authorization": f"Bearer {token}"}
        title = await _tab_title(client, match.group(1), gid.group(1) if gid else None, headers)
        quoted = "'" + title.replace("'", "''") + "'"
        col = column.upper()
        data = [{"range": f"{quoted}!{col}{row}", "values": [[value]]} for row, value in values]
        response = await client.post(
            f"{API}/{match.group(1)}/values:batchUpdate",
            json={"valueInputOption": "RAW", "data": data},
            headers=headers,
        )
    if response.status_code == 403:
        raise SheetsError(
            f"Signal can read but not edit this sheet. Share it with {service_account_email()} as an Editor."
        )
    if response.status_code != 200:
        raise SheetsError(f"Google Sheets refused the update (HTTP {response.status_code}).")
    return int(response.json().get("totalUpdatedCells", len(data)))
