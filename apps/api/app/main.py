"""
ClauseLens FastAPI application entry point.

Startup:
- Ensures storage buckets exist (MinIO or Supabase)

Middleware:
- X-Request-ID for tracing
- CORS

Routes:
- /vendors, /uploads, /jobs, /documents, /clauses, /search, /admin
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import admin, clauses, documents, jobs, search, uploads, vendors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    logger.info("ClauseLens API starting up...")
    try:
        from app.services.storage import startup_ensure_buckets
        startup_ensure_buckets()
        logger.info("Storage buckets verified/created.")
    except Exception as exc:
        logger.warning("Bucket setup failed (non-fatal): %s", exc)
    yield
    logger.info("ClauseLens API shutting down.")


app = FastAPI(
    title="ClauseLens API",
    version="0.1.0",
    description="Legal contract risk review parsing API",
    lifespan=lifespan,
)

# ─── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request ID middleware ──────────────────────────────────────────────────────
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Routes ────────────────────────────────────────────────────────────────────
app.include_router(vendors.router)
app.include_router(uploads.router)
app.include_router(jobs.router)
app.include_router(documents.router)
app.include_router(clauses.router)
app.include_router(search.router)
app.include_router(admin.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ─── Global exception handlers ─────────────────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Log all HTTP exceptions server-side; sanitise explicit 5xx detail strings."""
    if exc.status_code >= 500:
        logger.error(
            "HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "Internal server error"},
        )
    logger.warning(
        "HTTP %s at %s: %s", exc.status_code, request.url.path, exc.detail
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
