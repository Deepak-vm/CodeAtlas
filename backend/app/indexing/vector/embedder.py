"""
backend/app/indexing/vector/embedder.py

Wrapper around the Jina Embeddings API (remote) OR the local
jinaai/jina-embeddings-v2-base-code model (for local dev/indexing).

Controlled by settings.use_jina_api:
  - True  → calls https://api.jina.ai/v1/embeddings (no torch needed)
  - False → loads the model locally via sentence-transformers

Migrated from: indexing/embedder.py
"""

from __future__ import annotations

import time
import numpy as np
from tqdm import tqdm

from backend.app.core.config import settings

JINA_API_URL = "https://api.jina.ai/v1/embeddings"
JINA_API_BATCH_SIZE = 64
JINA_RETRY_MAX = 5
JINA_RETRY_DELAY = 2.0
JINA_INTER_BATCH_DELAY = 1.0   # seconds between batches — avoids 429 rate limits


class Embedder:
    """
    Singleton-friendly wrapper. Load once, use many times.

    In API mode: stateless — each call hits the Jina REST API.
    In local mode: model is loaded lazily on first call.
    """

    _instance: "Embedder | None" = None

    def __init__(self) -> None:
        self._model = None

    @classmethod
    def get(cls) -> "Embedder":
        """Return a module-level singleton Embedder (lazy init)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def _use_api(self) -> bool:
        return settings.use_jina_api

    def _load_local(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        print(f"Loading local embedding model: {settings.embedding_model}")
        print("(First run may download ~550 MB — cached after first load)")
        self._model = SentenceTransformer(settings.embedding_model, trust_remote_code=True)
        self._model.max_seq_length = settings.embedding_max_seq_len
        print(f"✓ Local model loaded | dim={settings.embedding_dim}")

    def _encode_local(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        self._load_local()
        all_vecs: list[np.ndarray] = []
        iterator = range(0, len(texts), settings.embedding_batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Embedding (local)", unit="batch")  # type: ignore

        for i in iterator:
            batch = texts[i : i + settings.embedding_batch_size]
            vecs = self._model.encode(  # type: ignore[union-attr]
                batch,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            all_vecs.append(vecs.astype(np.float32))

        return np.vstack(all_vecs)

    def _encode_api(self, texts: list[str], show_progress: bool = True) -> np.ndarray:
        import requests

        if not settings.jina_api_key:
            raise ValueError(
                "JINA_API_KEY is not set. Get a free key at https://jina.ai"
            )

        headers = {
            "Authorization": f"Bearer {settings.jina_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        all_vecs: list[np.ndarray] = []
        batch_range = range(0, len(texts), JINA_API_BATCH_SIZE)
        if show_progress:
            batch_range = tqdm(batch_range, desc="Embedding (Jina API)", unit="batch")  # type: ignore

        for i in batch_range:
            batch = texts[i : i + JINA_API_BATCH_SIZE]
            truncated = [t[:settings.embedding_max_seq_len * 4] for t in batch]

            payload = {
                "model": "jina-embeddings-v2-base-code",
                "input": truncated,
                "normalized": True,
            }

            for attempt in range(JINA_RETRY_MAX):
                try:
                    resp = requests.post(JINA_API_URL, headers=headers, json=payload, timeout=60)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except requests.exceptions.RequestException as e:
                    if attempt < JINA_RETRY_MAX - 1:
                        # 429 = rate limit: wait much longer with exponential backoff
                        is_rate_limit = (
                            hasattr(e, "response")
                            and e.response is not None
                            and e.response.status_code == 429
                        )
                        wait = (30 * (2 ** attempt)) if is_rate_limit else (JINA_RETRY_DELAY * (attempt + 1))
                        print(f"[embedder] Jina API {'rate limited' if is_rate_limit else 'error'} "
                              f"(attempt {attempt+1}/{JINA_RETRY_MAX}): {e} — waiting {wait:.0f}s")
                        time.sleep(wait)
                    else:
                        raise RuntimeError(f"Jina API failed after {JINA_RETRY_MAX} attempts: {e}") from e

            embeddings = sorted(data["data"], key=lambda x: x["index"])
            batch_vecs = np.array(
                [item["embedding"] for item in embeddings],
                dtype=np.float32,
            )
            all_vecs.append(batch_vecs)
            # Small inter-batch pause to stay under Jina's rate limit
            if i + JINA_API_BATCH_SIZE < len(texts):
                time.sleep(JINA_INTER_BATCH_DELAY)

        return np.vstack(all_vecs)

    def encode_documents(
        self,
        texts: list[str],
        show_progress: bool = True,
    ) -> np.ndarray:
        """Encode a list of document texts into L2-normalized float32 vectors."""
        if not texts:
            return np.empty((0, settings.embedding_dim), dtype=np.float32)
        if self._use_api:
            return self._encode_api(texts, show_progress=show_progress)
        else:
            return self._encode_local(texts, show_progress=show_progress)

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a single query string. Returns shape (embedding_dim,)."""
        vecs = self.encode_documents([query], show_progress=False)
        return vecs[0]

    @property
    def dim(self) -> int:
        return settings.embedding_dim
