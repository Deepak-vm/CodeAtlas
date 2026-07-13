"""
api/main.py

FastAPI backend for the Knowledge Base Agent.

Endpoints:
  POST /query      — run the full LangGraph pipeline, return answer + citations
  POST /feedback   — record thumbs up/down rating for an answer
  GET  /health     — index status + repos configured
  GET  /repos      — list available repos

Run:
  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import subprocess
from agents.graph import get_app
from agents.retrieval_nodes import _code_faiss, _commit_faiss, _readme_faiss, _code_bm25
from agents.state import AgentState
from api.schemas import AddRepoRequest, Citation, FeedbackRequest, HealthResponse, QueryRequest, QueryResponse

app = FastAPI(
    title="Knowledge Base Agent",
    description="Multi-repo RAG system: ask questions about your own code with citations",
    version="1.0.0",
)

# ── CORS (allow React dev server) ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Lazy-loaded graph (warm on first request, cached after) ───────────────────
_graph_app = None


def _get_graph():
    global _graph_app
    if _graph_app is None:
        _graph_app = get_app()
    return _graph_app


def _load_repos_config() -> list[dict]:
    if config.REPOS_CONFIG_FILE.exists():
        with open(config.REPOS_CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_repos_config(repos: list[dict]) -> None:
    with open(config.REPOS_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(repos, f, indent=4)


def _load_repo_names() -> list[str]:
    return [r["name"] for r in _load_repos_config()]


def _get_repo_chunk_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk_file in [config.CODE_CHUNKS_FILE, config.COMMIT_CHUNKS_FILE, config.README_CHUNKS_FILE]:
        if chunk_file.exists():
            try:
                with open(chunk_file, encoding="utf-8") as f:
                    for line in f:
                        line_str = line.strip()
                        if line_str:
                            data = json.loads(line_str)
                            repo = data.get("repo", "unknown")
                            counts[repo] = counts.get(repo, 0) + 1
            except Exception:
                pass
    return counts


def _get_last_sync_time() -> str:
    paths = [config.CODE_FAISS_PATH, config.CODE_CHUNKS_FILE]
    for p in paths:
        if p.exists():
            mtime = p.stat().st_mtime
            diff_min = max(0, int((time.time() - mtime) / 60))
            if diff_min < 1:
                return "Just now"
            elif diff_min < 60:
                return f"{diff_min} min ago"
            else:
                return f"{diff_min // 60} h ago"
    return "Not synced yet"


def _get_repo_last_sync_time(repo: dict) -> str:
    if repo.get("last_synced"):
        return repo["last_synced"]
    repo_name = repo.get("name", "")
    local_path = config.REPOS_DIR / repo_name
    if local_path.exists():
        try:
            mtime = local_path.stat().st_mtime
            diff_min = max(0, int((time.time() - mtime) / 60))
            if diff_min < 1:
                return "Just now"
            elif diff_min < 60:
                return f"{diff_min} min ago"
            else:
                return datetime.datetime.fromtimestamp(mtime).strftime("%I:%M %p")
        except Exception:
            pass
    return _get_last_sync_time()


def _ingest_and_index_single_repo(repo_name: str) -> None:
    """Ingest only the newly added repository and update vector indexes."""
    print(f"[api] Ingesting single repository: {repo_name}...")
    res_ingest = subprocess.run(
        [sys.executable, "-m", "ingestion.run_ingestion", "--only-repo", repo_name],
        capture_output=True, text=True
    )
    if res_ingest.returncode != 0:
        print(f"[api] Ingestion error: {res_ingest.stderr}")
        raise RuntimeError(f"Ingestion failed: {res_ingest.stderr}")

    print("[api] Updating vector indexes...")
    res_index = subprocess.run([sys.executable, "-m", "indexing.build_indexes"], capture_output=True, text=True)
    if res_index.returncode != 0:
        print(f"[api] Indexing error: {res_index.stderr}")
        raise RuntimeError(f"Indexing failed: {res_index.stderr}")

    _code_faiss.cache_clear()
    _commit_faiss.cache_clear()
    _readme_faiss.cache_clear()
    _code_bm25.cache_clear()
    print(f"[api] Ingestion and indexing complete for {repo_name}!")


def _delete_repo_and_reindex(repo_name: str) -> None:
    """
    Instantly remove a repo from all indexes WITHOUT re-embedding any remaining repos.
    Steps:
      1. Strip JSONL chunks for deleted repo from chunk files.
      2. Patch each FAISS index in-place (reconstruct kept vectors, no JinaAI calls).
      3. Patch BM25 index in-place (retokenize kept chunks, no JinaAI calls).
      4. Clear in-memory caches.
    """
    from ingestion.run_ingestion import _remove_repo_from_jsonl
    from indexing.faiss_store import FaissStore
    from indexing.bm25_store import BM25Store

    print(f"[api] Step 1: Stripping JSONL chunks for '{repo_name}'...")
    _remove_repo_from_jsonl(config.CODE_CHUNKS_FILE, repo_name)
    _remove_repo_from_jsonl(config.COMMIT_CHUNKS_FILE, repo_name)
    _remove_repo_from_jsonl(config.README_CHUNKS_FILE, repo_name)

    print(f"[api] Step 2: Patching FAISS indexes in-place (no re-embedding)...")
    FaissStore.remove_repo_and_save(config.CODE_FAISS_PATH, repo_name)
    FaissStore.remove_repo_and_save(config.COMMIT_FAISS_PATH, repo_name)
    FaissStore.remove_repo_and_save(config.README_FAISS_PATH, repo_name)

    print(f"[api] Step 3: Patching BM25 index in-place...")
    BM25Store.remove_repo_and_save(config.BM25_CODE_PATH, repo_name)

    print(f"[api] Step 4: Clearing in-memory retriever caches...")
    _code_faiss.cache_clear()
    _commit_faiss.cache_clear()
    _readme_faiss.cache_clear()
    _code_bm25.cache_clear()

    print(f"[api] ✓ Deletion complete for '{repo_name}' — no other repos were re-indexed!")


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest) -> QueryResponse:
    """
    Run the full multi-agent RAG pipeline.
    Returns a grounded answer with file:line citations.
    """
    t0 = time.perf_counter()

    # Guard: refuse queries when no repos are configured
    configured_repos = _load_repos_config()
    if not configured_repos:
        raise HTTPException(
            status_code=400,
            detail="No repositories are configured. Please add and index at least one repository from the Repositories page before querying."
        )

    graph = _get_graph()

    # If caller passed specific repos, validate and use; otherwise let router decide
    initial_repos = req.repos if req.repos else []

    initial_state: AgentState = {
        "query": req.query,
        "routed_repos": initial_repos,
        "routed_types": [],
        "code_chunks": [],
        "commit_chunks": [],
        "readme_chunks": [],
        "ambiguity_flag": False,
        "ambiguity_detail": "",
        "conversation_history": [
            {"query": t.query, "answer": t.answer}
            for t in (req.conversation_history or [])
        ],
        "final_answer": "",
        "citations": [],
    }

    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    latency_ms = (time.perf_counter() - t0) * 1000

    citations = [
        Citation(
            repo=c.get("repo", ""),
            file_path=c.get("file_path"),
            start_line=c.get("start_line"),
            end_line=c.get("end_line"),
            symbol_name=c.get("symbol_name"),
            commit_hash=c.get("commit_hash"),
            language=c.get("language"),
            snippet=c.get("snippet", ""),
            chunk_type=c.get("chunk_type", "code"),
        )
        for c in result.get("citations", [])
    ]

    return QueryResponse(
        answer=result.get("final_answer", ""),
        citations=citations,
        ambiguity_flag=result.get("ambiguity_flag", False),
        ambiguity_detail=result.get("ambiguity_detail", ""),
        latency_ms=round(latency_ms, 1),
        routed_repos=result.get("routed_repos", []),
        routed_types=result.get("routed_types", []),
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Check index files and repo configuration."""
    return HealthResponse(
        status="ok",
        indexes_loaded={
            "code": config.CODE_FAISS_PATH.exists(),
            "commits": config.COMMIT_FAISS_PATH.exists(),
            "readme": config.README_FAISS_PATH.exists(),
            "bm25_code": config.BM25_CODE_PATH.exists(),
        },
        repos_configured=_load_repo_names(),
    )


