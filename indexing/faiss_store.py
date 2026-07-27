"""
indexing/faiss_store.py

Thin FAISS wrapper that stores vectors alongside their chunk metadata.

Design:
  - IndexFlatIP (inner product) — works as cosine similarity because
    our embedder L2-normalizes all vectors before storing.
  - Metadata (the full chunk dict list) is kept in a parallel Python list
    and pickled alongside the FAISS index.
  - search() returns (chunk, score) pairs ranked highest-first.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from config import EMBEDDING_DIM, TOP_K_DENSE


class FaissStore:
    """
    Build, query, save, and load a FAISS flat index + metadata store.

    Usage:
        store = FaissStore()
        store.add(vectors, chunks)
        store.save(path)

        store2 = FaissStore.load(path)
        results = store2.search(query_vec, top_k=5)
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)   # inner product = cosine (if L2-normed)
        self._chunks: list[dict[str, Any]] = []

    # ── Building ───────────────────────────────────────────────────────────

    def add(self, vectors: np.ndarray, chunks: list[dict[str, Any]]) -> None:
        """
        Add embeddings + their corresponding chunk dicts to the store.

        Parameters
        ----------
        vectors : float32 array of shape (N, dim), must be L2-normalized
        chunks  : list of N chunk dicts (same order as vectors)
        """
        if len(vectors) != len(chunks):
            raise ValueError(f"vectors ({len(vectors)}) and chunks ({len(chunks)}) length mismatch")

        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors[np.newaxis, :]

        self._index.add(vectors)
        self._chunks.extend(chunks)

    # ── Querying ───────────────────────────────────────────────────────────

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = TOP_K_DENSE,
        repo_filter: list[str] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        """
        Return top_k (chunk, score) pairs.

        Parameters
        ----------
        query_vec   : float32 1-D array (EMBEDDING_DIM,), L2-normalized
        top_k       : number of results to return
        repo_filter : if given, only return chunks from these repos;
                      over-fetches by 3× internally to compensate for filter shrinkage
        """
        query_vec = np.asarray(query_vec, dtype=np.float32)
        if query_vec.ndim == 1:
            query_vec = query_vec[np.newaxis, :]

        n_total = self._index.ntotal
        if n_total == 0:
            return []

        # Over-fetch if filtering so we still get top_k after filter
        fetch_k = min(top_k * 3 if repo_filter else top_k, n_total)

        scores, indices = self._index.search(query_vec, fetch_k)
        scores = scores[0]
        indices = indices[0]

        results: list[tuple[dict, float]] = []
        for idx, score in zip(indices, scores):
            if idx == -1:
                continue
            chunk = self._chunks[idx]
            if repo_filter and chunk.get("repo") not in repo_filter:
                continue
            results.append((chunk, float(score)))
            if len(results) >= top_k:
                break

        return results

    # ── Persistence ────────────────────────────────────────────────────────

    def save(self, index_path: Path) -> None:
        """
        Save index to {index_path} (FAISS binary) and
        metadata to {index_path}.meta (pickle).
        """
        index_path = Path(index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_path))
        with open(str(index_path) + ".meta", "wb") as f:
            pickle.dump(self._chunks, f)
        print(f"  ✓ Saved {self._index.ntotal} vectors → {index_path}")

    @classmethod
    def load(cls, index_path: Path) -> "FaissStore":
        """Load a previously saved FaissStore."""
        index_path = Path(index_path)
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {index_path}")

        meta_path = Path(str(index_path) + ".meta")
        if not meta_path.exists():
            raise FileNotFoundError(f"FAISS metadata not found: {meta_path}")

        store = cls.__new__(cls)
        store._index = faiss.read_index(str(index_path))
        store.dim = store._index.d
        with open(meta_path, "rb") as f:
            store._chunks = pickle.load(f)
        print(f"  ✓ Loaded {store._index.ntotal} vectors from {index_path}")
        return store

    # ── Introspection ──────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return self._index.ntotal

    def repos(self) -> list[str]:
        """Return sorted list of unique repo names in this store."""
        return sorted({c.get("repo", "") for c in self._chunks})

    # ── Partial Deletion ───────────────────────────────────────────────────

    @classmethod
    def remove_repo_and_save(cls, index_path: Path, repo_name: str) -> int:
        """
        Load an existing FAISS index, remove all vectors belonging to repo_name,
        and save back in-place — NO re-embedding needed.

        Returns: number of vectors removed.
        """
        index_path = Path(index_path)
        if not index_path.exists():
            return 0

        meta_path = Path(str(index_path) + ".meta")
        if not meta_path.exists():
            return 0

        # Load existing store
        store = cls.load(index_path)
        original_count = store._index.ntotal

        # Find which positions to KEEP
        keep_indices = [
            i for i, chunk in enumerate(store._chunks)
            if chunk.get("repo", "").lower() != repo_name.lower()
        ]
        removed_count = original_count - len(keep_indices)

        if removed_count == 0:
            print(f"  ℹ No vectors found for repo '{repo_name}' in {index_path.name}")
            return 0

        # Edge case: all vectors belonged to this repo → write an empty index
        if len(keep_indices) == 0:
            new_store = cls(dim=store.dim)
            new_store.save(index_path)
            print(f"  ✓ Removed all {removed_count} vectors for '{repo_name}' from {index_path.name} → 0 remaining")
            return removed_count

        # Reconstruct kept vectors directly from IndexFlatIP (no re-embedding)
        kept_chunks = [store._chunks[i] for i in keep_indices]
        kept_vectors = np.array([
            store._index.reconstruct(i)
            for i in keep_indices
        ], dtype=np.float32)

        # Rebuild FAISS index with kept vectors only
        new_store = cls(dim=store.dim)
        new_store.add(kept_vectors, kept_chunks)
        new_store.save(index_path)

        print(f"  ✓ Removed {removed_count} vectors for '{repo_name}' from {index_path.name} → {len(keep_indices)} remaining")
        return removed_count


