"""
agents/synthesizer.py

synthesize_answer node: given retrieved chunks + query, generate a grounded
explanation with explicit file:line citations.

Behaviour:
  - Normal mode    : explain what was found, cite every claim with file:line
  - Ambiguity mode : compare and contrast implementations across repos
  - Commit context : weaves in "why this was built" from commit messages
                     when commit chunks are also present
"""

from __future__ import annotations

import re

from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

import config
from agents.state import AgentState


def _clean_label(text: str) -> str:
    """Strip emoji and non-ASCII from a label so it stays plain text in prompts."""
    cleaned = re.sub(r'[^\x00-\x7F]+', '', text).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or "doc"


_SYSTEM_NORMAL = """\
You are a senior software engineer helping a developer understand their own codebase.
You have been given relevant code chunks, commit history, and documentation retrieved
from the developer's repositories.

RULES — follow strictly:
1. Answer the question using ONLY the provided context. Do not hallucinate.
2. For every factual claim you make, cite the source using this format:
   `[repo/file_path:start_line]`
3. If commit messages are provided, use them to explain WHY the code exists,
   not just WHAT it does.
4. Be concrete — quote function names, variable names, exact line numbers.
5. If the context doesn't contain enough information to answer, say so clearly.
6. Keep your answer focused. Use markdown headers and code blocks where helpful.
"""

_SYSTEM_AMBIGUITY = """\
You are a senior software engineer helping a developer understand their own codebase.
Multiple repositories have implemented related functionality for this query.

RULES — follow strictly:
1. Your primary job is to COMPARE AND CONTRAST the implementations across repos.
2. For every claim, cite the source: `[repo/file_path:start_line]`
3. Identify key differences: different approaches, different trade-offs, different patterns.
4. Conclude with a recommendation: which implementation is more mature / suitable for reuse?
5. Do not hallucinate. Only use the provided context.
6. Use a structured format: one section per repo, then a comparison table, then a conclusion.
"""


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
            parts.append(c.get("content", "")[:1500])   # cap to avoid token overflow
            parts.append("```")

    if commit_chunks:
        parts.append("\n=== COMMIT HISTORY ===")
        for c in commit_chunks[:5]:  # top 5 commits
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
        model=config.GROQ_MODEL_PRIMARY,
        temperature=config.GROQ_TEMPERATURE,
        max_tokens=config.GROQ_MAX_TOKENS,
        api_key=config.GROQ_API_KEY,
    )

    messages = [
        SystemMessage(content=system),
        HumanMessage(content=user_message),
    ]

    response = llm.invoke(messages)
    answer = response.content.strip()

    print(f"[synthesizer] Generated {len(answer)} chars (history_turns={len(conversation_history)})")
    return {"final_answer": answer}

