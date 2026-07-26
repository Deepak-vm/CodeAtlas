"""
ingestion/repo_walker.py

Walks a local repository directory and returns a flat list of files to process,
filtered by extension and skipping noisy directories.
No LLM involved — pure filesystem traversal.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from config import (
    SKIP_DIRS,
    SKIP_FILE_EXTENSIONS,
    SKIP_FILENAMES,
    SUPPORTED_CODE_EXTENSIONS,
)


def _is_binary(file_path: Path, sample_size: int = 8192) -> bool:
    """Heuristic: if the first 8KB contains a null byte, treat as binary."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except OSError:
        return True


def walk_repo(
    repo_path: str | Path,
    include_extensions: set[str] | None = None,
) -> Generator[Path, None, None]:
    """
    Recursively walk *repo_path*, yielding Path objects for each processable file.

    Parameters
    ----------
    repo_path       : root directory of the repository
    include_extensions : if provided, only yield files with these extensions;
                         defaults to SUPPORTED_CODE_EXTENSIONS + [".md", ".rst"]
    """
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        raise ValueError(f"repo_path is not a directory: {repo_path}")

    if include_extensions is None:
        include_extensions = SUPPORTED_CODE_EXTENSIONS | {".md", ".rst", ".txt"}

    for dirpath, dirnames, filenames in os.walk(repo_path, topdown=True):
        # Prune unwanted directories *in-place* so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            # Skip explicitly blocklisted filenames (eval/debug scripts in target repos)
            if filename in SKIP_FILENAMES:
                continue
            file_path = Path(dirpath) / filename
            suffix = file_path.suffix.lower()

            if suffix in SKIP_FILE_EXTENSIONS:
                continue
            if suffix not in include_extensions:
                continue
            if _is_binary(file_path):
                continue

            yield file_path


def collect_code_files(repo_path: str | Path) -> list[Path]:
    """Return all source-code files (Python, JS/TS, etc.) in the repo."""
    return sorted(walk_repo(repo_path, include_extensions=SUPPORTED_CODE_EXTENSIONS))


def collect_doc_files(repo_path: str | Path) -> list[Path]:
    """Return all markdown/rst documentation files in the repo."""
    return sorted(walk_repo(repo_path, include_extensions={".md", ".rst", ".txt"}))


def relative_path(file_path: Path, repo_root: Path) -> str:
    """Return the file path relative to the repo root as a POSIX string."""
    try:
        return file_path.relative_to(repo_root).as_posix()
    except ValueError:
        return file_path.as_posix()

