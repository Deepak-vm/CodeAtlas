"""
ingestion/commit_ingester.py

Ingests git commit history for a repository using GitPython.
Each commit becomes one document chunk capturing: hash, message, date, author,
and the list of files changed.

Strategy:
  - Walk all branches (all=True → git log --all)
  - Cap at MAX_COMMIT_HISTORY commits per repo
  - Skip merge commits by default (configurable)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import MAX_COMMIT_HISTORY


def ingest_commits(
    repo_path: Path,
    repo: str,
    max_commits: int = MAX_COMMIT_HISTORY,
    skip_merges: bool = True,
) -> list[dict[str, Any]]:
    """
    Return a list of commit chunks for the given repo.

    Parameters
    ----------
    repo_path   : local path to the repository root
    repo        : short name of the repo (used in chunk metadata)
    max_commits : maximum number of commits to ingest
    skip_merges : if True, skip merge commits (usually noisy)
    """
    try:
        import git  # GitPython
    except ImportError:
        raise ImportError("gitpython is required: pip install gitpython")

    try:
        git_repo = git.Repo(str(repo_path), search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        print(f"  [warn] {repo_path} is not a git repository — skipping commits")
        return []

    chunks: list[dict] = []
    count = 0

    for commit in git_repo.iter_commits(all=True):
        if count >= max_commits:
            break
        if skip_merges and len(commit.parents) > 1:
            continue

        # Collect changed files — stats can be slow on large repos; guard it
        try:
            changed_files = list(commit.stats.files.keys())
        except Exception:
            changed_files = []

        # Compose a rich text blob for embedding
        content_parts = [
            f"commit: {commit.hexsha}",
            f"author: {commit.author.name} <{commit.author.email}>",
            f"date: {_format_dt(commit.authored_datetime)}",
            f"message: {commit.message.strip()}",
        ]
        if changed_files:
            content_parts.append("changed files:\n  " + "\n  ".join(changed_files[:30]))

        # Use the first changed file as the primary file_path so that
        # file-hit scoring and citations can match on it (e.g. 'router.py').
        primary_file = changed_files[0] if changed_files else None

        # Subject line of the commit message (first line, max 120 chars)
        subject = commit.message.strip().splitlines()[0][:120]

        chunk: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "chunk_type": "commit",
            "repo": repo,
            "file_path": primary_file,       # first changed file — enables file-hit scoring
            "content": "\n".join(content_parts),
            "symbol_name": subject,           # commit subject — surfaces in citations
            "language": None,
            "start_line": None,
            "end_line": None,
            "commit_hash": commit.hexsha,
            "commit_message": commit.message.strip(),
            "commit_date": _format_dt(commit.authored_datetime),
            "changed_files": changed_files,
        }

        chunks.append(chunk)
        count += 1

    return chunks


def _format_dt(dt: datetime) -> str:
    """Return an ISO-8601 string. Ensure tz-aware."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
