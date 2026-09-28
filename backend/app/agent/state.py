"""
backend/app/agent/state.py

LangGraph AgentState TypedDict — single source of truth for graph state.

Every node in the graph reads from and writes back to this shared state object.
Annotated fields with operator.add are automatically merged when parallel
branches write to them (fan-out → join pattern).

This is a direct port of agents/state.py — the structure is preserved exactly
so that existing graph nodes and eval code remain compatible.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    query: str

    # ── Router output ──────────────────────────────────────────────────────
    routed_repos: list[str]   # subset of repo names from repos.json
    routed_types: list[str]   # subset of ["code", "commits", "readme"]

    # ── Retrieval output (Annotated → merged across parallel branches) ─────
    code_chunks: Annotated[list[dict[str, Any]], operator.add]
    commit_chunks: Annotated[list[dict[str, Any]], operator.add]
    readme_chunks: Annotated[list[dict[str, Any]], operator.add]

    # ── Ambiguity ──────────────────────────────────────────────────────────
    ambiguity_flag: bool
    ambiguity_detail: str       # human-readable explanation shown in the UI

    # ── Multi-turn conversation memory (session-only, not persisted) ────────
    conversation_history: list[dict[str, Any]]   # [{query, answer}, ...]

    # ── Output ─────────────────────────────────────────────────────────────
    final_answer: str
    citations: list[dict[str, Any]]