@app.get("/repos")
async def list_repos() -> dict:
    """Return configured repos with details, chunk counts, and sync status."""
    config_repos = _load_repos_config()
    chunk_counts = _get_repo_chunk_counts()
    last_sync = _get_last_sync_time()

    repos_detail = [
        {
            "name": r["name"],
            "url": r.get("url", ""),
            "chunk_count": chunk_counts.get(r["name"], 0),
            "last_synced": _get_repo_last_sync_time(r),
        }
        for r in config_repos
    ]

    names = [r["name"] for r in config_repos]
    return {
        "repos": names,
        "repos_detail": repos_detail,
        "count": len(names),
        "chunk_counts": chunk_counts,
        "last_sync": last_sync
    }


@app.post("/repos/add")
async def add_repo(req: AddRepoRequest) -> dict:
    """Add a new repository to repos.json and trigger single-repo ingestion & indexing."""
    existing = _load_repos_config()

    if any(r["name"].lower() == req.name.lower() for r in existing):
        raise HTTPException(status_code=400, detail=f"Repository '{req.name}' already exists.")

    new_repo = {
        "name": req.name.strip(),
        "url": req.url.strip(),
        "last_synced": datetime.datetime.now().strftime("%I:%M %p"),
    }
    existing.append(new_repo)
    _save_repos_config(existing)

    try:
        _ingest_and_index_single_repo(req.name.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to ingest/index repo: {e}")

    return {"status": "ok", "message": f"Repository '{req.name}' added and indexed successfully."}


@app.delete("/repos/{repo_name}")
async def delete_repo(repo_name: str) -> dict:
    """Delete a repository from repos.json and update remaining index."""
    existing = _load_repos_config()
    filtered = [r for r in existing if r["name"].lower() != repo_name.lower()]

    if len(filtered) == len(existing):
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")

    _save_repos_config(filtered)

    try:
        _delete_repo_and_reindex(repo_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update index after deletion: {e}")

    return {"status": "ok", "message": f"Repository '{repo_name}' removed and index updated."}


@app.post("/repos/{repo_name}/update")
async def update_repo(repo_name: str) -> dict:
    """
    Re-index a single repository in-place.
    Steps:
      1. Strip old chunks/vectors for this repo only (same as delete, no other repos touched).
      2. Re-ingest only this repo (git pull → AST chunk → JinaAI embed).
      3. Append new vectors to FAISS/BM25 indexes.
      Other repos remain completely untouched — no re-embedding of them.
    """
    existing = _load_repos_config()
    repo_entry = next((r for r in existing if r["name"].lower() == repo_name.lower()), None)

    if not repo_entry:
        raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found in configuration.")

    try:
        # Step 1: strip old data for this repo from all indexes
        _delete_repo_and_reindex(repo_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to strip old index data: {e}")

    try:
        # Step 2: re-ingest & re-embed only this repo (pulls latest from git)
        _ingest_and_index_single_repo(repo_name)
        # Update last_synced timestamp in repos.json
        for r in existing:
            if r["name"].lower() == repo_name.lower():
                r["last_synced"] = datetime.datetime.now().strftime("%I:%M %p")
        _save_repos_config(existing)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to re-ingest repo: {e}")

    return {"status": "ok", "message": f"Repository '{repo_name}' updated successfully — only this repo was re-indexed."}


@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """
    Record a thumbs-up or thumbs-down rating for an answer.
    Appends a labeled row to data/feedback.jsonl for eval dataset building.
    """
    feedback_path = config.DATA_DIR / "feedback.jsonl"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "query": req.query,
        "answer_snippet": req.answer_snippet[:200],
        "rating": req.rating,
        "routed_repos": req.routed_repos,
    }

    with open(feedback_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[feedback] {req.rating} — '{req.query[:60]}...'")
    return {"status": "ok", "recorded": req.rating}

