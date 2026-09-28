"""
backend/app/ingestion/pipeline.py

Ingestion pipeline — the canonical entry point for loading a repo's data.

This module:
  - Orchestrates loaders, parsers, and chunkers for a single repo
  - Provides helpers for reading/writing JSONL chunk files
  - Exposes _remove_repo_from_jsonl() for use by RepoService during deletes

CLI wrapper: backend/scripts/ingest.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.ingestion.loaders.filesystem import collect_code_files, collect_doc_files
from backend.app.ingestion.loaders.git import ingest_commits
from backend.app.ingestion.parsers.markdown import chunk_readme_file
from backend.app.ingestion.chunkers.python_chunker import chunk_python_file
from backend.app.ingestion.chunkers.javascript import chunk_js_file, is_treesitter_available

logger = get_logger(__name__)

# ── JSONL helpers ──────────────────────────────────────────────────────────────

def write_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def _remove_repo_from_jsonl(jsonl_path: Path, repo_name: str) -> None:
    """Remove all chunks for repo_name from a JSONL file (in-place)."""
    if not jsonl_path.exists():
        return
    lines_to_keep = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    if data.get("repo", "").lower() != repo_name.lower():
                        lines_to_keep.append(line)
                except Exception:
                    lines_to_keep.append(line)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        f.writelines(lines_to_keep)


# ── Per-repo ingestion ─────────────────────────────────────────────────────────

def ingest_repo(
    repo_name: str,
    repo_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Ingest one repo → (code_chunks, commit_chunks, readme_chunks).
    """
    # ── Code chunks ───────────────────────────────────────────────────────────
    code_files = collect_code_files(repo_path)
    code_chunks: list[dict] = []

    py_files = [f for f in code_files if f.suffix == ".py"]
    js_files = [f for f in code_files if f.suffix in {".js", ".jsx", ".ts", ".tsx"}]

    for f in py_files:
        code_chunks.extend(chunk_python_file(f, repo_name, repo_path))

    for f in js_files:
        code_chunks.extend(chunk_js_file(f, repo_name, repo_path))

    # ── Commit chunks ─────────────────────────────────────────────────────────
    commit_chunks = ingest_commits(repo_path, repo_name)

    # ── README / doc chunks ───────────────────────────────────────────────────
    doc_files = collect_doc_files(repo_path)
    readme_chunks: list[dict] = []
    for f in doc_files:
        readme_chunks.extend(chunk_readme_file(f, repo_name, repo_path))

    logger.info(
        "ingestion_repo_complete",
        extra={
            "repo": repo_name,
            "code": len(code_chunks),
            "commits": len(commit_chunks),
            "readme": len(readme_chunks),
        },
    )
    return code_chunks, commit_chunks, readme_chunks


def ingest_and_write(
    repo_name: str,
    repo_path: Path,
    output_dir: Path | None = None,
) -> dict[str, int]:
    """
    Ingest a repo and write chunks to JSONL files.

    - Removes any prior chunks for this repo first (to prevent duplicates).
    - Appends new chunks to the shared JSONL files.

    Returns dict with chunk counts per type.
    """
    if output_dir is None:
        output_dir = settings.chunks_dir

    code_chunks, commit_chunks, readme_chunks = ingest_repo(repo_name, repo_path)

    for jsonl_path in [
        output_dir / "code_chunks.jsonl",
        output_dir / "commit_chunks.jsonl",
        output_dir / "readme_chunks.jsonl",
    ]:
        _remove_repo_from_jsonl(jsonl_path, repo_name)

    append_jsonl(output_dir / "code_chunks.jsonl", code_chunks)
    append_jsonl(output_dir / "commit_chunks.jsonl", commit_chunks)
    append_jsonl(output_dir / "readme_chunks.jsonl", readme_chunks)

    return {
        "code": len(code_chunks),
        "commits": len(commit_chunks),
        "readme": len(readme_chunks),
    }
