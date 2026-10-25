"""Health endpoints (spec §39).

These report what is actually reachable rather than always returning ok. During
Phase 1 most subsystems are intentionally absent, and the response says so
instead of pretending otherwise.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.core.config import get_settings
from app.integrations.base import FACEBOOK_REASON
from app.integrations.discord import DiscordConnector
from app.integrations.telegram import TelegramConnector

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.environment,
        "subsystems": {
            "engine": "ok",
            "database": "configured" if settings.has_database else "not_configured",
            "redis": "configured" if settings.redis_url else "not_configured",
            "ollama": "configured" if settings.ollama_model else "not_configured",
        },
    }


@router.get("/ai")
async def health_ai() -> dict:
    """Probe Ollama. A missing model is reported, never guessed at."""
    settings = get_settings()
    if not settings.ollama_model:
        return {
            "status": "not_configured",
            "detail": "OLLAMA_MODEL is unset; AI analysis is disabled.",
        }
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            available = [m["name"] for m in response.json().get("models", [])]
        return {
            "status": "ok" if settings.ollama_model in available else "model_missing",
            "configuredModel": settings.ollama_model,
            "availableModels": available,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return {
            "status": "unreachable",
            "baseUrl": settings.ollama_base_url,
            "detail": str(exc)[:200],
        }


@router.get("/platforms")
async def health_platforms() -> dict:
    """Spec §29: credential *status* only. Tokens never leave this process.

    Telegram is probed for real rather than reported as "configured" just
    because a token string exists -- a revoked token would otherwise look
    healthy right up until ingestion silently returned nothing.
    """
    settings = get_settings()
    platforms: list[dict] = []

    if settings.telegram_bot_token and settings.pseudonym_salt:
        connector = TelegramConnector(settings.telegram_bot_token, settings.pseudonym_salt)
        status = await connector.health_check()
        platforms.append(
            {
                "platform": "telegram",
                "status": status.status,
                "lastChecked": status.last_checked.isoformat() if status.last_checked else None,
                "error": status.error,
                "detail": status.detail,
            }
        )
    else:
        missing = "TELEGRAM_BOT_TOKEN" if not settings.telegram_bot_token else "PSEUDONYM_SALT"
        platforms.append(
            {
                "platform": "telegram",
                "status": "not_connected",
                "lastChecked": None,
                "error": None,
                "detail": f"{missing} is not set.",
            }
        )

    if settings.discord_bot_token and settings.pseudonym_salt:
        connector = DiscordConnector(settings.discord_bot_token, settings.pseudonym_salt)
        status = await connector.health_check()
        platforms.append(
            {
                "platform": "discord",
                "status": status.status,
                "lastChecked": status.last_checked.isoformat() if status.last_checked else None,
                "error": status.error,
                "detail": status.detail,
            }
        )
    else:
        missing = "DISCORD_BOT_TOKEN" if not settings.discord_bot_token else "PSEUDONYM_SALT"
        platforms.append(
            {
                "platform": "discord",
                "status": "not_connected",
                "lastChecked": None,
                "error": None,
                "detail": f"{missing} is not set.",
            }
        )

    # Discovery connectors: reported as connected only when credentials exist;
    # the live check is on /api/platforms/status/{platform}.
    for name, ok, how in (
        ("reddit", settings.reddit_client_id and settings.reddit_client_secret,
         "Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET on the server."),
        ("youtube", settings.youtube_api_key, "Set YOUTUBE_API_KEY on the server."),
    ):
        platforms.append(
            {"platform": name, "status": "connected" if ok else "not_connected",
             "lastChecked": None, "error": None,
             "detail": "Credentials set. See Platforms for a live check." if ok else how}
        )
    # Spec §46: never imply this is production-connected.
    platforms.append(
        {"platform": "facebook", "status": "not_implemented", "lastChecked": None,
         "error": None, "detail": FACEBOOK_REASON}
    )

    return {"platforms": platforms}
