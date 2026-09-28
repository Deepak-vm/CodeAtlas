"""
backend/app/retrieval/pipeline.py

RetrievalPipeline — the single point of entry for all retrieval operations.

Retrieval USES the indexes built by backend/app/indexing/pipeline.py.
It does not know how the indexes were built, only how to query them.

Architecture:
  RetrievalPipeline
    ├── code index  : FaissStore (faiss/code.faiss) + BM25Store (bm25/bm25_code.pkl)
    ├── commit index: FaissStore (faiss/commits.faiss)
    └── readme index: FaissStore (faiss/readme.faiss)

  search_code()    → FAISS dense candidates → BM25 hybrid rerank → top-K chunks
  search_commits() → FAISS dense → top-K chunks
  search_readme()  → FAISS dense → top-K chunks
"""

from __future__ import annotations

from typing import Any

from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger(__name__)


class RetrievalPipeline:
    """High-level retrieval interface used by agent nodes."""

    def __init__(
        self,
        code_faiss=None,
        commit_faiss=None,
        readme_faiss=None,
        code_bm25=None,
        embedder=None,
    ) -> None:
        self._code_faiss = code_faiss
        self._commit_faiss = commit_faiss
        self._readme_faiss = readme_faiss
        self._code_bm25 = code_bm25
        self._embedder = embedder

    @classmethod
    def load(cls) -> "RetrievalPipeline":
        """Load all available indexes from disk. Missing indexes are skipped gracefully."""
        from backend.app.indexing.vector.embedder import Embedder
        from backend.app.indexing.vector.faiss import FaissStore
        from backend.app.indexing.keyword.bm25 import BM25Store

        embedder = Embedder.get()

        def _try_load_faiss(path):
            try:
                store = FaissStore.load(path)
                logger.info("index_loaded", extra={"path": str(path), "size": store.size})
                return store
            except FileNotFoundError:
                logger.warning("index_missing", extra={"path": str(path)})
                return None

        def _try_load_bm25(path):
            try:
                store = BM25Store.load(path)
                logger.info("bm25_loaded", extra={"path": str(path)})
                return store
            except FileNotFoundError:
                logger.warning("bm25_missing", extra={"path": str(path)})
                return None

        return cls(
            code_faiss=_try_load_faiss(settings.code_faiss_path),
            commit_faiss=_try_load_faiss(settings.commit_faiss_path),
            readme_faiss=_try_load_faiss(settings.readme_faiss_path),
            code_bm25=_try_load_bm25(settings.bm25_code_path),
            embedder=embedder,
        )

    @property
    def has_code_index(self) -> bool:
        return self._code_faiss is not None

    @property
    def has_commit_index(self) -> bool:
        return self._commit_faiss is not None

    @property
    def has_readme_index(self) -> bool:
        return self._readme_faiss is not None

    @property
    def index_status(self) -> dict[str, bool]:
        return {
            "code": self.has_code_index,
            "commits": self.has_commit_index,
            "readme": self.has_readme_index,
            "bm25_code": self._code_bm25 is not None,
        }

    def search_code(
        self,
        query: str,
        repo_filter: list[str] | None = None,
        top_k_dense: int = 10,
        top_k_final: int = 5,
    ) -> list[dict[str, Any]]:
        if self._code_faiss is None:
            return []
        q_vec = self._embedder.encode_query(query)
        faiss_results = self._code_faiss.search(q_vec, top_k=top_k_dense, repo_filter=repo_filter)
        return self._hybrid_rerank(query, faiss_results, self._code_bm25, top_k=top_k_final)

    def search_commits(
        self,
        query: str,
        repo_filter: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if self._commit_faiss is None:
            return []
        q_vec = self._embedder.encode_query(query)
        faiss_results = self._commit_faiss.search(q_vec, top_k=top_k, repo_filter=repo_filter)
        return [chunk for chunk, _ in faiss_results]

    def search_readme(
        self,
        query: str,
        repo_filter: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if self._readme_faiss is None:
            return []
        q_vec = self._embedder.encode_query(query)
        faiss_results = self._readme_faiss.search(q_vec, top_k=top_k, repo_filter=repo_filter)
        return [chunk for chunk, _ in faiss_results]

    @staticmethod
    def _hybrid_rerank(
        query: str,
        faiss_results: list[tuple[dict, float]],
        bm25=None,
        top_k: int = 5,
        alpha: float = 0.6,
    ) -> list[dict[str, Any]]:
        if not faiss_results:
            return []
        if bm25 is None:
            return [chunk for chunk, _ in faiss_results[:top_k]]

        dense_map: dict[str, float] = {}
        chunks_by_id: dict[str, dict] = {}
        for chunk, score in faiss_results:
            cid = chunk["id"]
            dense_map[cid] = score
            chunks_by_id[cid] = chunk

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

        bm25_map: dict[str, float] = {}
        if bm25_results:
            max_bm25 = max(s for _, s in bm25_results) or 1.0
            for chunk, score in bm25_results:
                bm25_map[chunk["id"]] = score / max_bm25

        max_dense = max(dense_map.values()) or 1.0
        norm_dense = {cid: s / max_dense for cid, s in dense_map.items()}

        combined: list[tuple[str, float]] = []
        for cid in dense_map:
            d = norm_dense.get(cid, 0.0)
            b = bm25_map.get(cid, 0.0)
            combined.append((cid, alpha * d + (1 - alpha) * b))

        combined.sort(key=lambda x: x[1], reverse=True)
        return [chunks_by_id[cid] for cid, _ in combined[:top_k] if cid in chunks_by_id]
