"""Signal backend entrypoint.

Phase 1. Serves the scoring-engine endpoints, which need no database. The
conversation, auth and reply routes arrive with Phase 2.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import engine, health
from app.core.config import get_settings

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("signal")

settings = get_settings()

app = FastAPI(
    title="Signal API",
    version="0.1.0",
    description=(
        "Backend for Signal, a social intent radar. Phase 1: scoring engine "
        "endpoints. Conversations, auth and replies follow in Phase 2."
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
    problems = settings.validate_for_production()
    if problems:
        raise RuntimeError("Invalid production configuration: " + "; ".join(problems))
    if not settings.has_database:
        logger.warning(
            "DATABASE_URL is unset - engine endpoints only. "
            "Conversation, auth and reply routes are unavailable."
        )


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


app.include_router(health.router, prefix="/api")
app.include_router(engine.router, prefix="/api")

# Documented in the spec but not built yet. Without these a request to
# /api/conversations returns a bare 404, which is indistinguishable from a
# typo. 501 with a phase number says "this is coming", not "you got the URL
# wrong". Removed as each route lands.
PENDING_ROUTES: dict[str, int] = {
    "/api/auth": 2,
    "/api/conversations": 2,
    "/api/activity": 2,
    "/api/replies": 6,
    "/api/insights": 8,
    "/api/scans": 5,
    "/api/platforms": 5,
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
        "phase": 1,
        "docs": "/docs",
        "available": [
            "/api/health",
            "/api/health/ai",
            "/api/health/platforms",
            "/api/tuning",
            "/api/tuning/preview",
            "/api/tuning/non-negotiables",
            "/api/playground/analyze",
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
