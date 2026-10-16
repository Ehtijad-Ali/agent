"""Test-suite guard rails.

Without this, running the suite writes to the real development database. The
app's startup hook calls ``init_db()`` and ``load_active_config()``, and both
take their session from the global factory rather than from the ``get_db``
dependency that tests override -- so a TestClient would read and, through any
endpoint that bypassed the dependency, write to ``backend/signal.db``.

That actually happened: a test that saved a tuning config left three bogus
``configuration_versions`` rows in the dev database.

Blanking ``DATABASE_URL`` before the settings are cached makes startup a no-op
(no table creation, no config load, no scanner) while tests continue to inject
their own in-memory session. The real database is then unreachable from here by
construction, not by discipline.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = ""
# The scanner must never start during tests; it would poll live platforms.
os.environ["SCAN_INTERVAL_SECONDS"] = "0"
# Nor may anything else reach a live platform -- enabling an agent triggers a
# scan, which with the developer's real tokens would poll real groups.
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["DISCORD_BOT_TOKEN"] = ""
# A fixed salt keeps pseudonyms and visitor hashes deterministic across runs.
os.environ.setdefault("PSEUDONYM_SALT", "test-salt-not-a-real-one")
os.environ["ENVIRONMENT"] = "development"

from app.core.config import get_settings  # noqa: E402

# Settings are lru_cached; clear it in case importing anything above already
# populated the cache with the developer's real .env values.
get_settings.cache_clear()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def signed_in():
    """Every API test runs as a signed-in admin.

    Routes carry the session requirement at the router level (app/main.py), so
    without this the whole suite would 401 -- which would say nothing about the
    behaviour each test is actually asserting.

    Authentication itself is covered by test_auth.py, which clears this
    override so it can exercise the real dependency.
    """
    # Imported here rather than at module scope: the environment above must be
    # set before anything pulls in the settings cache.
    from app.api.routes.auth import current_user
    from app.main import app
    from app.models import User

    app.dependency_overrides[current_user] = lambda: User(
        id="00000000-0000-0000-0000-000000000001",
        email="tester@example.com",
        name="Tester",
        password_hash="not-a-real-hash",
        role="admin",
        is_active=True,
    )
    yield
    app.dependency_overrides.pop(current_user, None)
