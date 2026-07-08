"""
agents/retrieval_nodes.py

Three retrieval nodes for the LangGraph StateGraph:
  - retrieve_code    : FAISS dense + BM25 hybrid on code index
  - retrieve_commits : FAISS dense on commit index
  - retrieve_readme  : FAISS dense on readme index

Each node:
  1. Checks if its content type is in state["routed_types"] — skips if not
  2. Filters by state["routed_repos"]
  3. Encodes query with Jina
  4. FAISS search → BM25 rerank (code only) → return top-K chunks

Indexes are loaded once at module import and cached (not reloaded per query).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import config
from agents.state import AgentState
from indexing.embedder import Embedder
from indexing.faiss_store import FaissStore
from indexing.bm25_store import BM25Store


# ─────────────────────────────────────────────────────────────────────────────
# Index caches — loaded once, reused across queries
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _code_faiss() -> FaissStore | None:
    try:
        return FaissStore.load(config.CODE_FAISS_PATH)
    except FileNotFoundError:
        print("[retrieval] Code FAISS index not found — run build_indexes.py first")
        return None


@lru_cache(maxsize=1)
def _commit_faiss() -> FaissStore | None:
    try:
        return FaissStore.load(config.COMMIT_FAISS_PATH)
    except FileNotFoundError:
        print("[retrieval] Commit FAISS index not found — run build_indexes.py first")
        return None


@lru_cache(maxsize=1)
def _readme_faiss() -> FaissStore | None:
    try:
        return FaissStore.load(config.README_FAISS_PATH)
    except FileNotFoundError:
        print("[retrieval] README FAISS index not found — run build_indexes.py first")
        return None


@lru_cache(maxsize=1)
def _code_bm25() -> BM25Store | None:
    try:
        return BM25Store.load(config.BM25_CODE_PATH)
    except FileNotFoundError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid re-rank (code only)
# ─────────────────────────────────────────────────────────────────────────────

def _hybrid_rerank(
    query: str,
    faiss_results: list[tuple[dict, float]],
    bm25: BM25Store | None,
    top_k: int = config.TOP_K_FINAL,
    alpha: float = 0.6,   # weight for dense score (0.6 dense, 0.4 bm25)
) -> list[dict[str, Any]]:
    """
    Combine dense (FAISS) and sparse (BM25) scores with a linear interpolation.

    alpha=1.0 → pure dense  |  alpha=0.0 → pure BM25
    """
    if not faiss_results:
        return []

    if bm25 is None:
        # No BM25 available — return FAISS order
        return [chunk for chunk, _ in faiss_results[:top_k]]

    # Build a mapping from chunk id → dense score (already 0..1 from cosine)
    dense_map: dict[str, float] = {}
    chunks_by_id: dict[str, dict] = {}
    for chunk, score in faiss_results:
        cid = chunk["id"]
        dense_map[cid] = score
        chunks_by_id[cid] = chunk

    # Get BM25 scores for the same candidates via index lookup
    # We map chunk IDs → BM25 internal indices
    bm25_chunks = bm25._chunks  # type: ignore[attr-defined]
    id_to_bm25_idx = {c["id"]: i for i, c in enumerate(bm25_chunks)}

    candidate_bm25_indices = [
        id_to_bm25_idx[cid]
        for cid in dense_map
        if cid in id_to_bm25_idx
    ]

    bm25_results = bm25.search(
        query,
        top_k=len(candidate_bm25_indices) + 1,
        candidate_indices=candidate_bm25_indices,
    )

    # Normalise BM25 scores to [0, 1] within this candidate set
    bm25_map: dict[str, float] = {}
    if bm25_results:
        max_bm25 = max(s for _, s in bm25_results) or 1.0
        for chunk, score in bm25_results:
            bm25_map[chunk["id"]] = score / max_bm25

    # Normalise dense scores too (they're already cosine ≈ 0..1 but let's be safe)
    max_dense = max(dense_map.values()) or 1.0
    norm_dense = {cid: s / max_dense for cid, s in dense_map.items()}

    # Combine
    combined: list[tuple[str, float]] = []
    for cid in dense_map:
        d = norm_dense.get(cid, 0.0)
        b = bm25_map.get(cid, 0.0)
        combined.append((cid, alpha * d + (1 - alpha) * b))

    combined.sort(key=lambda x: x[1], reverse=True)

    return [chunks_by_id[cid] for cid, _ in combined[:top_k] if cid in chunks_by_id]


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval nodes
# ─────────────────────────────────────────────────────────────────────────────

def retrieve_code(state: AgentState) -> dict:
    """LangGraph node: dense+BM25 hybrid retrieval on code index."""
    if "code" not in state.get("routed_types", []):
        return {"code_chunks": []}

    store = _code_faiss()
    if store is None:
        return {"code_chunks": []}

    embedder = Embedder.get()
    q_vec = embedder.encode_query(state["query"])

    faiss_results = store.search(
        q_vec,
        top_k=config.TOP_K_DENSE,
        repo_filter=state.get("routed_repos") or None,
    )

    bm25 = _code_bm25()
    chunks = _hybrid_rerank(state["query"], faiss_results, bm25, top_k=config.TOP_K_FINAL)

    print(f"[retrieve_code] {len(chunks)} chunks returned")
    return {"code_chunks": chunks}


def retrieve_commits(state: AgentState) -> dict:
    """LangGraph node: dense retrieval on commit index."""
    if "commits" not in state.get("routed_types", []):
        return {"commit_chunks": []}

    store = _commit_faiss()
    if store is None:
        return {"commit_chunks": []}

    embedder = Embedder.get()
    q_vec = embedder.encode_query(state["query"])

    faiss_results = store.search(
        q_vec,
        top_k=config.TOP_K_FINAL,
        repo_filter=state.get("routed_repos") or None,
    )

    chunks = [c for c, _ in faiss_results]
    print(f"[retrieve_commits] {len(chunks)} chunks returned")
    return {"commit_chunks": chunks}


def retrieve_readme(state: AgentState) -> dict:
    """LangGraph node: dense retrieval on readme/docs index."""
    if "readme" not in state.get("routed_types", []):
        return {"readme_chunks": []}

    store = _readme_faiss()
    if store is None:
        return {"readme_chunks": []}

    embedder = Embedder.get()
    q_vec = embedder.encode_query(state["query"])

    faiss_results = store.search(
        q_vec,
        top_k=config.TOP_K_FINAL,
        repo_filter=state.get("routed_repos") or None,
    )

    chunks = [c for c, _ in faiss_results]
    print(f"[retrieve_readme] {len(chunks)} chunks returned")
    return {"readme_chunks": chunks}
