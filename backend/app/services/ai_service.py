"""AI summaries and suggested replies, written by the local Ollama model.

The template drafts in reply_service stay as the fallback (spec §14: the
pipeline must not fail when the AI does). When Ollama is reachable, the model
reads the actual message and writes:

* a one-sentence summary for the reviewer, in English;
* for each tone, a personal opening and body in the author's language.

The model never writes the compliance text. The disclosure, the free-to-play /
no-deposit / 18+ line and the link are added by code, in the fixed wording the
send-time safety check (safety_service) looks for, and the length cap trims
only the AI-written body. An AI draft therefore cannot fail the safety check
in a way a template draft could not.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings
from app.schemas.tuning import VoiceConfig
from app.services.reply_service import (
    DISCLOSURE,
    FREE_TO_PLAY,
    PRODUCT_LABEL,
    PRODUCT_URL,
    TONES,
    _assemble,
    detect_language,
)

logger = logging.getLogger("signal.ai")

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "pt": "Portuguese", "fr": "French",
    "de": "German", "it": "Italian", "nl": "Dutch", "tl": "Filipino",
}

# Asked for as JSON with a fixed schema: Ollama constrains the output to it,
# which a 3B model needs far more than a long prompt.
_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "summary": {"type": "string"},
        "replies": {
            "type": "object",
            "properties": {
                tone: {
                    "type": "object",
                    "properties": {"opening": {"type": "string"}, "body": {"type": "string"}},
                    "required": ["opening", "body"],
                }
                for tone in TONES
            },
            "required": list(TONES),
        },
    },
    "required": ["language", "summary", "replies"],
}

# Things the model must not put in its own text: a second link, or claims the
# compliance line already makes (duplicates read as spam).
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
# Pictographs and symbols; removed when the voice setting asks for no emoji,
# because small models add them regardless of the instruction.
_EMOJI = re.compile("[🀀-🫿☀-➿️]")


# Sentences restating what the fixed compliance line already says. Dropped
# from the model's body so the reply does not say it twice.
_RESTATES = re.compile(r"free[\s-]?to[\s-]?play|deposit|18\s*\+|disclosure|i work (on|for)", re.IGNORECASE)


def _without_restatements(body: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", body)
    kept = [x for x in sentences if x and not _RESTATES.search(x)]
    return " ".join(kept) if kept else body


@dataclass(slots=True)
class AIDraft:
    # None when the model's summary was unusable (e.g. not in English); the
    # caller then keeps the rule-based summary.
    summary: str | None
    language: str
    variants: list[dict[str, str]]


def enabled() -> bool:
    return bool(get_settings().ollama_model)


def _prompt(message: str, community: str, voice: VoiceConfig, language_hint: str) -> str:
    style = []
    style.append("formal" if voice.formality >= 60 else "casual and friendly")
    if voice.emoji >= 50:
        style.append("one emoji is fine")
    else:
        style.append("no emoji")
    return f"""You help a community manager for {PRODUCT_LABEL}, a FREE social prediction game \
(pick outcomes, earn points, climb a leaderboard; no real money, no deposits, 18+).

A person posted this in "{community}":
<<<
{message[:2000]}
>>>

Return JSON:
- "language": ISO 639-1 code of the post's language (hint: {language_hint}).
- "summary": ONE sentence IN ENGLISH (always English, even if the post is not) for the reviewer: what the person wants and whether
  {PRODUCT_LABEL} fits. Plain, factual, no hype.
- "replies": for each tone (helpful, concise, conversational) an "opening" (a short greeting
  that reacts to their post, max 12 words) and a "body" (1-2 sentences on why the game fits
  what THEY asked, max 35 words). Write opening and body in {language_name(language_hint)}. Style: {", ".join(style)}.

Rules: no links, no URLs, no prices, never mention betting with money, gambling, winnings or
odds. Do not mention disclosure, "free to play", deposits or age; that text is added separately."""


def _clean(text: str, limit: int) -> str:
    text = _URL.sub("", str(text or ""))
    text = " ".join(text.split()).strip(" \"'")
    return text[:limit].strip()


async def draft(
    message: str, community: str, voice: VoiceConfig, language_hint: str = "en"
) -> AIDraft | None:
    """Summary and three reply variants from the model, or None to fall back."""
    s = get_settings()
    if not s.ollama_model:
        return None
    payload = {
        "model": s.ollama_model,
        "prompt": _prompt(message, community, voice, language_hint),
        "format": _SCHEMA,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0.4, "num_ctx": 4096},
    }
    try:
        async with httpx.AsyncClient(timeout=s.ollama_timeout_seconds) as client:
            response = await client.post(f"{s.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        response.raise_for_status()
        data = json.loads(response.json().get("response") or "{}")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("AI drafting unavailable, using templates: %s", str(exc)[:200])
        return None

    summary = _clean(data.get("summary", ""), 300)
    language = _clean(data.get("language", ""), 5).lower()[:2] or language_hint
    replies = data.get("replies") or {}

    variants: list[dict[str, str]] = []
    for tone in TONES:
        part = replies.get(tone) or {}
        opening = _clean(part.get("opening", ""), 120)
        body = _clean(part.get("body", ""), 400)
        if voice.emoji < 50:
            opening = " ".join(_EMOJI.sub("", opening).split())
            body = " ".join(_EMOJI.sub("", body).split())
        opening = opening.rstrip(".!,;:¡¿ ")
        body = _without_restatements(body)
        if not opening or not body:
            return None  # an incomplete answer is worse than the template
        punctuation = "!" if voice.friendliness >= 65 and tone != "concise" else "."
        if punctuation == "." and opening.startswith("¡"):
            opening = opening[1:]
        head = f"{opening}{punctuation} {DISCLOSURE}"
        cta = f"{FREE_TO_PLAY} {PRODUCT_URL}"
        variants.append(
            {"tone": tone, "text": _assemble(head, body, cta, "", voice.max_length), "source": "ai"}
        )

    if not summary or detect_language(summary) != "en":
        summary = None
    return AIDraft(summary=summary, language=language if language.isalpha() else language_hint, variants=variants)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)
