"""
backend/app/database/storage.py

Supabase Storage integration for persisting FAISS + BM25 index files.

Problem: Render free plan has no persistent disk, so index files (.faiss, .meta, .pkl)
         and chunk JSONL files are wiped on every restart/redeploy.

Solution: After each indexing run, upload all index + chunk files to a Supabase
          Storage bucket. On startup, download them back to the local temp dir.

Usage:
    from backend.app.database.storage import index_storage
    index_storage.download_all()   # on startup
    index_storage.upload_all()     # after indexing
"""

from __future__ import annotations

import io
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.database.client import get_client

logger = get_logger(__name__)

BUCKET_NAME = "kb-indexes"

# Files to persist: relative path (from indexes_dir or chunks_dir) → storage key
_INDEX_FILES = [
    # FAISS indexes + metadata
    ("indexes/faiss/code.faiss",       "faiss/code.faiss"),
    ("indexes/faiss/code.faiss.meta",  "faiss/code.faiss.meta"),
    ("indexes/faiss/commits.faiss",    "faiss/commits.faiss"),
    ("indexes/faiss/commits.faiss.meta", "faiss/commits.faiss.meta"),
    ("indexes/faiss/readme.faiss",     "faiss/readme.faiss"),
    ("indexes/faiss/readme.faiss.meta","faiss/readme.faiss.meta"),
    # BM25
    ("indexes/bm25/bm25_code.pkl",     "bm25/bm25_code.pkl"),
    # JSONL chunks (needed to rebuild index after repo deletion)
    ("processed/code_chunks.jsonl",    "chunks/code_chunks.jsonl"),
    ("processed/commit_chunks.jsonl",  "chunks/commit_chunks.jsonl"),
    ("processed/readme_chunks.jsonl",  "chunks/readme_chunks.jsonl"),
]


class IndexStorage:
    """Upload and download index files to/from Supabase Storage."""

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist (idempotent)."""
        try:
            sb = get_client()
            buckets = [b.name for b in sb.storage.list_buckets()]
            if BUCKET_NAME not in buckets:
                sb.storage.create_bucket(BUCKET_NAME, options={"public": False})
                logger.info("storage_bucket_created", extra={"bucket": BUCKET_NAME})
        except Exception as e:
            logger.warning("storage_bucket_check_failed", extra={"error": str(e)})

    def upload_all(self) -> dict[str, bool]:
        """
        Upload all index + chunk files to Supabase Storage.
        Called after a successful indexing run.
        Returns dict of {storage_key: success}.
        """
        self._ensure_bucket()
        sb = get_client()
        results: dict[str, bool] = {}
        data_dir = settings.data_dir

        for rel_local, storage_key in _INDEX_FILES:
            local_path = data_dir / rel_local
            if not local_path.exists():
                logger.debug("storage_upload_skip_missing", extra={"file": rel_local})
                results[storage_key] = False
                continue
            try:
                file_bytes = local_path.read_bytes()
                # upsert = overwrite if exists
                sb.storage.from_(BUCKET_NAME).upload(
                    path=storage_key,
                    file=file_bytes,
                    file_options={"upsert": "true"},
                )
                logger.info("storage_uploaded", extra={"key": storage_key, "size_kb": len(file_bytes) // 1024})
                results[storage_key] = True
            except Exception as e:
                logger.error("storage_upload_failed", extra={"key": storage_key, "error": str(e)})
                results[storage_key] = False

        return results

    def download_all(self) -> dict[str, bool]:
        """
        Download all index + chunk files from Supabase Storage to local disk.
        Called on server startup. Skips files not in storage (first deploy).
        Returns dict of {storage_key: success}.
        """
        self._ensure_bucket()
        sb = get_client()
        results: dict[str, bool] = {}
        data_dir = settings.data_dir

        # List what's in the bucket
        try:
            existing_keys: set[str] = set()
            for folder in ["faiss", "bm25", "chunks"]:
                try:
                    items = sb.storage.from_(BUCKET_NAME).list(folder)
                    for item in items:
                        existing_keys.add(f"{folder}/{item['name']}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning("storage_list_failed", extra={"error": str(e)})
            existing_keys = set()

        for rel_local, storage_key in _INDEX_FILES:
            if storage_key not in existing_keys:
                logger.debug("storage_not_found_skip", extra={"key": storage_key})
                results[storage_key] = False
                continue

            local_path = data_dir / rel_local
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
                data = sb.storage.from_(BUCKET_NAME).download(storage_key)
                local_path.write_bytes(data)
                logger.info("storage_downloaded", extra={"key": storage_key, "size_kb": len(data) // 1024})
                results[storage_key] = True
            except Exception as e:
                logger.error("storage_download_failed", extra={"key": storage_key, "error": str(e)})
                results[storage_key] = False

        return results

    def delete_repo_files(self, repo_name: str) -> None:
        """
        After removing a repo from indexes and re-saving locally,
        re-upload the modified files to storage.
        """
        logger.info("storage_syncing_after_delete", extra={"repo": repo_name})
        self.upload_all()

    def status(self) -> dict:
        """Return which storage files exist in the bucket."""
        try:
            sb = get_client()
            existing_keys: set[str] = set()
            for folder in ["faiss", "bm25", "chunks"]:
                try:
                    items = sb.storage.from_(BUCKET_NAME).list(folder)
                    for item in items:
                        existing_keys.add(f"{folder}/{item['name']}")
                except Exception:
                    pass
            return {
                storage_key: storage_key in existing_keys
                for _, storage_key in _INDEX_FILES
            }
        except Exception as e:
            return {"error": str(e)}


# Module-level singleton
index_storage = IndexStorage()
