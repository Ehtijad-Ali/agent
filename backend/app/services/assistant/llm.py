"""Chat-completion client for the AI Agent.

Ollama is the default and the intended deployment: the model runs on the same
server, so there is no per-token bill and no data leaves the machine. Groq is
an optional hosted fallback used only when no Ollama model is configured.

Both are normalised to one shape: text content, plus tool calls as
``{"id", "type": "function", "function": {"name", "arguments": dict}}``.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings


class LLMError(RuntimeError):
    """The model could not be reached or answered with an error."""


@dataclass
class LLMReply:
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0


def provider() -> tuple[bool, str, str]:
    """(configured, provider, model)."""
    s = get_settings()
    model = s.assistant_model or s.ollama_model
    if model:
        return True, "ollama", model
    if s.groq_api_key:
        return True, "groq", s.groq_model
    return False, "ollama", ""


def _call_id() -> str:
    return "call_" + uuid.uuid4().hex[:12]


def _parse_arguments(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {"value": value}
        except ValueError:
            return {"raw": raw}
    return {}


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _tool_calls_from_text(content: str, tool_names: set[str]) -> list[dict[str, Any]]:
    """Small local models sometimes print a tool call as JSON text instead of
    using the tool-call channel. Recover it when the JSON names a real tool."""
    text = content.strip()
    if not text or "{" not in text:
        return []
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    match = _JSON_BLOCK.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []
    items = data if isinstance(data, list) else [data]
    calls: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else item
        name = fn.get("name")
        if name in tool_names:
            args = fn.get("arguments", fn.get("parameters", {}))
            calls.append(
                {"id": _call_id(), "type": "function",
                 "function": {"name": name, "arguments": _parse_arguments(args)}}
            )
    return calls


def to_ollama(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": [
                        {"function": {"name": c["function"]["name"],
                                      "arguments": c["function"]["arguments"]}}
                        for c in m["tool_calls"]
                    ],
                }
            )
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name") or ""})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


def to_openai(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or None,
                    "tool_calls": [
                        {"id": c["id"], "type": "function",
                         "function": {"name": c["function"]["name"],
                                      "arguments": json.dumps(c["function"]["arguments"])}}
                        for c in m["tool_calls"]
                    ],
                }
            )
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id") or "", "content": m["content"]})
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


async def chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
    configured, name, model = provider()
    if not configured:
        raise LLMError("No model is configured. Set OLLAMA_MODEL in backend/.env.")
    s = get_settings()
    tool_names = {t["function"]["name"] for t in tools}

    if name == "ollama":
        payload = {
            "model": model,
            "messages": to_ollama(messages),
            "tools": tools,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.2, "num_ctx": 8192},
        }
        try:
            async with httpx.AsyncClient(timeout=s.assistant_timeout_seconds) as client:
                response = await client.post(f"{s.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMError("The local model took too long to answer.") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Cannot reach Ollama at {s.ollama_base_url}. Is it running?") from exc
        if response.status_code == 404:
            raise LLMError(f"Ollama has no model '{model}'. Run: ollama pull {model}")
        if response.status_code >= 400:
            raise LLMError(f"Ollama error HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        message = data.get("message") or {}
        calls = [
            {"id": c.get("id") or _call_id(), "type": "function",
             "function": {"name": c["function"]["name"],
                          "arguments": _parse_arguments(c["function"].get("arguments"))}}
            for c in message.get("tool_calls") or []
            if c.get("function", {}).get("name")
        ]
        content = message.get("content") or ""
        if not calls:
            calls = _tool_calls_from_text(content, tool_names)
            if calls:
                content = ""
        tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
        return LLMReply(content=content.strip(), tool_calls=calls, tokens=tokens)

    # Groq (OpenAI-compatible).
    try:
        async with httpx.AsyncClient(timeout=s.assistant_timeout_seconds) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                json={"model": model, "messages": to_openai(messages), "tools": tools,
                      "tool_choice": "auto", "temperature": 0.2},
            )
    except httpx.HTTPError as exc:
        raise LLMError("Cannot reach Groq.") from exc
    if response.status_code >= 400:
        raise LLMError(f"Groq error HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    message = (data.get("choices") or [{}])[0].get("message") or {}
    calls = [
        {"id": c.get("id") or _call_id(), "type": "function",
         "function": {"name": c["function"]["name"],
                      "arguments": _parse_arguments(c["function"].get("arguments"))}}
        for c in message.get("tool_calls") or []
    ]
    usage = data.get("usage") or {}
    return LLMReply(content=(message.get("content") or "").strip(), tool_calls=calls,
                    tokens=int(usage.get("total_tokens") or 0))
