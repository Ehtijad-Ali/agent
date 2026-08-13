"""Deterministic author pseudonymisation (spec §10).

Real platform handles must never reach the frontend or the database. The same
author must always map to the same pseudonym, otherwise the "one reply per
person, ever" guarantee (spec §15) cannot be enforced -- prior outreach could
not be matched to a returning author.

HMAC-SHA256 keyed with PSEUDONYM_SALT, not a bare hash: platform user IDs are
low-entropy and enumerable, so an unsalted digest would be trivially reversible
by anyone who obtained the database.
"""

from __future__ import annotations

import hashlib
import hmac

_PREFIX = "user_"
_DIGEST_CHARS = 4


def pseudonymise(platform: str, external_user_id: str, salt: str) -> str:
    """Map a platform user id to a stable pseudonym like ``user_8f2a``.

    Namespaced by platform so the same numeric id on Discord and Telegram does
    not collapse to one identity.
    """
    if not salt:
        raise ValueError(
            "PSEUDONYM_SALT is not set. Refusing to pseudonymise with an empty "
            "key, which would make author ids reversible."
        )
    message = f"{platform}:{external_user_id}".encode()
    digest = hmac.new(salt.encode(), message, hashlib.sha256).hexdigest()
    return f"{_PREFIX}{digest[:_DIGEST_CHARS]}"


def content_hash(platform: str, text: str) -> str:
    """Normalised content fingerprint for duplicate detection (spec §11).

    Complements the platform + external id check: catches the same message
    reposted under a new id, which is common with spam.
    """
    normalised = " ".join(text.lower().split())
    return hashlib.sha256(f"{platform}:{normalised}".encode()).hexdigest()
