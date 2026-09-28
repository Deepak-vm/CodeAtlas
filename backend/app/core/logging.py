"""
backend/app/core/logging.py

Structured logging configuration for the Knowledge Base Agent.

Every request should carry a request_id that propagates through all log
entries emitted during its lifecycle.

Usage:
    from backend.app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("retrieval_started", query=query, repos=repos)
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

# ── Request-scoped correlation ID ─────────────────────────────────────────────
# Set at request ingress (middleware), read in any logger anywhere in the call stack.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    """Generate a compact correlation ID for a new request."""
    return uuid.uuid4().hex[:12]


# ── Structured log formatter ──────────────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """Emit log records as key=value pairs for easy grep / Render log parsing."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
        rid = request_id_var.get("") or "-"
        level = record.levelname[:4].upper()
        name = record.name.split(".")[-1]   # use last component only
        msg = record.getMessage()

        # Append any extra structured fields attached by the caller
        extras: list[str] = []
        for key, val in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                extras.append(f"{key}={val!r}")

        suffix = " " + " ".join(extras) if extras else ""
        return f"{ts} {level} [{name}] req={rid}{suffix} {msg}"


_STANDARD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


# ── Setup ─────────────────────────────────────────────────────────────────────

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Call once at application startup to configure root logger."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (configure root if not yet done)."""
    configure_logging()
    return logging.getLogger(name)


# ── Convenience log-event helpers ─────────────────────────────────────────────

def log_event(logger: logging.Logger, event: str, **kwargs: Any) -> None:
    """Emit a structured event log entry."""
    logger.info(event, extra=kwargs)
