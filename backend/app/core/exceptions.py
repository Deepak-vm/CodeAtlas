"""
backend/app/core/exceptions.py

Application-level exception hierarchy for the Knowledge Base Agent.

Centralising exceptions here means:
  - FastAPI exception handlers can catch them in one place
  - Agent nodes raise typed errors instead of raw strings
  - The frontend always gets a clean JSON error body

Usage:
    from backend.app.core.exceptions import RetrievalError, AgentError

    raise RetrievalError("FAISS index not found — run build_index.py first")
"""

from __future__ import annotations


class KnowledgeAgentError(Exception):
    """Base class for all application errors."""

    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message


# ── Configuration / startup ───────────────────────────────────────────────────

class ConfigurationError(KnowledgeAgentError):
    """Required environment variable or config value is missing."""
    http_status = 500
    error_code = "CONFIGURATION_ERROR"


# ── Agent errors ──────────────────────────────────────────────────────────────

class AgentError(KnowledgeAgentError):
    """LangGraph pipeline failed during execution."""
    http_status = 500
    error_code = "AGENT_ERROR"


class RouterError(AgentError):
    """Intent classification / routing step failed."""
    error_code = "ROUTER_ERROR"


class SynthesisError(AgentError):
    """LLM synthesis step failed."""
    error_code = "SYNTHESIS_ERROR"


# ── Retrieval errors ──────────────────────────────────────────────────────────

class RetrievalError(KnowledgeAgentError):
    """Index query or search step failed."""
    http_status = 503
    error_code = "RETRIEVAL_ERROR"


class IndexNotFoundError(RetrievalError):
    """FAISS or BM25 index file is missing."""
    http_status = 503
    error_code = "INDEX_NOT_FOUND"


# ── Database / repository errors ──────────────────────────────────────────────

class DatabaseError(KnowledgeAgentError):
    """Supabase operation failed."""
    http_status = 503
    error_code = "DATABASE_ERROR"


class RepositoryNotFoundError(DatabaseError):
    """Requested repo does not exist in Supabase."""
    http_status = 404
    error_code = "REPO_NOT_FOUND"


# ── Request validation ────────────────────────────────────────────────────────

class ValidationError(KnowledgeAgentError):
    """Request body failed business-level validation."""
    http_status = 400
    error_code = "VALIDATION_ERROR"


class NoReposConfiguredError(ValidationError):
    """No repositories have been indexed yet."""
    http_status = 400
    error_code = "NO_REPOS_CONFIGURED"


# ── Ingestion errors ──────────────────────────────────────────────────────────

class IngestionError(KnowledgeAgentError):
    """Repo ingestion or indexing subprocess failed."""
    http_status = 500
    error_code = "INGESTION_ERROR"


class RepoDuplicateError(IngestionError):
    """Repository already exists in Supabase."""
    http_status = 400
    error_code = "REPO_DUPLICATE"
