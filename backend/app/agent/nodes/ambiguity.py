"""
backend/app/agent/nodes/ambiguity.py

check_ambiguity node: detect when the same concept is implemented differently
across multiple repos, then surface the conflict instead of picking silently.

Detection logic:
  - Look at the top code_chunks returned
  - If top-2 chunks have a cosine score within AMBIGUITY_SCORE_DELTA of each other
    AND they come from different repos → flag as ambiguous
  - The ambiguity_detail string is used by the synthesizer to switch to
    "compare and contrast" mode

Ported from agents/ambiguity_checker.py — logic preserved exactly.
"""

from __future__ import annotations

from collections import Counter

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.agent.state import AgentState

logger = get_logger(__name__)


def check_ambiguity(state: AgentState) -> dict:
    """
    LangGraph node: analyse retrieved code chunks for cross-repo ambiguity.

    Sets:
      ambiguity_flag   : bool
      ambiguity_detail : human-readable description of the conflict
    """
    code_chunks = state.get("code_chunks", [])

    if len(code_chunks) < 2:
        return {"ambiguity_flag": False, "ambiguity_detail": ""}

    # Count how many repos appear in the retrieved chunks
    repo_counts = Counter(c.get("repo", "") for c in code_chunks)
    repos_present = [r for r in repo_counts if r]

    if len(repos_present) < settings.ambiguity_min_repos:
        return {"ambiguity_flag": False, "ambiguity_detail": ""}

    top_n = code_chunks[:6]

    top_repos = [c.get("repo", "") for c in top_n]
    unique_top_repos = set(top_repos)

    if len(unique_top_repos) < settings.ambiguity_min_repos:
        return {"ambiguity_flag": False, "ambiguity_detail": ""}

    # Build a human-readable summary of what's conflicting
    per_repo: dict[str, list[str]] = {}
    for c in top_n:
        repo = c.get("repo", "unknown")
        sym = c.get("symbol_name") or c.get("file_path", "unknown")
        per_repo.setdefault(repo, []).append(sym)

    detail_parts = []
    for repo, symbols in per_repo.items():
        detail_parts.append(f"  • {repo}: {', '.join(symbols[:3])}")

    detail = (
        f"Multiple repos implement related functionality for this query:\n"
        + "\n".join(detail_parts)
        + "\n\nThe answer will compare implementations across repos."
    )

    logger.info("ambiguity_detected", extra={"unique_repos": len(unique_top_repos)})
    return {"ambiguity_flag": True, "ambiguity_detail": detail}
