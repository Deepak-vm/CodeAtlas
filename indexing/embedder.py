"""
indexing/embedder.py

Wrapper around jinaai/jina-embeddings-v2-base-code.

Key facts about this model:
  - 768-dimensional output
  - Up to 8192 token context (we cap at 4096 to save RAM)
  - Requires trust_remote_code=True (custom JinaBERT architecture)
  - Supports queries vs documents via encode() with and without prompt prefix

Usage:
  embedder = Embedder()
  vecs = embedder.encode_documents(["def foo(): ...", "class Bar: ..."])
  q_vec = embedder.encode_query("where is my retry logic?")
"""

from __future__ import annotations

import numpy as np
from tqdm import tqdm

from config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MAX_SEQ_LEN,
    EMBEDDING_MODEL,
)


class Embedder:
    """
    Singleton-friendly wrapper. Load once, use many times.
    The model is loaded lazily on first call to save startup time.
    """

    _instance: "Embedder | None" = None

    def __init__(self) -> None:
        self._model = None

    # ── Singleton access ───────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "Embedder":
        """Return a module-level singleton Embedder (lazy init)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Model loading ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        print(f"Loading embedding model: {EMBEDDING_MODEL}")
        print("(First run may download ~550 MB — cached after first load)")
        self._model = SentenceTransformer(
            EMBEDDING_MODEL,
            trust_remote_code=True,
        )
        self._model.max_seq_length = EMBEDDING_MAX_SEQ_LEN
        print(f"✓ Model loaded | dim={EMBEDDING_DIM} | max_seq={EMBEDDING_MAX_SEQ_LEN}")

    # ── Encoding ───────────────────────────────────────────────────────────

    def encode_documents(
        self,
        texts: list[str],
        show_progress: bool = True,
    ) -> np.ndarray:
        """
        Encode a list of document texts into L2-normalized float32 vectors.
        Returns shape (N, EMBEDDING_DIM).
        """
        self._load()
        all_vecs: list[np.ndarray] = []
        iterator = range(0, len(texts), EMBEDDING_BATCH_SIZE)
        if show_progress:
            iterator = tqdm(iterator, desc="Embedding", unit="batch")  # type: ignore[assignment]

        for i in iterator:
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            vecs = self._model.encode(  # type: ignore[union-attr]
                batch,
                normalize_embeddings=True,    # L2-normalize → cosine sim = inner product
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            all_vecs.append(vecs.astype(np.float32))

        return np.vstack(all_vecs)

    def encode_query(self, query: str) -> np.ndarray:
        """
        Encode a single query string.
        Jina v2 code model uses the same encoding for queries and documents
        (symmetric retrieval), so no special prompt prefix needed.
        Returns shape (EMBEDDING_DIM,).
        """
        self._load()
        vec = self._model.encode(  # type: ignore[union-attr]
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vec[0].astype(np.float32)

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM

