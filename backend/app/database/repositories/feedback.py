"""
backend/app/database/repositories/feedback.py

Repository layer for the `feedback` Supabase table.
"""

from __future__ import annotations

from backend.app.database.client import get_client
from backend.app.core.exceptions import DatabaseError


class FeedbackRepository:
    """CRUD operations for the feedback table."""

    def save(
        self,
        query: str,
        answer_snippet: str,
        rating: str,
        routed_repos: list[str],
    ) -> None:
        try:
            sb = get_client()
            sb.table("feedback").insert({
                "query": query,
                "answer_snippet": answer_snippet[:200],
                "rating": rating,
                "routed_repos": routed_repos,
            }).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to save feedback: {e}") from e


# Module-level singleton
feedback_repository = FeedbackRepository()
