"""
backend/app/database/repositories/repos.py

Repository layer for the `repos` Supabase table.

Every database operation for repos goes through this module.
No other layer (services, routes, agent) should call the Supabase client directly.
"""

from __future__ import annotations

from backend.app.database.client import get_client
from backend.app.core.exceptions import DatabaseError


class RepoRepository:
    """CRUD operations for the repos table."""

    def get_all(self) -> list[dict]:
        """Return all repos ordered by creation time."""
        try:
            sb = get_client()
            res = (
                sb.table("repos")
                .select("name,url,last_synced,chunk_count")
                .order("created_at")
                .execute()
            )
            return res.data or []
        except Exception as e:
            raise DatabaseError(f"Failed to fetch repos: {e}") from e

    def exists(self, name: str) -> bool:
        try:
            sb = get_client()
            res = sb.table("repos").select("id").ilike("name", name).limit(1).execute()
            return len(res.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to check repo existence: {e}") from e

    def upsert(self, name: str, url: str, last_synced: str = "", chunk_count: int = 0) -> None:
        try:
            sb = get_client()
            sb.table("repos").upsert(
                {"name": name, "url": url, "last_synced": last_synced, "chunk_count": chunk_count},
                on_conflict="name",
            ).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to upsert repo '{name}': {e}") from e

    def update_sync(self, name: str, last_synced: str, chunk_count: int = 0) -> None:
        try:
            sb = get_client()
            sb.table("repos").update(
                {"last_synced": last_synced, "chunk_count": chunk_count}
            ).ilike("name", name).execute()
        except Exception as e:
            raise DatabaseError(f"Failed to update repo sync metadata: {e}") from e

    def delete(self, name: str) -> bool:
        try:
            sb = get_client()
            res = sb.table("repos").delete().ilike("name", name).execute()
            return len(res.data) > 0
        except Exception as e:
            raise DatabaseError(f"Failed to delete repo '{name}': {e}") from e


# Module-level singleton
repo_repository = RepoRepository()
