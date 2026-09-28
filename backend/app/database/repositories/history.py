"""
backend/app/database/repositories/history.py

Repository layer for the `query_history` Supabase table.
"""

from __future__ import annotations

from backend.app.database.client import get_client
from backend.app.core.exceptions import DatabaseError


class HistoryRepository:
    """CRUD operations for the query_history table."""

    def save(
        self,
        query: str,
        answer: str,
        routed_repos: list[str],
        routed_types: list[str],
        citations: list[dict],
        latency_ms: float,
        ambiguity_flag: bool = False,
        ambiguity_detail: str = "",
    ) -> int:
        """Insert a query record and return its ID."""
        try:
            sb = get_client()
            res = sb.table("query_history").insert({
                "query": query,
                "answer": answer,
                "routed_repos": routed_repos,
                "routed_types": routed_types,
                "citations": citations,
                "latency_ms": latency_ms,
                "ambiguity_flag": ambiguity_flag,
                "ambiguity_detail": ambiguity_detail,
            }).execute()
            return res.data[0]["id"] if res.data else -1
        except Exception as e:
            raise DatabaseError(f"Failed to save query history: {e}") from e

    def get_recent(self, limit: int = 100) -> list[dict]:
        """Return most recent queries, newest first."""
        try:
            sb = get_client()
            res = (
                sb.table("query_history")
                .select(
                    "id,query,answer,routed_repos,routed_types,citations,"
                    "latency_ms,ambiguity_flag,ambiguity_detail,saved,created_at"
                )
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise DatabaseError(f"Failed to fetch query history: {e}") from e

    def toggle_saved(self, history_id: int, saved: bool) -> None:
        try:
            sb = get_client()
            sb.table("query_history").update({"saved": saved}).eq("id", history_id).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to toggle saved flag: {e}") from e

    def delete(self, history_id: int) -> None:
        try:
            sb = get_client()
            sb.table("query_history").delete().eq("id", history_id).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to delete history item {history_id}: {e}") from e

    def bulk_delete(self, ids: list[int]) -> None:
        if not ids:
            return
        try:
            sb = get_client()
            sb.table("query_history").delete().in_("id", ids).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to bulk delete history items: {e}") from e


# Module-level singleton
history_repository = HistoryRepository()
