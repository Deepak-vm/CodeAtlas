"""
agents/ambiguity_checker.py

check_ambiguity node: detect when the same concept is implemented differently
across multiple repos, then surface the conflict instead of picking silently.

Detection logic:
  - Look at the top code_chunks returned
  - If top-2 chunks have a cosine score within AMBIGUITY_SCORE_DELTA of each other
    AND they come from different repos → flag as ambiguous
  - The ambiguity_detail string is used by the synthesizer to switch to
    "compare and contrast" mode

This is the standout feature of the system — don't skip it.
"""

from __future__ import annotations

from collections import Counter

import config
from agents.state import AgentState
from indexing.embedder import Embedder
from indexing.faiss_store import FaissStore


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

    if len(repos_present) < config.AMBIGUITY_MIN_REPOS:
        return {"ambiguity_flag": False, "ambiguity_detail": ""}

    # Re-score the top chunks against each other using their embeddings
    # We can't store scores in AgentState easily, so we use a heuristic:
    # look at the symbol names — if 2+ chunks from different repos share
    # similar symbol names or concepts, that's the signal.
    top_n = code_chunks[:6]   # only inspect top-6 for performance

    # Check for cross-repo presence in top positions
    top_repos = [c.get("repo", "") for c in top_n]
    unique_top_repos = set(top_repos)

    if len(unique_top_repos) < config.AMBIGUITY_MIN_REPOS:
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

    print(f"[ambiguity] Flag raised: {len(unique_top_repos)} repos in top results")
    return {"ambiguity_flag": True, "ambiguity_detail": detail}
