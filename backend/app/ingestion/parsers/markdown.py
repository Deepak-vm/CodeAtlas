"""
ingestion/readme_ingester.py

Chunks README and other documentation files.

Strategy:
  - Split on Markdown headings (## / ###) to produce logical sections
  - Each section → one chunk with the heading as symbol_name
  - Fallback: fixed-size window for plain text / RST files
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any


_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def chunk_readme_file(
    file_path: Path,
    repo: str,
    repo_root: Path,
) -> list[dict[str, Any]]:
    """
    Parse a documentation file and return section-level chunk dicts.
    """
    rel_path = file_path.relative_to(repo_root).as_posix()

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    suffix = file_path.suffix.lower()
    if suffix in {".md"}:
        return _chunk_markdown(source, repo, rel_path)
    else:
        # RST / plain text → simple sliding window
        return _chunk_plain(source, repo, rel_path)


# ─────────────────────────────────────────────────────────────────────────────

def _chunk_markdown(
    source: str,
    repo: str,
    file_path: str,
    min_section_chars: int = 50,
) -> list[dict]:
    """Split markdown on heading boundaries."""
    lines = source.splitlines(keepends=True)
    total_lines = len(lines)

    # Find heading positions
    splits: list[tuple[int, str]] = []  # (line_number_1indexed, heading_text)
    for i, line in enumerate(lines, start=1):
        m = _HEADING_RE.match(line.rstrip())
        if m:
            splits.append((i, m.group(2).strip()))

    if not splits:
        # No headings — treat entire file as one chunk
        return [_make_doc_chunk(repo, file_path, source.strip(), "README", 1, total_lines)]

    chunks: list[dict] = []

    # Section before the first heading (e.g. badges, tagline)
    if splits[0][0] > 1:
        pre = "".join(lines[: splits[0][0] - 1]).strip()
        if pre and len(pre) >= min_section_chars:
            chunks.append(
                _make_doc_chunk(repo, file_path, pre, "preamble", 1, splits[0][0] - 1)
            )

    for idx, (start_line, heading) in enumerate(splits):
        end_line = splits[idx + 1][0] - 1 if idx + 1 < len(splits) else total_lines
        content = "".join(lines[start_line - 1 : end_line]).strip()
        if content and len(content) >= min_section_chars:
            chunks.append(
                _make_doc_chunk(repo, file_path, content, heading, start_line, end_line)
            )

    return chunks


def _chunk_plain(
    source: str,
    repo: str,
    file_path: str,
    window: int = 60,
    overlap: int = 10,
) -> list[dict]:
    lines = source.splitlines(keepends=True)
    total = len(lines)
    step = window - overlap
    chunks = []
    start = 1
    while start <= total:
        end = min(start + window - 1, total)
        content = "".join(lines[start - 1 : end]).strip()
        if content:
            chunks.append(_make_doc_chunk(repo, file_path, content, None, start, end))
        start += step
    return chunks


def _make_doc_chunk(
    repo: str,
    file_path: str,
    content: str,
    symbol_name: str | None,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "chunk_type": "readme",
        "repo": repo,
        "file_path": file_path,
        "content": content,
        "symbol_name": symbol_name,
        "language": "markdown",
        "start_line": start_line,
        "end_line": end_line,
        "commit_hash": None,
        "commit_message": None,
        "commit_date": None,
        "changed_files": [],
    }
