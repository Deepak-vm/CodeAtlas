"""
backend/app/agent/nodes/retrieve.py

Three retrieval nodes for the LangGraph StateGraph:
  - retrieve_code    : FAISS dense + BM25 hybrid on code index
  - retrieve_commits : FAISS dense on commit index
  - retrieve_readme  : FAISS dense on readme index

Each node:
  1. Checks if its content type is in state["routed_types"] — skips if not
  2. Filters by state["routed_repos"]
  3. Encodes query with Jina embedder
  4. FAISS search → BM25 rerank (code only) → return top-K chunks

Indexes are loaded once at module import and cached (not reloaded per query).

This module calls into the retrieval.pipeline service rather than directly
touching FAISS/BM25 internals — clean separation of concerns.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.agent.state import AgentState
from backend.app.retrieval.pipeline import RetrievalPipeline

logger = get_logger(__name__)


# ── Index cache accessors — exposed for cache invalidation from repo_service ──

@lru_cache(maxsize=1)
def _get_pipeline() -> RetrievalPipeline:
    """Load and cache the retrieval pipeline (all three indexes)."""
    return RetrievalPipeline.load()


def invalidate_index_cache() -> None:
    """Clear all cached indexes — call after re-indexing a repo."""
    _get_pipeline.cache_clear()
    logger.info("index_cache_cleared")


# ── LangGraph nodes ───────────────────────────────────────────────────────────

def retrieve_code(state: AgentState) -> dict:
    """LangGraph node: dense+BM25 hybrid retrieval on code index."""
    if "code" not in state.get("routed_types", []):
        return {"code_chunks": []}

    pipeline = _get_pipeline()
    if not pipeline.has_code_index:
        logger.warning("retrieve_code: code index not found")
        return {"code_chunks": []}

    chunks = pipeline.search_code(
        query=state["query"],
        repo_filter=state.get("routed_repos") or None,
        top_k_dense=settings.top_k_dense,
        top_k_final=settings.top_k_final,
    )
    logger.info("retrieve_code", extra={"chunk_count": len(chunks)})
    return {"code_chunks": chunks}


def retrieve_commits(state: AgentState) -> dict:
    """LangGraph node: dense retrieval on commit index."""
    if "commits" not in state.get("routed_types", []):
        return {"commit_chunks": []}

    pipeline = _get_pipeline()
    if not pipeline.has_commit_index:
        logger.warning("retrieve_commits: commit index not found")
        return {"commit_chunks": []}

    chunks = pipeline.search_commits(
        query=state["query"],
        repo_filter=state.get("routed_repos") or None,
        top_k=settings.top_k_final,
    )
    logger.info("retrieve_commits", extra={"chunk_count": len(chunks)})
    return {"commit_chunks": chunks}


def retrieve_readme(state: AgentState) -> dict:
    """LangGraph node: dense retrieval on readme/docs index."""
    if "readme" not in state.get("routed_types", []):
        return {"readme_chunks": []}

    pipeline = _get_pipeline()
    if not pipeline.has_readme_index:
        logger.warning("retrieve_readme: readme index not found")
        return {"readme_chunks": []}

    chunks = pipeline.search_readme(
        query=state["query"],
        repo_filter=state.get("routed_repos") or None,
        top_k=settings.top_k_final,
    )
    logger.info("retrieve_readme", extra={"chunk_count": len(chunks)})
    return {"readme_chunks": chunks}
