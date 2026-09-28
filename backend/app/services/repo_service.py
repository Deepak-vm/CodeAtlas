"""
backend/app/services/repo_service.py

RepoService — all business logic for adding, updating, and deleting repositories.

Responsibilities:
  - Validate repo name uniqueness
  - Orchestrate ingestion via the new backend/app/ingestion/ package
  - Orchestrate indexing via the new backend/app/indexing/ package
  - Update Supabase metadata
  - Invalidate in-memory index caches
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger, log_event
from backend.app.core.exceptions import (
    IngestionError,
    RepoDuplicateError,
    RepositoryNotFoundError,
)
from backend.app.database.repositories.repos import repo_repository

logger = get_logger(__name__)


def _invalidate_index_cache() -> None:
    from backend.app.agent.nodes.retrieve import invalidate_index_cache
    invalidate_index_cache()


class RepoService:
    """Orchestrates repository ingestion, indexing, and metadata persistence."""

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_chunk_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for chunk_file in [
            settings.code_chunks_file,
            settings.commit_chunks_file,
            settings.readme_chunks_file,
        ]:
            if chunk_file.exists():
                try:
                    with open(chunk_file, encoding="utf-8") as f:
                        for line in f:
                            line_str = line.strip()
                            if line_str:
                                data = json.loads(line_str)
                                repo = data.get("repo", "unknown")
                                counts[repo] = counts.get(repo, 0) + 1
                except Exception:
                    pass
        return counts

    def _get_last_sync_time(self) -> str:
        import time
        paths = [settings.code_faiss_path, settings.code_chunks_file]
        for p in paths:
            if p.exists():
                mtime = p.stat().st_mtime
                diff_min = max(0, int((time.time() - mtime) / 60))
                if diff_min < 1:
                    return "Just now"
                elif diff_min < 60:
                    return f"{diff_min} min ago"
                else:
                    return f"{diff_min // 60} h ago"
        return "Not synced yet"

    def _resolve_repo_path(self, entry: dict) -> Path:
        """Resolve a repo entry to a local path, cloning if needed."""
        import subprocess

        if "path" in entry:
            p = Path(entry["path"]).expanduser().resolve()
            if not p.is_dir():
                raise IngestionError(f"Repo path does not exist: {p}")
            return p

        if "url" in entry:
            name = entry.get("name") or entry["url"].rstrip("/").split("/")[-1].removesuffix(".git")
            dest = settings.repos_dir / name
            if dest.exists():
                return dest
            settings.repos_dir.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(
                ["git", "clone", "--depth", "500", entry["url"], str(dest)],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise IngestionError(f"git clone failed: {result.stderr[:300]}")
            return dest

        raise IngestionError(f"Repo entry must have 'path' or 'url': {entry}")

    def _ingest_and_index(self, repo_name: str) -> None:
        """Run ingestion + indexing using the new backend packages."""
        from backend.app.ingestion.pipeline import ingest_and_write
        from backend.app.indexing.pipeline import build_all_indexes

        log_event(logger, "ingestion_started", repo=repo_name)

        # Get the repo's URL/path from DB
        try:
            all_repos = repo_repository.get_all()
        except Exception as e:
            raise IngestionError(f"Could not fetch repos from Supabase: {e}") from e

        entry = next((r for r in all_repos if r["name"].lower() == repo_name.lower()), None)
        if not entry:
            raise IngestionError(f"Repo '{repo_name}' not found in database.")

        repo_path = self._resolve_repo_path(entry)

        try:
            counts = ingest_and_write(repo_name, repo_path)
            log_event(logger, "ingestion_completed", repo=repo_name, **counts)
        except Exception as e:
            raise IngestionError(f"Ingestion failed for '{repo_name}': {e}") from e

        log_event(logger, "indexing_started", repo=repo_name)
        try:
            build_all_indexes(
                chunks_dir=settings.chunks_dir,
                output_dir=settings.indexes_dir,
            )
            log_event(logger, "indexing_completed", repo=repo_name)
        except Exception as e:
            raise IngestionError(f"Indexing failed for '{repo_name}': {e}") from e

        # ── Persist indexes to Supabase Storage (survives Render restarts) ─────
        try:
            from backend.app.database.storage import index_storage
            results = index_storage.upload_all()
            uploaded = sum(1 for v in results.values() if v)
            log_event(logger, "storage_upload_complete", repo=repo_name, uploaded=uploaded, total=len(results))
        except Exception as e:
            # Non-fatal: indexes are on disk for this session, will warn but not fail
            logger.warning("storage_upload_failed", extra={"repo": repo_name, "error": str(e)})

        _invalidate_index_cache()

    def _delete_and_reindex(self, repo_name: str) -> None:
        """Remove a repo's chunks and vectors from all indexes."""
        from backend.app.ingestion.pipeline import _remove_repo_from_jsonl
        from backend.app.indexing.vector.faiss import FaissStore
        from backend.app.indexing.keyword.bm25 import BM25Store

        _remove_repo_from_jsonl(settings.code_chunks_file, repo_name)
        _remove_repo_from_jsonl(settings.commit_chunks_file, repo_name)
        _remove_repo_from_jsonl(settings.readme_chunks_file, repo_name)

        FaissStore.remove_repo_and_save(settings.code_faiss_path, repo_name)
        FaissStore.remove_repo_and_save(settings.commit_faiss_path, repo_name)
        FaissStore.remove_repo_and_save(settings.readme_faiss_path, repo_name)

        BM25Store.remove_repo_and_save(settings.bm25_code_path, repo_name)

        # ── Sync updated indexes back to Supabase Storage ────────────────────
        try:
            from backend.app.database.storage import index_storage
            index_storage.upload_all()
        except Exception as e:
            logger.warning("storage_sync_after_delete_failed", extra={"error": str(e)})

        _invalidate_index_cache()
        log_event(logger, "repo_deleted_from_index", repo=repo_name)

    # ── Public API ────────────────────────────────────────────────────────

    def list_repos(self) -> dict:
        config_repos = repo_repository.get_all()
        chunk_counts = self._get_chunk_counts()
        last_sync = self._get_last_sync_time()

        repos_detail = [
            {
                "name": r["name"],
                "url": r.get("url", ""),
                "chunk_count": chunk_counts.get(r["name"], r.get("chunk_count", 0)),
                "last_synced": r.get("last_synced", last_sync),
            }
            for r in config_repos
        ]
        names = [r["name"] for r in config_repos]
        return {
            "repos": names,
            "repos_detail": repos_detail,
            "count": len(names),
            "chunk_counts": chunk_counts,
            "last_sync": last_sync,
        }

    def add_repo(self, name: str, url: str) -> dict:
        name = name.strip()
        url = url.strip()

        if repo_repository.exists(name):
            raise RepoDuplicateError(f"Repository '{name}' already exists.")

        now = datetime.datetime.now().strftime("%I:%M %p")
        repo_repository.upsert(name=name, url=url, last_synced=now)

        try:
            self._ingest_and_index(name)
        except Exception as e:
            try:
                repo_repository.delete(name)
            except Exception:
                pass
            raise IngestionError(f"Failed to ingest/index '{name}': {e}") from e

        chunk_counts = self._get_chunk_counts()
        try:
            repo_repository.update_sync(
                name=name,
                last_synced=now,
                chunk_count=chunk_counts.get(name, 0),
            )
        except Exception:
            pass

        return {"status": "ok", "message": f"Repository '{name}' added and indexed successfully."}

    def delete_repo(self, name: str) -> dict:
        if not repo_repository.exists(name):
            raise RepositoryNotFoundError(f"Repository '{name}' not found.")
        repo_repository.delete(name)
        self._delete_and_reindex(name)
        return {"status": "ok", "message": f"Repository '{name}' removed and index updated."}

    def update_repo(self, name: str) -> dict:
        if not repo_repository.exists(name):
            raise RepositoryNotFoundError(f"Repository '{name}' not found.")
        self._delete_and_reindex(name)
        self._ingest_and_index(name)
        now = datetime.datetime.now().strftime("%I:%M %p")
        chunk_counts = self._get_chunk_counts()
        repo_repository.update_sync(
            name=name,
            last_synced=now,
            chunk_count=chunk_counts.get(name, 0),
        )
        return {"status": "ok", "message": f"Repository '{name}' updated successfully."}

    def get_health(self) -> dict:
        from backend.app.agent.nodes.retrieve import _get_pipeline
        try:
            pipeline = _get_pipeline()
            index_status = pipeline.index_status
        except Exception:
            index_status = {
                "code": settings.code_faiss_path.exists(),
                "commits": settings.commit_faiss_path.exists(),
                "readme": settings.readme_faiss_path.exists(),
                "bm25_code": settings.bm25_code_path.exists(),
            }
        try:
            repo_names = [r["name"] for r in repo_repository.get_all()]
        except Exception:
            repo_names = []
        return {"index_status": index_status, "repo_names": repo_names}


# Module-level singleton
repo_service = RepoService()
