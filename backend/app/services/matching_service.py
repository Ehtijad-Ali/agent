"""Robust keyword matcher.

A verbatim port of ``src/lib/scoring.ts`` (normaliseText / stem / tokenise /
editDistance / matchKeyword). The two implementations must agree exactly: the
frontend renders the score breakdown the backend produces, and the Playground
is required to use the same engine as ingestion (spec §22).

Deliberately NOT ``keyword in message``. See spec §12.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

MatchType = Literal["broad", "exact", "phrase"]

# Ported verbatim from scoring.ts. Order is irrelevant but membership is not:
# "no" and "without" being stopwords is what makes the spec §33 critical test
# pass ("no deposit" vs "play without depositing money"). Do not prune this.
STOP_WORDS: frozenset[str] = frozenset(
    """
    a an the is are was were be been being
    to of in on at for with without and or
    but if then than so as by this that these
    those i you we they he she it my your
    our their his her its me him them us
    do does did have has had will would can
    could should may might must shall any some
    no not very too also just only really anyone
    someone know looking find
    about above across after against along among around
    before behind below beneath beside between beyond
    during except from inside into near off onto
    outside over through throughout toward under until
    up upon within out down again more most
    other such own same few all both each
    get got make made go goes went
    """.split()
)

# Unicode-aware: strip anything that is not a letter, number or whitespace.
_NON_WORD = re.compile(r"[^\w\s]|_", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalise_text(value: str) -> str:
    """Lowercase, NFKC-normalise, strip punctuation, collapse whitespace.

    NFKC is a deliberate addition over the TS version: platform messages arrive
    with full-width and decomposed forms that JS's regex pass leaves alone.
    It cannot change the result for plain ASCII, so the engines still agree on
    every existing test vector.
    """
    folded = unicodedata.normalize("NFKC", value).lower()
    return _WHITESPACE.sub(" ", _NON_WORD.sub(" ", folded)).strip()


def stem(word: str) -> str:
    """Light suffix stripper. Mirrors the TS stemmer exactly, including its
    quirks -- a real lemmatiser here would desynchronise the two engines."""
    w = word.lower().strip()
    if len(w) <= 3:
        return w
    # -ies -> -y   ("countries" -> "country")
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    # -ing         ("depositing" -> "deposit")
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    # -ed          ("played" -> "play")
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    # -es only after a sibilant ("boxes" -> "box")
    if w.endswith("es") and len(w) > 4 and w[-3:-2] in ("s", "h", "x", "z"):
        return w[:-2]
    # -s plural, but not "bus" / "this" / "loss"
    if w.endswith("s") and len(w) > 3 and w[-2:-1] not in ("s", "u", "i"):
        return w[:-1]
    return w


def tokenise(value: str) -> list[str]:
    """Normalise -> split -> drop stopwords and 1-char tokens -> stem."""
    return [
        stem(token)
        for token in normalise_text(value).split(" ")
        if len(token) > 1 and token not in STOP_WORDS
    ]


def edit_distance(a: str, b: str, max_distance: int = 2) -> int:
    """Levenshtein, short-circuited at ``max_distance`` for speed."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > max_distance:
        return max_distance + 1
    if la == 0:
        return lb
    if lb == 0:
        return la
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            tmp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (0 if a[i - 1] == b[j - 1] else 1))
            prev = tmp
    return min(dp[lb], max_distance + 1)


@dataclass(frozen=True, slots=True)
class MatchResult:
    """``weight`` is 0..1 and scales the rule's configured points, so a partial
    or non-adjacent match scores lower than an exact one (spec §12)."""

    hit: bool
    weight: float


_NO_MATCH = MatchResult(hit=False, weight=0.0)


def match_keyword(
    message_tokens: list[str],
    normalised_message: str,
    term: str,
    match_type: MatchType,
) -> MatchResult:
    """Match one configured term against an already-normalised message."""
    term_norm = normalise_text(term)
    if not term_norm:
        return _NO_MATCH

    if match_type == "phrase":
        # Substring first: catches "play without depositing money" containing
        # "play without depositing".
        if term_norm in normalised_message:
            return MatchResult(hit=True, weight=1.0)

        # Near-phrase: require ALL non-stopword stemmed tokens of the term to
        # be present within edit distance 1. Requiring *all* is what stops
        # "real money" matching a message that only says "money".
        term_tokens = tokenise(term)
        if not term_tokens:
            return _NO_MATCH

        matched = 0
        adjacent = 0
        last_idx = -2
        for tt in term_tokens:
            idx = _find_token(message_tokens, tt)
            if idx != -1:
                matched += 1
                if idx == last_idx + 1:
                    adjacent += 1
                last_idx = idx

        if matched == len(term_tokens):
            # Full match; adjacency in the message earns full weight.
            weight = 1.0 if adjacent >= len(term_tokens) - 1 else 0.85
            return MatchResult(hit=True, weight=weight)

        # No partial credit for phrases -- too many false positives.
        return _NO_MATCH

    if match_type == "exact":
        return MatchResult(hit=True, weight=1.0) if term_norm in normalised_message else _NO_MATCH

    # broad: any stemmed token of the term appears, weight = hit ratio.
    term_tokens = [stem(t) for t in term_norm.split(" ") if t]
    if not term_tokens:
        return _NO_MATCH
    hits = sum(1 for tt in term_tokens if _find_token(message_tokens, tt) != -1)
    if hits == 0:
        return _NO_MATCH
    return MatchResult(hit=True, weight=min(1.0, hits / len(term_tokens)))


def _find_token(message_tokens: list[str], target: str) -> int:
    """Index of the first token equal to or within edit distance 1 of target."""
    for i, mt in enumerate(message_tokens):
        if mt == target or edit_distance(mt, target, 1) <= 1:
            return i
    return -1
