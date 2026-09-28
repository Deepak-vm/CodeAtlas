"""
backend/app/indexing/vector/faiss.py

Thin FAISS wrapper that stores vectors alongside their chunk metadata.

Design:
  - IndexFlatIP (inner product) — works as cosine similarity because
    our embedder L2-normalizes all vectors before storing.
  - Metadata (the full chunk dict list) is kept in a parallel Python list
    and pickled alongside the FAISS index.
  - search() returns (chunk, score) pairs ranked highest-first.

Migrated from: indexing/faiss_store.py
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from backend.app.core.config import settings


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

    def __init__(self, dim: int | None = None) -> None:
        if dim is None:
            dim = settings.embedding_dim
        self.dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._chunks: list[dict[str, Any]] = []

    def add(self, vectors: np.ndarray, chunks: list[dict[str, Any]]) -> None:
        if len(vectors) != len(chunks):
            raise ValueError(f"vectors ({len(vectors)}) and chunks ({len(chunks)}) length mismatch")
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = vectors[np.newaxis, :]
        self._index.add(vectors)
        self._chunks.extend(chunks)

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int | None = None,
        repo_filter: list[str] | None = None,
    ) -> list[tuple[dict[str, Any], float]]:
        if top_k is None:
            top_k = settings.top_k_dense
        query_vec = np.asarray(query_vec, dtype=np.float32)
        if query_vec.ndim == 1:
            query_vec = query_vec[np.newaxis, :]

        n_total = self._index.ntotal
        if n_total == 0:
            return []

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

    def save(self, index_path: Path) -> None:
        index_path = Path(index_path)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_path))
        with open(str(index_path) + ".meta", "wb") as f:
            pickle.dump(self._chunks, f)
        print(f"  ✓ Saved {self._index.ntotal} vectors → {index_path}")

    @classmethod
    def load(cls, index_path: Path) -> "FaissStore":
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

    @property
    def size(self) -> int:
        return self._index.ntotal

    def repos(self) -> list[str]:
        return sorted({c.get("repo", "") for c in self._chunks})

    @classmethod
    def remove_repo_and_save(cls, index_path: Path, repo_name: str) -> int:
        """
        Load an existing FAISS index, remove all vectors for repo_name,
        and save back in-place. NO re-embedding needed.
        Returns number of vectors removed.
        """
        index_path = Path(index_path)
        if not index_path.exists():
            return 0
        meta_path = Path(str(index_path) + ".meta")
        if not meta_path.exists():
            return 0

        store = cls.load(index_path)
        original_count = store._index.ntotal

        keep_indices = [
            i for i, chunk in enumerate(store._chunks)
            if chunk.get("repo", "").lower() != repo_name.lower()
        ]
        removed_count = original_count - len(keep_indices)

        if removed_count == 0:
            print(f"  ℹ No vectors found for repo '{repo_name}' in {index_path.name}")
            return 0

        if len(keep_indices) == 0:
            new_store = cls(dim=store.dim)
            new_store.save(index_path)
            return removed_count

        kept_chunks = [store._chunks[i] for i in keep_indices]
        kept_vectors = np.array([
            store._index.reconstruct(i) for i in keep_indices
        ], dtype=np.float32)

        new_store = cls(dim=store.dim)
        new_store.add(kept_vectors, kept_chunks)
        new_store.save(index_path)

        print(f"  ✓ Removed {removed_count} vectors for '{repo_name}' → {len(keep_indices)} remaining")
        return removed_count
