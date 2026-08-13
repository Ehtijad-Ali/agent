"""Health endpoints (spec §39).

These report what is actually reachable rather than always returning ok. During
Phase 1 most subsystems are intentionally absent, and the response says so
instead of pretending otherwise.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter

from app.core.config import get_settings

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
    """Spec §29: credential *status* only. Tokens never leave this process."""
    settings = get_settings()
    return {
        "platforms": [
            {
                "platform": "telegram",
                "status": "configured" if settings.telegram_bot_token else "not_connected",
                "lastChecked": None,
                "error": None,
            },
            {
                "platform": "discord",
                "status": "configured" if settings.discord_bot_token else "not_connected",
                "lastChecked": None,
                "error": None,
            },
            # Spec §46: do not claim these are production-connected.
            {"platform": "reddit", "status": "not_implemented", "lastChecked": None, "error": None},
            {"platform": "facebook", "status": "not_implemented", "lastChecked": None, "error": None},
        ]
    }
