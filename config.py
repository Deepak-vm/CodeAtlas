"""
config.py — Central configuration for the Knowledge Base Agent.

All tuneable knobs live here. No other file should hardcode paths, model names,
or thresholds — import from this module instead.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Project root
# ─────────────────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.resolve()

# ─────────────────────────────────────────────────────────────────────────────
# Repos — populated at runtime via CLI / repos.json, NOT hardcoded here.
#
# repos.json example (drop in project root):
# [
#   {"name": "my-backend",      "path": "/home/user/repos/my-backend"},
#   {"name": "my-rag-agent",    "path": "/home/user/repos/my-rag-agent"},
#   {"name": "web-crawler",     "path": "/home/user/repos/web-crawler"}
# ]
#
# OR pass GitHub URLs — the ingester will clone them into REPOS_DIR.
# [
#   {"name": "my-backend", "url": "https://github.com/user/my-backend"}
# ]
# ─────────────────────────────────────────────────────────────────────────────
REPOS_CONFIG_FILE = ROOT_DIR / "repos.json"
REPOS_DIR = ROOT_DIR / "repos"          # where remote repos are cloned into

# ─────────────────────────────────────────────────────────────────────────────
# Data directories
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = ROOT_DIR / "data"
CHUNKS_DIR = DATA_DIR / "chunks"
INDEXES_DIR = DATA_DIR / "indexes"

# JSONL output files
CODE_CHUNKS_FILE = CHUNKS_DIR / "code_chunks.jsonl"
COMMIT_CHUNKS_FILE = CHUNKS_DIR / "commit_chunks.jsonl"
README_CHUNKS_FILE = CHUNKS_DIR / "readme_chunks.jsonl"

# FAISS index files
CODE_FAISS_PATH = INDEXES_DIR / "code.faiss"
COMMIT_FAISS_PATH = INDEXES_DIR / "commits.faiss"
README_FAISS_PATH = INDEXES_DIR / "readme.faiss"

# BM25 index (code only)
BM25_CODE_PATH = INDEXES_DIR / "bm25_code.pkl"

# ─────────────────────────────────────────────────────────────────────────────
# Embedding model
# ─────────────────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"
EMBEDDING_DIM = 768          # jina-v2-base-code output dimension
EMBEDDING_MAX_SEQ_LEN = 512   # Capped at 512 for CPU speed and RAM safety
EMBEDDING_BATCH_SIZE = 8     # Reduced to 8 to prevent Linux OOM killer on 8GB RAM

# ─────────────────────────────────────────────────────────────────────────────
# LLM / API
# ─────────────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL_PRIMARY = "llama-3.3-70b-versatile"   # router + synthesizer
GROQ_MODEL_FAST = "llama-3.1-8b-instant"         # cheap pre-filter steps
GROQ_TEMPERATURE = 0.0
GROQ_MAX_TOKENS = 2048

# LangSmith
LANGCHAIN_API_KEY = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT = os.getenv("LANGCHAIN_PROJECT", "Knowledge-Base-Agent")

# ─────────────────────────────────────────────────────────────────────────────
# Chunking parameters
# ─────────────────────────────────────────────────────────────────────────────
PYTHON_FALLBACK_CHUNK_LINES = 50    # sliding window if no AST symbols found
PYTHON_FALLBACK_OVERLAP_LINES = 10

JS_FALLBACK_CHUNK_LINES = 60
JS_FALLBACK_OVERLAP_LINES = 10

MAX_COMMIT_HISTORY = 500            # commits per repo
README_SPLIT_BY_HEADING = True      # split README on ## headings

# ─────────────────────────────────────────────────────────────────────────────
# Files / directories to skip during repo walking
# ─────────────────────────────────────────────────────────────────────────────
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "venv", ".venv",
    "env", "dist", "build", ".next", ".nuxt", "coverage",
    ".pytest_cache", ".mypy_cache", "htmlcov", "site-packages",
    "eggs", ".eggs", "migrations",               # django migrations = noise
    "eval",                                       # eval/ dirs inside target repos (test scripts, not user code)
}

# Specific filenames to skip regardless of directory.
# These are one-off debug/check scripts that live at the repo root and
# wouldn't be caught by directory-level filtering.
SKIP_FILENAMES = {
    "check_all.py",      # root-level debug harness committed to MultiSource-RAG-Agent
}

SKIP_FILE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".whl",
    ".lock",                                      # package-lock, poetry.lock
    ".map",                                       # js source maps
}

SUPPORTED_CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".go", ".java", ".rs", ".cpp", ".c", ".h",
}

# ─────────────────────────────────────────────────────────────────────────────
# Retrieval parameters
# ─────────────────────────────────────────────────────────────────────────────
TOP_K_DENSE = 10        # FAISS candidates before BM25 rerank
TOP_K_FINAL = 5         # final chunks returned to synthesis
AMBIGUITY_SCORE_DELTA = 0.05   # threshold: if top-2 within this → ambiguous
AMBIGUITY_MIN_REPOS = 2        # must span ≥2 repos to flag ambiguity

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
API_CORS_ORIGINS = ["http://localhost:3000", "http://localhost:5173"]
