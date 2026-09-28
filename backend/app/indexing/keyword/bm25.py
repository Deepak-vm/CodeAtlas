"""
backend/app/indexing/keyword/bm25.py

BM25 index on code chunk content + symbol names.
Used for the hybrid signal: dense FAISS candidates are re-ranked with BM25
on symbol/function names to surface exact-match results that embeddings
might rank lower.

Migrated from: indexing/bm25_store.py
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

from backend.app.core.config import settings


def _tokenize(text: str) -> list[str]:
    """
    Simple tokenizer: lowercase, split on non-alphanumeric, remove empty tokens.
    Treats camelCase / snake_case as separate tokens for better symbol matching.
    """
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    tokens = re.split(r"[^a-z0-9_]+", text.lower())
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
        corpus: list[list[str]] = []
        for c in chunks:
            doc_text = c.get("content", "")
            symbol = c.get("symbol_name") or ""
            tokens = _tokenize(symbol) * 3 + _tokenize(doc_text)
            corpus.append(tokens)

        self._bm25 = BM25Okapi(corpus)

    def search(
        self,
        query: str,
        top_k: int | None = None,
        repo_filter: list[str] | None = None,
        candidate_indices: list[int] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        if top_k is None:
            top_k = settings.top_k_dense
        if self._bm25 is None:
            return []

        q_tokens = _tokenize(query)
        if not q_tokens:
            return []

        if candidate_indices is not None:
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

    @classmethod
    def remove_repo_and_save(cls, path: Path, repo_name: str) -> int:
        path = Path(path)
        if not path.exists():
            return 0
        store = cls.load(path)
        original_count = len(store._chunks)
        kept_chunks = [c for c in store._chunks if c.get("repo", "").lower() != repo_name.lower()]
        removed_count = original_count - len(kept_chunks)
        if removed_count == 0:
            return 0
        new_store = cls(kept_chunks)
        new_store.save(path)
        return removed_count
