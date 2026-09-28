"""
backend/app/services/chat_service.py

ChatService — orchestrates the LangGraph pipeline for a single query.

The FastAPI route calls chat_service.chat() and receives a QueryResponse.
It does NOT interact with the graph, state, or database directly.

Responsibilities:
  - Validate preconditions (repos configured)
  - Invoke the LangGraph pipeline
  - Map graph output → QueryResponse schema
  - Persist query history to Supabase (best-effort)
  - Emit structured log events for observability
"""

from __future__ import annotations

import time

from backend.app.core.config import settings
from backend.app.core.logging import get_logger, log_event
from backend.app.core.exceptions import AgentError, NoReposConfiguredError
from backend.app.agent.graph import get_app
from backend.app.agent.state import AgentState
from backend.app.schemas.chat import Citation, QueryRequest, QueryResponse
from backend.app.database.repositories.history import history_repository
from backend.app.database.repositories.repos import repo_repository

logger = get_logger(__name__)


class ChatService:
    """Orchestrates a full query → answer pipeline execution."""

    def chat(self, req: QueryRequest) -> QueryResponse:
        """
        Run the full multi-agent RAG pipeline.

        Args:
            req: Validated QueryRequest from the API layer.

        Returns:
            QueryResponse with answer, citations, routing metadata, latency.

        Raises:
            NoReposConfiguredError: if no repos have been indexed.
            AgentError: if the LangGraph pipeline fails.
        """
        log_event(logger, "request_started", query_len=len(req.query))

        # Pre-condition: must have at least one repo indexed
        try:
            configured_repos = repo_repository.get_all()
        except Exception as e:
            logger.warning("db_unavailable_for_repos_check", extra={"error": str(e)})
            configured_repos = []

        if not configured_repos:
            raise NoReposConfiguredError(
                "No repositories configured. "
                "Please add and index at least one repository before querying."
            )

        graph = get_app()
        initial_repos = req.repos if req.repos else []

        initial_state: AgentState = {
            "query": req.query,
            "routed_repos": initial_repos,
            "routed_types": [],
            "code_chunks": [],
            "commit_chunks": [],
            "readme_chunks": [],
            "ambiguity_flag": False,
            "ambiguity_detail": "",
            "conversation_history": [
                {"query": t.query, "answer": t.answer}
                for t in (req.conversation_history or [])
            ],
            "final_answer": "",
            "citations": [],
        }

        t0 = time.perf_counter()
        log_event(logger, "pipeline_started")

        try:
            result = graph.invoke(initial_state)
        except Exception as e:
            raise AgentError(f"Pipeline execution failed: {e}") from e

        latency_ms = (time.perf_counter() - t0) * 1000
        log_event(logger, "pipeline_completed", latency_ms=round(latency_ms, 1))

        citations_raw = result.get("citations", [])
        citations = [
            Citation(
                repo=c.get("repo", ""),
                file_path=c.get("file_path"),
                start_line=c.get("start_line"),
                end_line=c.get("end_line"),
                symbol_name=c.get("symbol_name"),
                commit_hash=c.get("commit_hash"),
                language=c.get("language"),
                snippet=c.get("snippet", ""),
                chunk_type=c.get("chunk_type", "code"),
            )
            for c in citations_raw
        ]

        # Persist to Supabase (best-effort — don't fail the request if this fails)
        try:
            history_repository.save(
                query=req.query,
                answer=result.get("final_answer", ""),
                routed_repos=result.get("routed_repos", []),
                routed_types=result.get("routed_types", []),
                citations=citations_raw,
                latency_ms=round(latency_ms, 1),
                ambiguity_flag=result.get("ambiguity_flag", False),
                ambiguity_detail=result.get("ambiguity_detail", ""),
            )
            log_event(logger, "history_saved")
        except Exception as e:
            logger.warning("history_save_failed", extra={"error": str(e)})

        log_event(logger, "request_completed", latency_ms=round(latency_ms, 1))

        return QueryResponse(
            answer=result.get("final_answer", ""),
            citations=citations,
            ambiguity_flag=result.get("ambiguity_flag", False),
            ambiguity_detail=result.get("ambiguity_detail", ""),
            latency_ms=round(latency_ms, 1),
            routed_repos=result.get("routed_repos", []),
            routed_types=result.get("routed_types", []),
        )


# Module-level singleton
chat_service = ChatService()
