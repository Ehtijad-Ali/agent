"""Deterministic reply drafting.

Port of ``draftReply`` from ``src/lib/scoring.ts``. This is the template-based
fallback: it always produces three genuinely different variants and always
carries the disclosure and free-to-play wording, so drafts exist even when
Ollama is unreachable (spec §14 requires the pipeline not to crash on AI
failure). The Ollama provider will layer on top and must clear the same
reply safety check (spec §17).

Nothing here sends anything. Drafts are drafts (spec §18).
"""

from __future__ import annotations

import re

from app.schemas.tuning import VoiceConfig

# Locked by the non-negotiable rules -- disclosure leads rather than trails, so
# a reader skimming the first line sees the brand connection.
DISCLOSURE = "Full disclosure, I work on Join All Bettors."
FREE_TO_PLAY = "Free to play, no deposits, 18+."
PRODUCT_URL = "https://joinallbettors.example"

TONES: tuple[str, ...] = ("helpful", "concise", "conversational")


def draft_reply(
    community: str,
    tone: str,
    voice: VoiceConfig,
) -> str:
    """Build one variant, guaranteeing the mandatory parts survive the length cap.

    The naive approach -- assemble the whole string then slice to
    ``max_length`` -- silently destroys the parts that make the reply legal.
    At the default 280 characters the helpful and conversational variants both
    overflow, and the tail is exactly where the disclosure and the link live.
    Observed output was ``"... Link if it's useful:…"``: a call to action with
    no link, and in the original ordering the brand disclosure was cut instead,
    which would fail the reply safety check in spec §17.

    So the mandatory head (greeting + disclosure) and tail (free-to-play note +
    URL) are reserved first, and only the descriptive body is trimmed to fit.
    """
    high_emoji = voice.emoji >= 50
    high_friendliness = voice.friendliness >= 65
    high_formality = voice.formality >= 60
    high_cta = voice.cta_strength >= 65

    greeting = "Hello" if high_formality else ("Hey there" if high_friendliness else "Hi")
    emoji = ""

    if tone == "concise":
        head = f"{greeting}. {DISCLOSURE}"
        body = "It's a free prediction game, which sounds like what you're after."
        cta = f"{FREE_TO_PLAY} {PRODUCT_URL}"
    elif tone == "conversational":
        punctuation = "!" if high_friendliness else ","
        head = f"{greeting}{punctuation} Saw your post in {community}. {DISCLOSURE}"
        body = (
            "We made a free social prediction game: pick outcomes, earn points, "
            "climb a leaderboard. No money in it anywhere."
        )
        link_phrase = "Want the link?" if high_cta else "Link's here if you fancy a look:"
        cta = f"{FREE_TO_PLAY} {link_phrase} {PRODUCT_URL}"
        emoji = " 🙂" if high_emoji else ""
    else:  # helpful
        head = f"{greeting}, thanks for asking in {community}. {DISCLOSURE}"
        body = (
            "It might be what you're after: pick outcomes, earn points, climb a "
            "leaderboard, and no real money changes hands."
        )
        link_phrase = "You can try it here:" if high_cta else "Link if it's useful:"
        cta = f"{FREE_TO_PLAY} {link_phrase} {PRODUCT_URL}"
        emoji = " 🎯" if high_emoji else ""

    return _assemble(head, body, cta, emoji, voice.max_length)


def draft_all_variants(community: str, voice: VoiceConfig) -> list[dict[str, str]]:
    """The three variants the frontend expects, in its expected order."""
    return [{"tone": t, "text": draft_reply(community, t, voice)} for t in TONES]


def _assemble(head: str, body: str, cta: str, emoji: str, limit: int) -> str:
    """Fit ``head + body + cta`` into ``limit``, sacrificing only ``body``.

    ``head`` carries the disclosure and ``cta`` carries the free-to-play note
    and the URL; both are compliance-mandatory, so they are never trimmed. If
    they alone exceed the limit the reply is returned over-length rather than
    mutilated -- the safety check should reject it loudly instead of the
    drafter quietly shipping something non-compliant.
    """
    mandatory = f"{head} {cta}{emoji}"
    if len(mandatory) > limit:
        return mandatory

    full = f"{head} {body} {cta}{emoji}"
    if len(full) <= limit:
        return full

    # Trim the body on a word boundary to whatever room is left.
    room = limit - len(mandatory) - 1  # the extra space the body would add
    if room < 24:  # too little left to say anything useful
        return mandatory
    trimmed = body[:room]
    space = trimmed.rfind(" ")
    if space > 0:
        trimmed = trimmed[:space]
    trimmed = trimmed.rstrip(" ,.:;") + "…"
    return f"{head} {trimmed} {cta}{emoji}"


# --- language detection ---------------------------------------------------
# Port of detectLanguage() from mockApi.ts. Heuristic and deliberately cheap;
# the AI provider returns a better value once Ollama is wired in (spec §14).

_LANG_PATTERNS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    ("pt", re.compile(r"[áâãàäéêíóôõúç]"), re.compile(r"\b(jogo|gratuito|alguém|previsão|predição)\b")),
    ("fr", re.compile(r"[àâçéèêëîïôûùü]"), re.compile(r"\b(jeu|gratuit|quelqu'un|pronostic)\b")),
    ("de", re.compile(r"[äöüß]"), re.compile(r"\b(spiel|kostenlos|jemand|vorhersage)\b")),
    ("es", re.compile(r"[ñ¿¡]"), re.compile(r"\b(juego|gratis|alguien|predicción)\b")),
)


def detect_language(message: str) -> str:
    lowered = message.lower()
    for code, chars, words in _LANG_PATTERNS:
        if chars.search(message) or words.search(lowered):
            return code
    return "en"
