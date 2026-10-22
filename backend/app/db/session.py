"""Database engine and session handling (spec §4).

SQLite locally, Postgres in deployment -- the URL decides. Nothing in the
models or services is dialect-specific, so moving to Postgres is a URL change
and an Alembic run, not a rewrite.

The engine is created lazily. ``DATABASE_URL`` stays optional so the Phase 1
engine endpoints keep working on a machine with no database at all; anything
that needs persistence calls ``require_session`` and returns 503 when it is
unset, rather than failing at import time.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every model."""


@lru_cache
def get_engine() -> Engine | None:
    """One engine per process. ``None`` when no database is configured."""
    settings = get_settings()
    if not settings.database_url:
        return None

    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}

    if url.startswith("sqlite"):
        # The poller writes from a worker task while requests read from the
        # threadpool, so the connection must not be pinned to one thread.
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            # WAL lets the ingestion writer and the API readers coexist without
            # "database is locked" on every concurrent scan.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


@lru_cache
def get_sessionmaker() -> sessionmaker[Session] | None:
    engine = get_engine()
    if engine is None:
        return None
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> bool:
    """Create tables if a database is configured. Returns whether it ran.

    ``create_all`` is enough while the schema is young; Alembic takes over once
    there is data worth migrating rather than recreating.
    """
    engine = get_engine()
    if engine is None:
        return False
    from app import models  # noqa: F401  -- registers mappers before create_all

    Base.metadata.create_all(engine)
    return True


def session_scope() -> Session:
    """A session for background workers, which have no request to hang off.

    The caller owns the transaction and must close it.
    """
    factory = get_sessionmaker()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    return factory()


def get_db() -> Iterator[Session]:
    """FastAPI dependency. 503 rather than 500 when there is no database, so a
    half-configured deploy reads as "not available" instead of "broken"."""
    factory = get_sessionmaker()
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured; persistence is unavailable.",
        )
    db = factory()
    try:
        yield db
    finally:
        db.close()
