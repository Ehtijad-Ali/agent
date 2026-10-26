"""One entry point for language-model calls, whichever provider serves them.

``AI_PROVIDER`` picks the backend:

  ollama  (default) -- the model runs on this server. No usage limits or
                       per-token cost; speed is bounded by the CPU.
  groq              -- Groq's hosted API. Much faster, but its free tier caps
                       tokens per minute, which a tool-using agent hits quickly.

Both return the same shape -- {"message": {...}, "usage": {...}} with the
message in chat-completions form (content, tool_calls with JSON-string
arguments) -- so the agent engine and the drafting code never branch on the
provider.

Ollama is called through its native /api/chat rather than its OpenAI-compatible
endpoint, because only the native API accepts ``num_ctx``. Ollama's default
context is small and silently truncates long prompts (tool schemas plus tool
results), which shows up as an agent that "forgets" what it just read.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("signal.llm")


class LLMError(RuntimeError):
    """The model could not answer. The message is safe to show the operator."""


def provider() -> str:
    return (get_settings().ai_provider or "ollama").lower()


def model_name() -> str:
    settings = get_settings()
    return settings.groq_model if provider() == "groq" else settings.ollama_model


def agent_model_name() -> str:
    """The model the AI Agent chat runs on."""
    settings = get_settings()
    if provider() == "groq":
        return settings.groq_model
    return settings.ollama_agent_model or settings.ollama_model


def is_configured() -> bool:
    settings = get_settings()
    if provider() == "groq":
        return bool(settings.groq_api_key)
    return bool(settings.ollama_model)


def not_configured_reason() -> str:
    if provider() == "groq":
        return "The AI is not configured: GROQ_API_KEY is not set on the server."
    return "The AI is not configured: OLLAMA_MODEL is not set on the server."


async def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
    json_mode: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    """``model`` overrides OLLAMA_MODEL for this call (Ollama only)."""
    if provider() == "groq":
        from app.services import groq_client

        return await groq_client.chat(messages, tools=tools, max_tokens=max_tokens)
    return await _ollama_chat(messages, tools, max_tokens, json_mode, model)


# -- Ollama --------------------------------------------------------------------


def _to_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chat-completions messages -> Ollama's native shape.

    The differences: tool-call arguments are an object, not a JSON string, and
    a tool result names its tool rather than referencing a call id.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            calls = []
            for c in m["tool_calls"]:
                args = c["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args or "{}")
                    except ValueError:
                        args = {}
                calls.append({"function": {"name": c["function"]["name"], "arguments": args}})
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
        elif role == "tool":
            out.append({"role": "tool", "content": m.get("content") or "", "tool_name": m.get("name") or ""})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return out


async def _ollama_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    max_tokens: int,
    json_mode: bool,
    model: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ollama_model:
        raise LLMError(not_configured_reason())

    payload: dict[str, Any] = {
        "model": model or settings.ollama_model,
        "messages": _to_ollama(messages),
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "num_ctx": settings.ollama_context,
            "num_predict": max_tokens,
            "temperature": 0.3,
        },
    }
    if tools:
        payload["tools"] = tools
    if json_mode:
        payload["format"] = "json"

    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
    except httpx.TimeoutException as exc:
        raise LLMError(
            f"The local AI did not answer within {settings.ollama_timeout_seconds}s. "
            "The server may be busy; try again, or break the task into smaller steps."
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(
            "The local AI (Ollama) is not reachable. Check that the ollama "
            "service is running."
        ) from exc

    if response.status_code != 200:
        try:
            detail = response.json().get("error", response.text)
        except ValueError:
            detail = response.text
        if "not found" in str(detail).lower():
            detail = f"model '{settings.ollama_model}' is not installed (run: ollama pull {settings.ollama_model})"
        raise LLMError(f"Local AI error ({response.status_code}): {str(detail)[:300]}")

    body = response.json()
    raw = body.get("message") or {}
    calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": c["function"]["name"],
                "arguments": json.dumps(c["function"].get("arguments") or {}),
            },
        }
        for i, c in enumerate(raw.get("tool_calls") or [])
    ]
    message: dict[str, Any] = {"role": "assistant", "content": raw.get("content") or ""}
    if calls:
        message["tool_calls"] = calls
    prompt_tokens = int(body.get("prompt_eval_count") or 0)
    completion_tokens = int(body.get("eval_count") or 0)
    return {
        "message": message,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
