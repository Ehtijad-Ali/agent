"""Signal backend entrypoint.

Phase 2. Serves the scoring engine plus the conversation, activity, insights,
scan and outbound-reply routes, backed by a database and a background ingestion
poller. Auth remains unbuilt, so writes are attributed to a single local
operator.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import (
    activity,
    agents,
    assistant,
    auth,
    automation,
    conversations,
    engine,
    health,
    insights,
    platforms,
    replies,
    scans,
    search,
    tracking,
    users,
)
from app.api.routes.auth import current_user
from app.core.config import get_settings
from app.db.session import init_db
from app.workers import poller

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("signal")
# httpx logs every request URL at INFO, and a Telegram Bot API URL embeds the
# bot token. Left at INFO, the token ends up in plain text in every log file.
logging.getLogger("httpx").setLevel(logging.WARNING)

settings = get_settings()

app = FastAPI(
    title="Signal API",
    version="0.1.0",
    description=(
        "Backend for Signal, a social intent radar. Phase 2: scoring engine, "
        "conversations, insights, ingestion and human-approved replies. Auth "
        "follows in Phase 3."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Spec §38: exact origins, never a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
async def _validate_configuration() -> None:
    from app.utils.background import capture_loop

    # Lets sync routes hand events to n8n without blocking the request.
    capture_loop()
    problems = settings.validate_for_production()
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    if not settings.has_database:
        logger.warning(
            "DATABASE_URL is unset - engine endpoints only. "
            "Conversation and activity routes will return 503."
        )
        return

    init_db()
    engine.load_active_config()
    _recover_agent_tasks()
    if poller.start():
        logger.info("Ingestion is live.")


def _recover_agent_tasks() -> None:
    from app.db.session import session_scope
    from app.services.agent_engine import recover_on_startup

    db = session_scope()
    try:
        recover_on_startup(db)
    finally:
        db.close()


@app.on_event("shutdown")
async def _stop_poller() -> None:
    """Cancel the poller so a reload does not leave a second one running."""
    await poller.stop()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Spec §39: every request carries an id, echoed back for correlation."""
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _error(code: str, message: str, status: int, request_id: str) -> JSONResponse:
    """Spec §32: consistent envelope, never a raw stack trace."""
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return _error(
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        status=exc.status_code,
        request_id=getattr(request.state, "request_id", "-"),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
    return _error(
        code="VALIDATION_ERROR",
        message=f"{field}: {first.get('msg', 'invalid request')}",
        status=422,
        request_id=getattr(request.state, "request_id", "-"),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Full detail to the log, a generic message to the client."""
    request_id = getattr(request.state, "request_id", "-")
    logger.exception("Unhandled error [request_id=%s]", request_id)
    return _error(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. Quote the request id when reporting this.",
        status=500,
        request_id=request_id,
    )


# Signing in must not itself require being signed in.
app.include_router(auth.router, prefix="/api")

# Everything below carries the session requirement at the router level rather
# than per-endpoint: a new route added to any of these files is protected by
# default, which is the safe direction for a mistake to fall (spec §38).
_SIGNED_IN = [Depends(current_user)]

app.include_router(health.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(engine.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(conversations.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(activity.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(agents.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(assistant.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(insights.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(platforms.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(scans.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(search.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(replies.router, prefix="/api", dependencies=_SIGNED_IN)
app.include_router(users.router, prefix="/api", dependencies=_SIGNED_IN)
# No /api prefix: /r/{slug} is pasted into public messages, so it stays short.
# n8n workflows authenticate with the shared secret, not a browser session.
app.include_router(automation.router, prefix="/api")
app.include_router(tracking.router)

# Documented in the spec but not built yet. Without these a request to
# /api/conversations returns a bare 404, which is indistinguishable from a
# typo. 501 with a phase number says "this is coming", not "you got the URL
# wrong". Removed as each route lands.
PENDING_ROUTES: dict[str, int] = {
    "/api/auth": 3,
    "/api/safety": 4,
}


@app.get("/", include_in_schema=False)
async def index():
    """Opening the base URL in a browser should land somewhere useful rather
    than on a 404."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/docs")


@app.get("/api", tags=["meta"])
async def api_root() -> dict:
    return {
        "name": "Signal API",
        "version": app.version,
        "phase": 2,
        "docs": "/docs",
        "available": [
            "/api/health",
            "/api/health/ai",
            "/api/health/platforms",
            "/api/platforms/discord",
            "/api/tuning",
            "/api/tuning/preview",
            "/api/tuning/non-negotiables",
            "/api/playground/analyze",
            "/api/conversations",
            "/api/activity",
            "/api/insights/overview",
            "/api/scans/run",
            "/api/replies/{id}/send",
        ],
        "pending": {path: f"phase {phase}" for path, phase in PENDING_ROUTES.items()},
    }


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def not_yet_implemented(path: str):
    """Catch-all for /api. Distinguishes 'planned' from 'wrong URL'."""
    full = f"/api/{path}".rstrip("/")
    for prefix, phase in PENDING_ROUTES.items():
        if full == prefix or full.startswith(prefix + "/"):
            return JSONResponse(
                status_code=501,
                content={
                    "success": False,
                    "error": {
                        "code": "NOT_IMPLEMENTED",
                        "message": (
                            f"{prefix} is specified but not built yet "
                            f"(phase {phase}). See GET /api for what is live."
                        ),
                    },
                },
            )
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": {
                "code": "HTTP_404",
                "message": f"No route for {full}. See GET /api or /docs.",
            },
        },
    )
