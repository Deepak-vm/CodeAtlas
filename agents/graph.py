"""
agents/graph.py

Full LangGraph StateGraph assembly for the Knowledge Base Agent.

Graph topology :

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

Usage:
  from agents.graph import build_graph

  app = build_graph()
  result = app.invoke({"query": "where is my retry logic?"})
  print(result["final_answer"])
  print(result["citations"])
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from agents.state import AgentState
from agents.router import route_query
from agents.retrieval_nodes import retrieve_code, retrieve_commits, retrieve_readme
from agents.ambiguity_checker import check_ambiguity
from agents.synthesizer import synthesize_answer
from agents.citation_formatter import format_citations


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
    # Entry
    builder.add_edge(START, "route_query")

    # Fan-out: router → 3 parallel retrieval branches
    builder.add_edge("route_query", "retrieve_code")
    builder.add_edge("route_query", "retrieve_commits")
    builder.add_edge("route_query", "retrieve_readme")

    # Join: all 3 retrieval nodes → ambiguity checker
    # LangGraph waits for all three to complete before calling check_ambiguity
    builder.add_edge("retrieve_code", "check_ambiguity")
    builder.add_edge("retrieve_commits", "check_ambiguity")
    builder.add_edge("retrieve_readme", "check_ambiguity")

    # Linear: ambiguity → synthesis → citations → end
    builder.add_edge("check_ambiguity", "synthesize_answer")
    builder.add_edge("synthesize_answer", "format_citations")
    builder.add_edge("format_citations", END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level compiled app (singleton)
# ─────────────────────────────────────────────────────────────────────────────
_app = None


def get_app():
    """Return the compiled graph app (lazy singleton)."""
    global _app
    if _app is None:
        _app = build_graph()
    return _app


# ─────────────────────────────────────────────────────────────────────────────
# CLI for quick manual testing 
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel

    console = Console()

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "where have I implemented authentication?"

    console.print(Panel(f"[bold cyan]Query:[/bold cyan] {query}", expand=False))

    app = build_graph()
    result = app.invoke({
        "query": query,
        "routed_repos": [],
        "routed_types": [],
        "code_chunks": [],
        "commit_chunks": [],
        "readme_chunks": [],
        "ambiguity_flag": False,
        "ambiguity_detail": "",
        "final_answer": "",
        "citations": [],
    })

    console.print("\n[bold green]Answer:[/bold green]")
    console.print(Markdown(result["final_answer"]))

    if result.get("ambiguity_flag"):
        console.print(f"\n[bold yellow]⚠ Ambiguity detected:[/bold yellow] {result['ambiguity_detail']}")

    console.print(f"\n[bold]Citations ({len(result['citations'])}):[/bold]")
    for i, c in enumerate(result["citations"][:5], 1):
        console.print(
            f"  [{i}] {c['repo']}/{c['file_path']}:{c['start_line']}"
            + (f"  [{c['symbol_name']}]" if c.get("symbol_name") else "")
        )

