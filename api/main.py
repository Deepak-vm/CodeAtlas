"""
api/main.py

FastAPI backend for the Knowledge Base Agent.

Storage:
  - Supabase PostgreSQL (repos metadata, query history, feedback)
  - Render persistent disk (FAISS indexes, chunk JSONL files — binary, must be on disk)

Endpoints:
  POST /query              — run the full LangGraph pipeline, return answer + citations
  POST /feedback           — record thumbs up/down rating (→ Supabase)
  GET  /history            — fetch all query history from Supabase
  POST /history/{id}/save  — toggle saved flag on a history item
  DELETE /history/{id}     — delete a single history item
  DELETE /history/bulk     — bulk delete history items
  GET  /health             — index status + repos configured
  GET  /repos              — list available repos (from Supabase)
  POST /repos/add          — add + index a repo (metadata → Supabase)
  DELETE /repos/{name}     — delete repo (Supabase + indexes)
  POST /repos/{name}/update — re-index a repo (update Supabase timestamp)
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
import subprocess
import db.client as db
from agents.graph import get_app
from agents.retrieval_nodes import _code_faiss, _commit_faiss, _readme_faiss, _code_bm25
from agents.state import AgentState
from api.schemas import (
    AddRepoRequest, Citation, FeedbackRequest,
    HealthResponse, QueryRequest, QueryResponse,
)

app = FastAPI(
    title="Knowledge Base Agent",
    description="Multi-repo RAG system: ask questions about your own code with citations",
    version="2.0.0",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup: ensure disk dirs exist + bootstrap Supabase schema ───────────────
config.DATA_DIR.mkdir(parents=True, exist_ok=True)
config.CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
config.INDEXES_DIR.mkdir(parents=True, exist_ok=True)
config.REPOS_DIR.mkdir(parents=True, exist_ok=True)
db.bootstrap_schema()   # creates tables if they don't exist

# ── Lazy-loaded LangGraph pipeline ────────────────────────────────────────────
_graph_app = None


def _get_graph():
    global _graph_app
    if _graph_app is None:
        _graph_app = get_app()
    return _graph_app


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    from ingestion.run_ingestion import _remove_repo_from_jsonl
    from indexing.faiss_store import FaissStore
    from indexing.bm25_store import BM25Store

    print(f"[api] Step 1: Stripping JSONL chunks for '{repo_name}'...")
    _remove_repo_from_jsonl(config.CODE_CHUNKS_FILE, repo_name)
    _remove_repo_from_jsonl(config.COMMIT_CHUNKS_FILE, repo_name)
    _remove_repo_from_jsonl(config.README_CHUNKS_FILE, repo_name)

    print(f"[api] Step 2: Patching FAISS indexes in-place...")
    FaissStore.remove_repo_and_save(config.CODE_FAISS_PATH, repo_name)
    FaissStore.remove_repo_and_save(config.COMMIT_FAISS_PATH, repo_name)
    FaissStore.remove_repo_and_save(config.README_FAISS_PATH, repo_name)

    print(f"[api] Step 3: Patching BM25 index...")
    BM25Store.remove_repo_and_save(config.BM25_CODE_PATH, repo_name)

    print(f"[api] Step 4: Clearing in-memory caches...")
    _code_faiss.cache_clear()
    _commit_faiss.cache_clear()
    _readme_faiss.cache_clear()
    _code_bm25.cache_clear()
    print(f"[api] ✓ Deletion complete for '{repo_name}'")


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Query
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest) -> QueryResponse:
    """Run the full multi-agent RAG pipeline and save result to Supabase."""
    t0 = time.perf_counter()

    configured_repos = db.get_all_repos()
    if not configured_repos:
        raise HTTPException(
            status_code=400,
            detail="No repositories are configured. Please add and index at least one repository from the Repositories page before querying.",
        )

    graph = _get_graph()
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

    citations_raw = result.get("citations", [])
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
        for c in citations_raw
    ]

    # ── Save to Supabase (non-blocking best-effort) ───────────────────────────
    try:
        db.save_query(
            query=req.query,
            answer=result.get("final_answer", ""),
            routed_repos=result.get("routed_repos", []),
            routed_types=result.get("routed_types", []),
            citations=citations_raw,
            latency_ms=round(latency_ms, 1),
            ambiguity_flag=result.get("ambiguity_flag", False),
            ambiguity_detail=result.get("ambiguity_detail", ""),
        )
    except Exception as e:
        print(f"[db] Warning: could not save query to Supabase: {e}")

    return QueryResponse(
        answer=result.get("final_answer", ""),
        citations=citations,
        ambiguity_flag=result.get("ambiguity_flag", False),
        ambiguity_detail=result.get("ambiguity_detail", ""),
        latency_ms=round(latency_ms, 1),
        routed_repos=result.get("routed_repos", []),
        routed_types=result.get("routed_types", []),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Query History
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/history")
async def get_history(limit: int = 100) -> dict:
    """Fetch shared query history from Supabase (newest first)."""
    try:
        items = db.get_history(limit=limit)
        return {"history": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {e}")


@app.post("/history/{history_id}/save")
async def toggle_save_history(history_id: int, body: dict = Body(default={})) -> dict:
    """Toggle the 'saved' bookmark flag on a history item."""
    saved = body.get("saved", True)
    try:
        db.toggle_history_saved(history_id, saved)
        return {"status": "ok", "id": history_id, "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update history item: {e}")


@app.delete("/history/{history_id}")
async def delete_history_item(history_id: int) -> dict:
    """Delete a single history entry."""
    try:
        db.delete_history_item(history_id)
        return {"status": "ok", "deleted": history_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete history item: {e}")


@app.post("/history/bulk-delete")
async def bulk_delete_history(body: dict = Body(...)) -> dict:
    """Bulk delete history items by list of IDs."""
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    try:
        db.bulk_delete_history(ids)
        return {"status": "ok", "deleted_count": len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk delete: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Feedback
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """Record a thumbs-up or thumbs-down rating → Supabase feedback table."""
    try:
        db.save_feedback(
            query=req.query,
            answer_snippet=req.answer_snippet,
            rating=req.rating,
            routed_repos=req.routed_repos,
        )
    except Exception as e:
        print(f"[db] Warning: could not save feedback: {e}")

    print(f"[feedback] {req.rating} — '{req.query[:60]}...'")
    return {"status": "ok", "recorded": req.rating}


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Check index files and repo configuration."""
    try:
        repo_names = [r["name"] for r in db.get_all_repos()]
    except Exception:
        repo_names = []

    return HealthResponse(
        status="ok",
        indexes_loaded={
            "code": config.CODE_FAISS_PATH.exists(),
            "commits": config.COMMIT_FAISS_PATH.exists(),
            "readme": config.README_FAISS_PATH.exists(),
            "bm25_code": config.BM25_CODE_PATH.exists(),
        },
        repos_configured=repo_names,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Repos
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/repos")
async def list_repos() -> dict:
    """Return configured repos with chunk counts from Supabase."""
    try:
        config_repos = db.get_all_repos()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load repos: {e}")

    chunk_counts = _get_repo_chunk_counts()
    last_sync = _get_last_sync_time()

    repos_detail = [
        {
            "name": r["name"],
            "url": r.get("url", ""),
            "chunk_count": chunk_counts.get(r["name"], r.get("chunk_count", 0)),
            "last_synced": r.get("last_synced", last_sync),
        }
        for r in config_repos
    ]

    names = [r["name"] for r in config_repos]
    return {
        "repos": names,
        "repos_detail": repos_detail,
        "count": len(names),
        "chunk_counts": chunk_counts,
        "last_sync": last_sync,
    }


@app.post("/repos/add")
async def add_repo(req: AddRepoRequest) -> dict:
    """Add a new repository to Supabase and trigger ingestion + indexing."""
    try:
        if db.repo_exists(req.name):
            raise HTTPException(status_code=400, detail=f"Repository '{req.name}' already exists.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error checking repo: {e}")

    now = datetime.datetime.now().strftime("%I:%M %p")
    try:
        db.upsert_repo(name=req.name.strip(), url=req.url.strip(), last_synced=now)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save repo to DB: {e}")

    try:
        _ingest_and_index_single_repo(req.name.strip())
    except Exception as e:
        # Roll back DB entry if ingestion fails
        try:
            db.delete_repo(req.name.strip())
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to ingest/index repo: {e}")

    # Update chunk count in DB after successful indexing
    chunk_counts = _get_repo_chunk_counts()
    try:
        db.update_repo_sync(
            name=req.name.strip(),
            last_synced=now,
            chunk_count=chunk_counts.get(req.name.strip(), 0),
        )
    except Exception:
        pass  # non-critical

    return {"status": "ok", "message": f"Repository '{req.name}' added and indexed successfully."}


@app.delete("/repos/{repo_name}")
async def delete_repo_endpoint(repo_name: str) -> dict:
    """Delete a repository from Supabase and remove from indexes."""
    try:
        removed = db.delete_repo(repo_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    try:
        _delete_repo_and_reindex(repo_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update index after deletion: {e}")

    return {"status": "ok", "message": f"Repository '{repo_name}' removed and index updated."}


@app.post("/repos/{repo_name}/update")
async def update_repo(repo_name: str) -> dict:
    """Re-index a single repository in-place and update Supabase timestamp."""
    try:
        if not db.repo_exists(repo_name):
            raise HTTPException(status_code=404, detail=f"Repository '{repo_name}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    try:
        _delete_repo_and_reindex(repo_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to strip old index data: {e}")

    try:
        _ingest_and_index_single_repo(repo_name)
        now = datetime.datetime.now().strftime("%I:%M %p")
        chunk_counts = _get_repo_chunk_counts()
        db.update_repo_sync(
            name=repo_name,
            last_synced=now,
            chunk_count=chunk_counts.get(repo_name, 0),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to re-ingest repo: {e}")

    return {"status": "ok", "message": f"Repository '{repo_name}' updated successfully."}
