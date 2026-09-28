"""
backend/app/main.py

FastAPI application factory for the Knowledge Base Agent.

This replaces the old api/main.py (which was 538 lines mixing routes,
business logic, index management, and DB calls).

The new main.py is thin:
  - Creates the FastAPI app
  - Applies CORS middleware
  - Registers routers with /api/v1 prefix
  - Sets up startup tasks (DB ping, directory creation)

Entry point for Render:
  uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT

For local dev:
  uvicorn backend.app.main:app --reload --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── Ensure the project root is on sys.path so `ingestion`, `indexing`, etc.
# can still be imported as top-level packages (they are not inside backend/).
_ROOT = Path(__file__).parent.parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.exceptions import KnowledgeAgentError

configure_logging()
logger = get_logger(__name__)

# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Knowledge Base Agent",
    description="Multi-repo RAG system: ask questions about your own code with citations",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler (typed app errors → clean JSON) ──────────────────

@app.exception_handler(KnowledgeAgentError)
async def app_error_handler(request: Request, exc: KnowledgeAgentError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.error_code, "detail": exc.message},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
from backend.app.api.routes import chat, repos, health  # noqa: E402 (after sys.path setup)

PREFIX = f"/api/{settings.api_version}"

app.include_router(chat.router, prefix=PREFIX, tags=["Chat"])
app.include_router(repos.router, prefix=PREFIX, tags=["Repositories"])
app.include_router(health.router, prefix=PREFIX, tags=["Health"])

# ── Backward-compatible routes (no /api/v1 prefix) ────────────────────────────
# The existing frontend calls /query, /history, /repos, /feedback, /health.
# We re-register those routes without a prefix so the frontend works without changes.

app.include_router(chat.router, tags=["Chat (legacy)"])
app.include_router(repos.router, tags=["Repositories (legacy)"])
app.include_router(health.router, tags=["Health (legacy)"])


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """Ensure data directories exist and DB connection is live."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.chunks_dir.mkdir(parents=True, exist_ok=True)
    settings.indexes_dir.mkdir(parents=True, exist_ok=True)
    settings.repos_dir.mkdir(parents=True, exist_ok=True)

    # DB ping
    from backend.app.database.client import ping
    if ping():
        logger.info("supabase_connected")
    else:
        logger.warning("supabase_connection_failed")
