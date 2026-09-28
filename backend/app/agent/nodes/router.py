"""
backend/app/agent/nodes/router.py

route_query node: given a user query, classify it into:
  - routed_repos : which repos are likely relevant  (subset of available repos)
  - routed_types : which content types to search    (code | commits | readme)

Uses Groq Llama 3.3 70B with a few-shot JSON prompt.
Falls back to "search everything" if the LLM response fails to parse.

Ported from agents/router.py — logic preserved exactly.
"""

from __future__ import annotations

import json

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.agent.state import AgentState

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Read available repo names (dynamically, not hardcoded)
# ─────────────────────────────────────────────────────────────────────────────

def _load_repo_names() -> list[str]:
    """Load repo names from Supabase (primary) or fall back to local repos.json."""
    # Always try Supabase first — repos are stored there, not in a local file
    try:
        from backend.app.database.repositories.repos import repo_repository
        repos = repo_repository.get_all()
        if repos:
            return [r["name"] for r in repos]
    except Exception:
        pass

    # Fallback: local repos.json (only present in local dev)
    if settings.repos_config_file.exists():
        try:
            with open(settings.repos_config_file) as f:
                repos = json.load(f)
            return [r["name"] for r in repos]
        except Exception:
            pass

    return []


def _get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.groq_model_primary,
        temperature=settings.groq_temperature,
        api_key=settings.groq_api_key,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Prompt (unchanged from original)
# ─────────────────────────────────────────────────────────────────────────────

from backend.app.agent.prompts.router import ROUTER_SYSTEM, ROUTER_USER


# Keep _SYSTEM_PROMPT as an alias to avoid changing all call sites
_SYSTEM_PROMPT = ROUTER_SYSTEM



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

        logger.info(
            "route_query",
            extra={"repos": valid_filter, "types": routed_types, "source": "user_filter"},
        )
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

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        routed_repos = parsed.get("routed_repos", available_repos)
        routed_types = parsed.get("routed_types", ["code", "commits", "readme"])

        routed_repos = [r for r in routed_repos if r in available_repos] or available_repos
        routed_types = [t for t in routed_types if t in {"code", "commits", "readme"}]
        routed_types = routed_types or ["code", "commits", "readme"]

    except Exception as exc:
        logger.warning("route_query fallback to all repos", extra={"error": str(exc)})
        routed_repos = available_repos
        routed_types = ["code", "commits", "readme"]

    logger.info(
        "route_query",
        extra={"repos": routed_repos, "types": routed_types, "source": "llm"},
    )
    return {
        "routed_repos": routed_repos,
        "routed_types": routed_types,
    }
