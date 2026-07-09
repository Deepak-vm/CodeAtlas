"""
agents/router.py

route_query node: given a user query, classify it into:
  - routed_repos : which repos are likely relevant  (subset of available repos)
  - routed_types : which content types to search    (code | commits | readme)

Uses Groq Llama 3.3 70B with a few-shot JSON prompt.
Falls back to "search everything" if the LLM response fails to parse.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

import config
from agents.state import AgentState


# ─────────────────────────────────────────────────────────────────────────────
# Read available repo names from repos.json (dynamically, not hardcoded)
# ─────────────────────────────────────────────────────────────────────────────

def _load_repo_names() -> list[str]:
    if config.REPOS_CONFIG_FILE.exists():
        with open(config.REPOS_CONFIG_FILE) as f:
            repos = json.load(f)
        return [r["name"] for r in repos]
    return []


# ─────────────────────────────────────────────────────────────────────────────
# LLM
# ─────────────────────────────────────────────────────────────────────────────

def _get_llm() -> ChatGroq:
    return ChatGroq(
        model=config.GROQ_MODEL_PRIMARY,
        temperature=config.GROQ_TEMPERATURE,
        api_key=config.GROQ_API_KEY,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a query router for a personal codebase knowledge base.
Your job: given a user's question about their own code, decide which repositories
and content types to search.

Available content types:
  - "code"    : source code files (functions, classes, components)
  - "commits" : git commit history (what changed, when, why)
  - "readme"  : documentation, README files, architecture notes

Rules:
  1. If the query is about "where", "how", "show me", "find" → code + readme
  2. If the query is about "when", "why", "who changed", "history" → commits
  3. If the query is vague or could span multiple repos → include all repos
  4. If you can tell from the query which repo it concerns, narrow it down
  5. When uncertain, include everything — over-retrieval is better than missing context
  6. ALWAYS return valid JSON with exactly these keys: routed_repos (list), routed_types (list)

Available repos: {repos_list}

Few-shot examples:
---
Query: "where have I implemented WebSocket real-time features?"
{{ "routed_repos": {repos_list}, "routed_types": ["code", "readme"] }}

Query: "who last changed the retry logic and why?"
{{ "routed_repos": {repos_list}, "routed_types": ["commits", "code"] }}

Query: "what does this project do?"
{{ "routed_repos": {repos_list}, "routed_types": ["readme"] }}

Query: "show me my async task queue implementation"
{{ "routed_repos": {repos_list}, "routed_types": ["code"] }}
---
"""


def route_query(state: AgentState) -> dict:
    """
    LangGraph node: classify the query and populate routed_repos + routed_types.

    IMPORTANT: If routed_repos is already set (user explicitly selected repo filters),
    honour that selection and skip LLM routing for repos — only infer content types.
    """
    query = state["query"]
    already_filtered_repos = state.get("routed_repos", [])
    available_repos = _load_repo_names()

    # Fallback if no repos configured yet
    if not available_repos:
        return {
            "routed_repos": [],
            "routed_types": ["code", "commits", "readme"],
        }

    # ── If the user has already specified repo filters, honour them exactly ──
    if already_filtered_repos:
        # Validate the user-provided repos are real
        valid_filter = [r for r in already_filtered_repos if r in available_repos]
        if not valid_filter:
            valid_filter = available_repos

        # Still ask LLM to determine content types
        repos_str = json.dumps(valid_filter)
        system = _SYSTEM_PROMPT.format(repos_list=repos_str)
        llm = _get_llm()
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=f'Query: "{query}"\nRespond with JSON only.'),
        ]
        try:
            response = llm.invoke(messages)
            raw = response.content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            parsed = json.loads(raw)
            routed_types = parsed.get("routed_types", ["code", "commits", "readme"])
            routed_types = [t for t in routed_types if t in {"code", "commits", "readme"}]
            routed_types = routed_types or ["code", "commits", "readme"]
        except Exception:
            routed_types = ["code", "commits", "readme"]

        print(f"[router] USER FILTER applied: repos={valid_filter} | types={routed_types}")
        return {
            "routed_repos": valid_filter,
            "routed_types": routed_types,
        }

    # ── No user filter — use LLM to decide both repos and types ──
    repos_str = json.dumps(available_repos)
    system = _SYSTEM_PROMPT.format(repos_list=repos_str)

    llm = _get_llm()
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=f'Query: "{query}"\nRespond with JSON only.'),
    ]

    try:
        response = llm.invoke(messages)
        raw = response.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        routed_repos = parsed.get("routed_repos", available_repos)
        routed_types = parsed.get("routed_types", ["code", "commits", "readme"])

        # Validate — only keep valid values
        routed_repos = [r for r in routed_repos if r in available_repos] or available_repos
        routed_types = [t for t in routed_types if t in {"code", "commits", "readme"}]
        routed_types = routed_types or ["code", "commits", "readme"]

    except Exception as e:
        print(f"[router] Failed to parse LLM response: {e} — falling back to all")
        routed_repos = available_repos
        routed_types = ["code", "commits", "readme"]

    print(f"[router] LLM routed: repos={routed_repos} | types={routed_types}")
    return {
        "routed_repos": routed_repos,
        "routed_types": routed_types,
    }

