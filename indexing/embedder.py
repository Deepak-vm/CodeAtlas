"""
indexing/embedder.py

Wrapper around the Jina Embeddings API (remote, free tier) OR the local
jinaai/jina-embeddings-v2-base-code model (for local dev/indexing).

Controlled by config.USE_JINA_API:
  - True  → calls https://api.jina.ai/v1/embeddings (no torch/transformers needed)
  - False → loads the model locally via sentence-transformers (original behaviour)

API docs: https://jina.ai/embeddings/

Usage:
  embedder = Embedder()
  vecs = embedder.encode_documents(["def foo(): ...", "class Bar: ..."])
  q_vec = embedder.encode_query("where is my retry logic?")
"""

from __future__ import annotations

import time
import numpy as np
from tqdm import tqdm

from config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MAX_SEQ_LEN,
    EMBEDDING_MODEL,
    JINA_API_KEY,
    USE_JINA_API,
)

# Jina API constants
JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_API_BATCH_SIZE = 64          # Jina allows up to 2048 inputs per request; 64 is safe
JINA_RETRY_MAX = 3
JINA_RETRY_DELAY = 2.0            # seconds between retries


class Embedder:
    """
    Singleton-friendly wrapper. Load once, use many times.

    In API mode: stateless — each call hits the Jina REST API.
    In local mode: model is loaded lazily on first call to save startup time.
    """

    _instance: "Embedder | None" = None

    def __init__(self) -> None:
        self._model = None          # only used in local mode

    # ── Singleton access ───────────────────────────────────────────────────

    @classmethod
    def get(cls) -> "Embedder":
        """Return a module-level singleton Embedder (lazy init)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Mode detection ─────────────────────────────────────────────────────

    @property
    def _use_api(self) -> bool:
        return USE_JINA_API

    # ── Local model (fallback for local dev / indexing) ────────────────────

    def _load_local(self) -> None:
        """Lazy-load local sentence-transformers model (only if USE_JINA_API=False)."""
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        print(f"Loading local embedding model: {EMBEDDING_MODEL}")
        print("(First run may download ~550 MB — cached after first load)")
        self._model = SentenceTransformer(
            EMBEDDING_MODEL,
            trust_remote_code=True,
        )
        self._model.max_seq_length = EMBEDDING_MAX_SEQ_LEN
        print(f"✓ Local model loaded | dim={EMBEDDING_DIM} | max_seq={EMBEDDING_MAX_SEQ_LEN}")

    def _encode_local(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        self._load_local()
        all_vecs: list[np.ndarray] = []
        iterator = range(0, len(texts), EMBEDDING_BATCH_SIZE)
        if show_progress:
            iterator = tqdm(iterator, desc="Embedding (local)", unit="batch")  # type: ignore[assignment]

        for i in iterator:
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            vecs = self._model.encode(  # type: ignore[union-attr]
                batch,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            all_vecs.append(vecs.astype(np.float32))

        return np.vstack(all_vecs)

    # ── Jina API (production / deploy mode) ───────────────────────────────

    def _encode_api(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        """
        Call the Jina Embeddings v1 API in batches.
        Returns L2-normalized float32 array of shape (N, EMBEDDING_DIM).
        """
        import requests

        if not JINA_API_KEY:
            raise ValueError(
                "JINA_API_KEY is not set. "
                "Get a free key at https://jina.ai and add it to .env"
            )

        headers = {
            "Authorization": f"Bearer {JINA_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        all_vecs: list[np.ndarray] = []
        batch_range = range(0, len(texts), JINA_API_BATCH_SIZE)
        if show_progress:
            batch_range = tqdm(batch_range, desc="Embedding (Jina API)", unit="batch")  # type: ignore[assignment]

        for i in batch_range:
            batch = texts[i : i + JINA_API_BATCH_SIZE]

            # Truncate each text to keep within token limits
            truncated = [t[:EMBEDDING_MAX_SEQ_LEN * 4] for t in batch]  # ~4 chars/token

            payload = {
                "model": "jina-embeddings-v2-base-code",
                "input": truncated,
                "normalized": True,   # API-side L2 normalization
            }

            for attempt in range(JINA_RETRY_MAX):
                try:
                    resp = requests.post(JINA_API_URL, headers=headers, json=payload, timeout=60)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except requests.exceptions.RequestException as e:
                    if attempt < JINA_RETRY_MAX - 1:
                        print(f"[embedder] Jina API error (attempt {attempt+1}): {e} — retrying in {JINA_RETRY_DELAY}s")
                        time.sleep(JINA_RETRY_DELAY)
                    else:
                        raise RuntimeError(f"Jina API failed after {JINA_RETRY_MAX} attempts: {e}") from e

            # Extract embeddings in order
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            batch_vecs = np.array(
                [item["embedding"] for item in embeddings],
                dtype=np.float32,
            )
            all_vecs.append(batch_vecs)

        return np.vstack(all_vecs)

    # ── Public interface (same for both modes) ────────────────────────────

    def encode_documents(
        self,
        texts: list[str],
        show_progress: bool = True,
    ) -> np.ndarray:
        """
        Encode a list of document texts into L2-normalized float32 vectors.
        Returns shape (N, EMBEDDING_DIM).
        """
        if not texts:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

        if self._use_api:
            return self._encode_api(texts, show_progress=show_progress)
        else:
            return self._encode_local(texts, show_progress=show_progress)

    def encode_query(self, query: str) -> np.ndarray:
        """
        Encode a single query string.
        Jina v2 code model uses symmetric retrieval (same encoding for query and docs).
        Returns shape (EMBEDDING_DIM,).
        """
        vecs = self.encode_documents([query], show_progress=False)
        return vecs[0]

    @property
    def dim(self) -> int:
        return EMBEDDING_DIM
