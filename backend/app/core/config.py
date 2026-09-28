"""
backend/app/core/config.py

Centralised settings for the Knowledge Base Agent.

All tuneable knobs live here. Values are read from environment variables
(via python-dotenv / Render env vars). No other module should hardcode
paths, model names, or thresholds — import from this module instead.

Usage:
    from backend.app.core.config import settings

    print(settings.groq_model_primary)
    path = settings.code_faiss_path
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """All application configuration, sourced from environment variables."""

    # ── Project root ──────────────────────────────────────────────────────────
    # Points at the repo root (three levels up from this file inside backend/app/core/)
    ROOT_DIR: Path = Path(__file__).parent.parent.parent.parent.resolve()

    # ── Backend root (all Python internals live here) ─────────────────────────
    @property
    def backend_dir(self) -> Path:
        return self.ROOT_DIR / "backend"

    # ── Data directories (inside backend/) ───────────────────────────────────
    @property
    def data_dir(self) -> Path:
        return self.backend_dir / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def chunks_dir(self) -> Path:
        """Processed JSONL chunk files."""
        return self.data_dir / "processed"

    @property
    def indexes_dir(self) -> Path:
        return self.data_dir / "indexes"

    @property
    def faiss_dir(self) -> Path:
        return self.indexes_dir / "faiss"

    @property
    def bm25_dir(self) -> Path:
        return self.indexes_dir / "bm25"

    # ── Repos config ──────────────────────────────────────────────────────────
    @property
    def repos_config_file(self) -> Path:
        return self.raw_dir / "repos.json"

    @property
    def repos_dir(self) -> Path:
        return self.raw_dir / "repos"

    # ── JSONL chunk files ─────────────────────────────────────────────────────
    @property
    def code_chunks_file(self) -> Path:
        return self.chunks_dir / "code_chunks.jsonl"

    @property
    def commit_chunks_file(self) -> Path:
        return self.chunks_dir / "commit_chunks.jsonl"

    @property
    def readme_chunks_file(self) -> Path:
        return self.chunks_dir / "readme_chunks.jsonl"

    # ── FAISS index files ─────────────────────────────────────────────────────
    @property
    def code_faiss_path(self) -> Path:
        return self.faiss_dir / "code.faiss"

    @property
    def commit_faiss_path(self) -> Path:
        return self.faiss_dir / "commits.faiss"

    @property
    def readme_faiss_path(self) -> Path:
        return self.faiss_dir / "readme.faiss"

    @property
    def bm25_code_path(self) -> Path:
        return self.bm25_dir / "bm25_code.pkl"

    # ── Embedding model ───────────────────────────────────────────────────────
    embedding_model: str = "jinaai/jina-embeddings-v2-base-code"
    embedding_dim: int = 768
    embedding_max_seq_len: int = 512
    embedding_batch_size: int = 8

    # ── Jina Embeddings API ───────────────────────────────────────────────────
    @property
    def jina_api_key(self) -> str:
        return os.getenv("JINA_API_KEY", "")

    @property
    def use_jina_api(self) -> bool:
        return os.getenv("USE_JINA_API", "false").lower() == "true"

    # ── LLM (Groq) ────────────────────────────────────────────────────────────
    @property
    def groq_api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    groq_model_primary: str = "openai/gpt-oss-120b"
    groq_model_fast: str = "openai/gpt-oss-20b"
    groq_temperature: float = 0.0
    groq_max_tokens: int = 2048

    # ── Supabase ──────────────────────────────────────────────────────────────
    @property
    def supabase_url(self) -> str:
        return os.getenv("SUPABASE_URL", "")

    @property
    def supabase_service_key(self) -> str:
        return os.getenv("SUPABASE_SERVICE_KEY", "")

    # ── LangSmith ─────────────────────────────────────────────────────────────
    @property
    def langchain_api_key(self) -> str:
        return os.getenv("LANGCHAIN_API_KEY", "")

    @property
    def langchain_project(self) -> str:
        return os.getenv("LANGCHAIN_PROJECT", "Knowledge-Base-Agent")

    # ── Chunking parameters ───────────────────────────────────────────────────
    python_fallback_chunk_lines: int = 50
    python_fallback_overlap_lines: int = 10
    js_fallback_chunk_lines: int = 60
    js_fallback_overlap_lines: int = 10
    max_commit_history: int = 500
    readme_split_by_heading: bool = True

    # ── Files / directories to skip during repo walking ───────────────────────
    skip_dirs: frozenset = frozenset({
        "node_modules", ".git", "__pycache__", "venv", ".venv",
        "env", "dist", "build", ".next", ".nuxt", "coverage",
        ".pytest_cache", ".mypy_cache", "htmlcov", "site-packages",
        "eggs", ".eggs", "migrations", "eval",
    })

    skip_filenames: frozenset = frozenset({"check_all.py"})

    skip_file_extensions: frozenset = frozenset({
        ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
        ".pdf", ".zip", ".tar", ".gz", ".whl",
        ".lock", ".map",
    })

    supported_code_extensions: frozenset = frozenset({
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".go", ".java", ".rs", ".cpp", ".c", ".h",
    })

    # ── Retrieval parameters ──────────────────────────────────────────────────
    top_k_dense: int = 10
    top_k_final: int = 5
    ambiguity_score_delta: float = 0.05
    ambiguity_min_repos: int = 2

    # ── FastAPI ───────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_version: str = "v1"

    @property
    def api_cors_origins(self) -> list[str]:
        frontend_url = os.getenv("FRONTEND_URL", "").rstrip("/")
        origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://code-atlas-snowy.vercel.app",
        ]
        if frontend_url:
            origins.append(frontend_url)
        return origins


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the global Settings singleton (cached after first call)."""
    return Settings()


# Module-level singleton for convenience imports
settings = get_settings()
