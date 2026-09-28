"""
backend/app/indexing/pipeline.py

Indexing pipeline — transforms JSONL chunks into searchable FAISS + BM25 indexes.

This is the "build infrastructure" step:
  chunks (JSONL) → embeddings → FAISS indexes + BM25 indexes

Separation from retrieval:
  - Indexing BUILDS the search infrastructure
  - Retrieval USES it at query time

CLI wrapper: backend/scripts/index.py
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.indexing.vector.embedder import Embedder
from backend.app.indexing.vector.faiss import FaissStore
from backend.app.indexing.keyword.bm25 import BM25Store

logger = get_logger(__name__)


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL chunk file and return list of chunk dicts."""
    if not path.exists():
        logger.warning("jsonl_not_found", extra={"path": str(path)})
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_index(
    chunks: list[dict],
    embedder: Embedder,
    faiss_path: Path,
    bm25_path: Path | None = None,
    label: str = "",
) -> None:
    """Embed chunks and write a FAISS index (+ optional BM25 index) to disk."""
    if not chunks:
        logger.warning("no_chunks_skip_index", extra={"label": label})
        return

    logger.info("building_index", extra={"label": label, "chunks": len(chunks)})

    texts = [c["content"] for c in chunks]
    vecs = embedder.encode_documents(texts, show_progress=True)

    store = FaissStore(dim=embedder.dim)
    store.add(vecs, chunks)
    store.save(faiss_path)

    if bm25_path is not None:
        bm25 = BM25Store(chunks)
        bm25.save(bm25_path)

    logger.info("index_built", extra={"label": label, "path": str(faiss_path)})


def build_all_indexes(
    chunks_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, int]:
    """
    Read all JSONL chunk files and build FAISS + BM25 indexes.

    Returns dict with chunk counts per type.
    """
    if chunks_dir is None:
        chunks_dir = settings.chunks_dir
    if output_dir is None:
        output_dir = settings.indexes_dir

    # Ensure output subdirectories exist
    faiss_dir = output_dir / "faiss"
    bm25_dir = output_dir / "bm25"
    faiss_dir.mkdir(parents=True, exist_ok=True)
    bm25_dir.mkdir(parents=True, exist_ok=True)

    embedder = Embedder.get()

    code_chunks = read_jsonl(chunks_dir / "code_chunks.jsonl")
    commit_chunks = read_jsonl(chunks_dir / "commit_chunks.jsonl")
    readme_chunks = read_jsonl(chunks_dir / "readme_chunks.jsonl")

    build_index(
        code_chunks, embedder,
        faiss_path=faiss_dir / "code.faiss",
        bm25_path=bm25_dir / "bm25_code.pkl",
        label="code",
    )
    build_index(
        commit_chunks, embedder,
        faiss_path=faiss_dir / "commits.faiss",
        label="commits",
    )
    build_index(
        readme_chunks, embedder,
        faiss_path=faiss_dir / "readme.faiss",
        label="readme",
    )

    return {
        "code": len(code_chunks),
        "commits": len(commit_chunks),
        "readme": len(readme_chunks),
    }
