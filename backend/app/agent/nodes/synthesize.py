"""
backend/app/agent/nodes/synthesize.py

synthesize_answer node: given retrieved chunks + query, generate a grounded
explanation with explicit file:line citations.

Behaviour:
  - Normal mode    : explain what was found, cite every claim with file:line
  - Ambiguity mode : compare and contrast implementations across repos
  - Commit context : weaves in "why this was built" from commit messages
                     when commit chunks are also present

Ported from agents/synthesizer.py — logic preserved exactly.
"""

from __future__ import annotations

import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.agent.state import AgentState

logger = get_logger(__name__)


def _clean_label(text: str) -> str:
    """Strip emoji and non-ASCII from a label so it stays plain text in prompts."""
    cleaned = re.sub(r'[^\x00-\x7F]+', '', text).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or "doc"


from backend.app.agent.prompts.answer import SYNTHESIZE_NORMAL, SYNTHESIZE_AMBIGUITY

# Aliases to avoid changing call sites
_SYSTEM_NORMAL = SYNTHESIZE_NORMAL
_SYSTEM_AMBIGUITY = SYNTHESIZE_AMBIGUITY



def _format_chunks_for_prompt(
    code_chunks: list[dict],
    commit_chunks: list[dict],
    readme_chunks: list[dict],
) -> str:
    """Serialise retrieved chunks into a prompt-friendly text block."""
    parts: list[str] = []

    if code_chunks:
        parts.append("=== CODE CHUNKS ===")
        for i, c in enumerate(code_chunks, 1):
            loc = f"{c.get('repo', '?')}/{c.get('file_path', '?')}:{c.get('start_line', '?')}-{c.get('end_line', '?')}"
            sym = c.get("symbol_name") or "—"
            parts.append(f"\n[{i}] {loc} | symbol: {sym}")
            parts.append("```")
            parts.append(c.get("content", "")[:1500])
            parts.append("```")

    if commit_chunks:
        parts.append("\n=== COMMIT HISTORY ===")
        for c in commit_chunks[:5]:
            parts.append(
                f"• [{c.get('repo')}] {c.get('commit_hash', '?')[:8]} "
                f"({c.get('commit_date', '?')[:10]}): {c.get('commit_message', '?')[:200]}"
            )

    if readme_chunks:
        parts.append("\n=== DOCUMENTATION ===")
        for c in readme_chunks[:3]:
            loc = f"{c.get('repo', '?')}/{c.get('file_path', '?')}"
            sym = _clean_label(c.get("symbol_name") or "section")
            parts.append(f"\n[doc: {sym} @ {loc}]")
            parts.append(c.get("content", "")[:800])

    return "\n".join(parts)


def synthesize_answer(state: AgentState) -> dict:
    """LangGraph node: generate a grounded, cited answer."""
    query = state["query"]
    code_chunks = state.get("code_chunks", [])
    commit_chunks = state.get("commit_chunks", [])
    readme_chunks = state.get("readme_chunks", [])
    ambiguity_flag = state.get("ambiguity_flag", False)
    ambiguity_detail = state.get("ambiguity_detail", "")
    conversation_history = state.get("conversation_history", [])

    context = _format_chunks_for_prompt(code_chunks, commit_chunks, readme_chunks)

    if not context.strip():
        return {
            "final_answer": (
                "I couldn't find relevant code in the indexed repositories for this query. "
                "Please make sure the repos are ingested and indexed, or try rephrasing your question."
            )
        }

    system = _SYSTEM_AMBIGUITY if ambiguity_flag else _SYSTEM_NORMAL

    # Build prior conversation block (last 3 turns max)
    history_block = ""
    if conversation_history:
        history_block = "=== PRIOR CONVERSATION ===\n"
        for turn in conversation_history[-3:]:
            history_block += f"Q: {turn.get('query', '')}\n"
            history_block += f"A: {turn.get('answer', '')[:500]}...\n\n"
        history_block += "=== END PRIOR CONVERSATION ===\n\n"

    user_message = f"""{history_block}Question: {query}

{f"Note: {ambiguity_detail}" if ambiguity_flag else ""}

Retrieved Context:
{context}

Please answer the question with explicit file:line citations for every claim.
"""

    llm = ChatGroq(
        model=settings.groq_model_primary,
        temperature=settings.groq_temperature,
        max_tokens=settings.groq_max_tokens,
        api_key=settings.groq_api_key,
    )

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user_message),
    ]

    response = llm.invoke(messages)
    answer = response.content.strip()

    logger.info("answer_synthesized", extra={"answer_len": len(answer), "history_turns": len(conversation_history)})
    return {"final_answer": answer}
