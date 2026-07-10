"""
indexing/bm25_store.py

BM25 index on code chunk content + symbol names.
Used for the hybrid signal: dense FAISS candidates are re-ranked with BM25
on symbol/function names to surface exact-match results that embeddings
might rank lower.

Connects to the BM25 work from the SOTA Web Crawler project.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from config import TOP_K_DENSE


def _tokenize(text: str) -> list[str]:
    """
    Simple tokenizer: lowercase, split on non-alphanumeric, remove empty tokens.
    Treats camelCase / snake_case as separate tokens for better symbol matching.
    """
    # Insert space before uppercase letters in camelCase
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    # Split on anything that's not alphanumeric or underscore
    tokens = re.split(r"[^a-z0-9_]+", text.lower())
    # Further split on underscores (snake_case)
    expanded: list[str] = []
    for t in tokens:
        expanded.extend(p for p in t.split("_") if p)
    return [t for t in expanded if len(t) > 1]


class BM25Store:
    """
    Build, query, save, and load a BM25 index over code chunks.

    Usage:
        store = BM25Store(chunks)  # build
        store.save(path)

        store2 = BM25Store.load(path)
        results = store2.search("websocket retry logic", top_k=10)
    """

    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        from rank_bm25 import BM25Okapi

        self._chunks: list[dict] = []
        self._bm25: BM25Okapi | None = None

        if chunks:
            self._build(chunks)

    def _build(self, chunks: list[dict]) -> None:
        from rank_bm25 import BM25Okapi

        self._chunks = chunks
        # Corpus: bias toward symbol names (they're compact and highly discriminative)
        corpus: list[list[str]] = []
        for c in chunks:
            doc_text = c.get("content", "")
            symbol = c.get("symbol_name") or ""
            # Repeat symbol tokens 3× to upweight them in BM25
            tokens = _tokenize(symbol) * 3 + _tokenize(doc_text)
            corpus.append(tokens)

        self._bm25 = BM25Okapi(corpus)

    def search(
        self,
        query: str,
        top_k: int = TOP_K_DENSE,
        repo_filter: list[str] | None = None,
        candidate_indices: list[int] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Return top_k (chunk, bm25_score) pairs.

        Parameters
        ----------
        query             : natural language query
        top_k             : number to return
        repo_filter       : optional whitelist of repo names
        candidate_indices : if provided, only score these indices (used for re-ranking
                            FAISS candidates rather than the full corpus)
        """
        if self._bm25 is None:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        if candidate_indices is not None:
            # Score only the subset
            scores_raw = self._bm25.get_scores(q_tokens)
            scored = [(i, scores_raw[i]) for i in candidate_indices]
        else:
            scores_raw = self._bm25.get_scores(q_tokens)
            scored = list(enumerate(scores_raw))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[tuple[dict, float]] = []
        for idx, score in scored:
            chunk = self._chunks[idx]
            if repo_filter and chunk.get("repo") not in repo_filter:
                continue
            results.append((chunk, float(score)))
            if len(results) >= top_k:
                break

        return results

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({"chunks": self._chunks, "bm25": self._bm25}, f)
        print(f"  ✓ Saved BM25 index ({len(self._chunks)} docs) → {path}")

    @classmethod
    def load(cls, path: Path) -> "BM25Store":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"BM25 index not found: {path}")
        store = cls.__new__(cls)
        with open(path, "rb") as f:
            data = pickle.load(f)
        store._chunks = data["chunks"]
        store._bm25 = data["bm25"]
        print(f"  ✓ Loaded BM25 index ({len(store._chunks)} docs) from {path}")
        return store

    # ── Partial Deletion ───────────────────────────────────────────────────

    @classmethod
    def remove_repo_and_save(cls, path: Path, repo_name: str) -> int:
        """
        Load existing BM25 index, remove all entries for repo_name,
        rebuild BM25 from remaining chunks, and save back in-place.
        NO re-embedding needed (BM25 is bag-of-words, just re-tokenizes remaining docs).

        Returns: number of chunks removed.
        """
        path = Path(path)
        if not path.exists():
            return 0

        store = cls.load(path)
        original_count = len(store._chunks)
        kept_chunks = [c for c in store._chunks if c.get("repo", "").lower() != repo_name.lower()]
        removed_count = original_count - len(kept_chunks)

        if removed_count == 0:
            print(f"  ℹ No BM25 entries found for repo '{repo_name}' in {path.name}")
            return 0

        new_store = cls(kept_chunks)
        new_store.save(path)
        print(f"  ✓ Removed {removed_count} BM25 entries for '{repo_name}' from {path.name} → {len(kept_chunks)} remaining")
        return removed_count
