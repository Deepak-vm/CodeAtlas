"""
backend/app/agent/graph.py

LangGraph StateGraph assembly for the Knowledge Base Agent.

Graph topology:

  START
    │
    ▼
  route_query                     ← classify repo + content type
    │
    ├──────────────────────────────────────────────────────────┐
    ▼                             ▼                            ▼
  retrieve_code            retrieve_commits           retrieve_readme
  (FAISS+BM25 hybrid)      (FAISS dense)             (FAISS dense)
    │                             │                            │
    └──────────────────────┬──────┘────────────────────────────┘
                           ▼
                     check_ambiguity      ← cross-repo conflict detection
                           │
                           ▼
                    synthesize_answer     ← Groq Llama 3.3 70B
                           │
                           ▼
                    format_citations      ← structured citation list
                           │
                           ▼
                          END

The graph is built once at startup and reused for all requests.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from backend.app.agent.state import AgentState
from backend.app.agent.nodes.router import route_query
from backend.app.agent.nodes.retrieve import retrieve_code, retrieve_commits, retrieve_readme
from backend.app.agent.nodes.ambiguity import check_ambiguity
from backend.app.agent.nodes.synthesize import synthesize_answer
from backend.app.agent.nodes.citations import format_citations


def build_graph() -> StateGraph:
    """
    Assemble and compile the full LangGraph StateGraph.
    Call this once at startup and reuse the compiled app.
    """
    builder = StateGraph(AgentState)

    # ── Register nodes ─────────────────────────────────────────────────────
    builder.add_node("route_query", route_query)
    builder.add_node("retrieve_code", retrieve_code)
    builder.add_node("retrieve_commits", retrieve_commits)
    builder.add_node("retrieve_readme", retrieve_readme)
    builder.add_node("check_ambiguity", check_ambiguity)
    builder.add_node("synthesize_answer", synthesize_answer)
    builder.add_node("format_citations", format_citations)

    # ── Edges ──────────────────────────────────────────────────────────────
    builder.add_edge(START, "route_query")

    # Fan-out: router → 3 parallel retrieval branches
    builder.add_edge("route_query", "retrieve_code")
    builder.add_edge("route_query", "retrieve_commits")
    builder.add_edge("route_query", "retrieve_readme")

    # Join: all 3 retrieval nodes → ambiguity checker
    builder.add_edge("retrieve_code", "check_ambiguity")
    builder.add_edge("retrieve_commits", "check_ambiguity")
    builder.add_edge("retrieve_readme", "check_ambiguity")

    # Linear: ambiguity → synthesis → citations → end
    builder.add_edge("check_ambiguity", "synthesize_answer")
    builder.add_edge("synthesize_answer", "format_citations")
    builder.add_edge("format_citations", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level compiled app (lazy singleton)
# ─────────────────────────────────────────────────────────────────────────────
_app = None


def get_app():
    """Return the compiled graph app (lazy singleton)."""
    global _app
    if _app is None:
        _app = build_graph()
    return _app
