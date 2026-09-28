"""
backend/app/agent/nodes/citations.py

format_citations node: extract structured citation objects from the final answer
and from the retrieved chunk metadata.

Rather than parsing the LLM's free-text for [repo/file:line] patterns
(error-prone), we take a more reliable two-step approach:
  1. Parse citation markers from the answer text (best-effort)
  2. Merge with ground-truth metadata from the retrieved chunks

This ensures citations are always backed by real chunk metadata, never hallucinated.

Ported from agents/citation_formatter.py — logic preserved exactly.
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.agent.state import AgentState

logger = get_logger(__name__)

# Matches: [repo/path/to/file.py:12-45] or [repo/file.py:12]
_CITATION_RE = re.compile(
    r"\[(?P<repo>[^/\]]+)/(?P<path>[^\]:]+):(?P<start>\d+)(?:-(?P<end>\d+))?\]"
)


def format_citations(state: AgentState) -> dict:
    """
    LangGraph node: build a structured citations list combining:
      - Markers found in the answer text
      - All retrieved code/commit/readme chunks (always included as context)

    Returns a de-duplicated list of citation dicts, ordered by appearance in answer.
    """
    answer = state.get("final_answer", "")
    code_chunks = state.get("code_chunks", [])
    commit_chunks = state.get("commit_chunks", [])
    readme_chunks = state.get("readme_chunks", [])

    all_chunks = code_chunks + commit_chunks + readme_chunks

    # Build a lookup: (repo, file_path, start_line) → chunk
    chunk_lookup: dict[tuple, dict] = {}
    for c in all_chunks:
        key = (c.get("repo", ""), c.get("file_path", ""), c.get("start_line"))
        chunk_lookup[key] = c

    citations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    # ── Step 1: parse answer text for citation markers ─────────────────────
    for m in _CITATION_RE.finditer(answer):
        repo = m.group("repo")
        path = m.group("path")
        start = int(m.group("start"))
        end = int(m.group("end")) if m.group("end") else start

        key = (repo, path, start)
        chunk = chunk_lookup.get(key)

        citation: dict[str, Any] = {
            "repo": repo,
            "file_path": path,
            "start_line": start,
            "end_line": end,
            "symbol_name": chunk.get("symbol_name") if chunk else None,
            "commit_hash": chunk.get("commit_hash") if chunk else None,
            "language": chunk.get("language") if chunk else None,
            "snippet": _extract_snippet(chunk) if chunk else "",
            "chunk_type": chunk.get("chunk_type", "code") if chunk else "code",
        }

        cid = f"{repo}::{path}::{start}"
        if cid not in seen_ids:
            citations.append(citation)
            seen_ids.add(cid)

    # ── Step 2: always include all retrieved chunks as supporting citations ─
    for chunk in all_chunks:
        cid = chunk.get("id", "")
        if cid in seen_ids:
            continue
        seen_ids.add(cid)

        citation = {
            "repo": chunk.get("repo", ""),
            "file_path": chunk.get("file_path", ""),
            "start_line": chunk.get("start_line"),
            "end_line": chunk.get("end_line"),
            "symbol_name": chunk.get("symbol_name"),
            "commit_hash": chunk.get("commit_hash"),
            "language": chunk.get("language"),
            "snippet": _extract_snippet(chunk),
            "chunk_type": chunk.get("chunk_type", "code"),
        }
        citations.append(citation)

    logger.info("citations_formatted", extra={"count": len(citations)})
    return {"citations": citations}


def _extract_snippet(chunk: dict | None, max_chars: int = 300) -> str:
    """Return a short code snippet from the chunk for display."""
    if not chunk:
        return ""
    content = chunk.get("content", "")
    lines = [
        ln for ln in content.splitlines()
        if not ln.startswith("# ") and not ln.startswith("// ")
    ]
    snippet = "\n".join(lines[:10]).strip()
    return snippet[:max_chars]
