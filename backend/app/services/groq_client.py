"""Groq chat-completions client (OpenAI-compatible API).

Plain httpx rather than an SDK: the API is one endpoint, and the project
already depends on httpx with the same retry pattern in its platform
connectors.

The key is read from settings on each call and sent only in the Authorization
header to api.groq.com. It is never logged: errors are reported by status code
and Groq's own message, never with the request.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm import LLMError

logger = logging.getLogger("signal.groq")

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_ATTEMPTS = 3


class GroqError(LLMError):
    """Groq could not answer. The message is safe to show the operator."""


def is_configured() -> bool:
    return bool(get_settings().groq_api_key)


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("retry-after")
    try:
        return max(0.5, min(float(raw), 30.0))
    except (TypeError, ValueError):
        return 2.0


async def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """One completion. Returns {"message": ..., "usage": ...}.

    429 and 5xx are retried with backoff; anything else is raised as a
    GroqError carrying Groq's description.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise GroqError("The AI agent is not configured: GROQ_API_KEY is not set on the server.")

    payload: dict[str, Any] = {
        "model": model or settings.groq_model,
        "messages": messages,
        "max_completion_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    last_error = "no response"
    for attempt in range(MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=settings.groq_timeout_seconds) as client:
                response = await client.post(API_URL, json=payload, headers=headers)
        except httpx.TimeoutException:
            last_error = f"Groq did not answer within {settings.groq_timeout_seconds}s"
            continue
        except httpx.HTTPError as exc:
            raise GroqError(f"Could not reach Groq: {exc.__class__.__name__}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"Groq returned HTTP {response.status_code}"
            if attempt < MAX_ATTEMPTS - 1:
                delay = _retry_after(response) * (attempt + 1)
                logger.info("Groq %s, retrying in %.1fs", response.status_code, delay)
                await asyncio.sleep(delay)
            continue

        try:
            body = response.json()
        except ValueError as exc:
            raise GroqError(f"Groq returned a non-JSON response ({response.status_code})") from exc

        if response.status_code != 200:
            detail = (body.get("error") or {}).get("message", "unknown error")
            if response.status_code == 401:
                detail = "the API key was rejected"
            raise GroqError(f"Groq error ({response.status_code}): {detail}")

        choice = (body.get("choices") or [{}])[0]
        return {"message": choice.get("message") or {}, "usage": body.get("usage") or {}}

    if "429" in last_error:
        raise GroqError("Groq's rate limit was reached. Wait a minute and try again.")
    raise GroqError(last_error)
