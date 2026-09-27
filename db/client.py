"""
db/client.py

Supabase client using the official supabase-py SDK.
Communicates via HTTPS REST API (port 443) — works on Render free tier.

Direct psycopg2 / port 5432 is NOT used here because Render free tier
blocks outbound TCP to that port.

Required env vars:
  SUPABASE_URL          https://your-project.supabase.co
  SUPABASE_SERVICE_KEY  service_role secret key (from Supabase → Settings → API)

Tables (create once in Supabase SQL editor — see bootstrap_schema_sql below):
  repos           — repo metadata
  query_history   — every query+answer stored globally
  feedback        — thumbs up/down ratings
"""

from __future__ import annotations

import json
import os
from typing import Any

from supabase import create_client, Client

# ── Lazy singleton ─────────────────────────────────────────────────────────────
_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY env vars must be set. "
                "Get them from Supabase dashboard → Project Settings → API."
            )
        _client = create_client(url, key)
    return _client


# ── Schema SQL (run ONCE in Supabase SQL editor) ───────────────────────────────
# Go to: supabase.com → your project → SQL Editor → paste and run this

BOOTSTRAP_SCHEMA_SQL = """
-- Run this once in Supabase SQL Editor to create the tables

CREATE TABLE IF NOT EXISTS repos (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    url          TEXT NOT NULL DEFAULT '',
    last_synced  TEXT NOT NULL DEFAULT '',
    chunk_count  INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_history (
    id               SERIAL PRIMARY KEY,
    query            TEXT NOT NULL,
    answer           TEXT NOT NULL DEFAULT '',
    routed_repos     JSONB NOT NULL DEFAULT '[]',
    routed_types     JSONB NOT NULL DEFAULT '[]',
    citations        JSONB NOT NULL DEFAULT '[]',
    latency_ms       FLOAT NOT NULL DEFAULT 0,
    ambiguity_flag   BOOLEAN NOT NULL DEFAULT FALSE,
    ambiguity_detail TEXT NOT NULL DEFAULT '',
    saved            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    query           TEXT NOT NULL,
    answer_snippet  TEXT NOT NULL DEFAULT '',
    rating          TEXT NOT NULL CHECK (rating IN ('up', 'down')),
    routed_repos    JSONB NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_history_created ON query_history (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback (created_at DESC);
"""


def bootstrap_schema() -> None:
    """Verify the connection is alive at startup. Tables must be pre-created via SQL editor."""
    try:
        sb = get_client()
        # simple ping — just list repos (empty list is fine)
        sb.table("repos").select("id").limit(1).execute()
        print("[db] ✓ Supabase connection OK (HTTPS REST API)")
    except Exception as e:
        print(f"[db] ⚠ Supabase connection failed: {e}")
        print("[db]   → Make sure SUPABASE_URL and SUPABASE_SERVICE_KEY are set")
        print("[db]   → Tables must exist — run BOOTSTRAP_SCHEMA_SQL in Supabase SQL editor")


# ── Repos CRUD ─────────────────────────────────────────────────────────────────

def get_all_repos() -> list[dict]:
    sb = get_client()
    res = sb.table("repos").select("name,url,last_synced,chunk_count").order("created_at").execute()
    return res.data or []


def repo_exists(name: str) -> bool:
    sb = get_client()
    res = sb.table("repos").select("id").ilike("name", name).limit(1).execute()
    return len(res.data) > 0


def upsert_repo(name: str, url: str, last_synced: str = "", chunk_count: int = 0) -> None:
    sb = get_client()
    sb.table("repos").upsert(
        {"name": name, "url": url, "last_synced": last_synced, "chunk_count": chunk_count},
        on_conflict="name",
    ).execute()


def update_repo_sync(name: str, last_synced: str, chunk_count: int = 0) -> None:
    sb = get_client()
    sb.table("repos").update(
        {"last_synced": last_synced, "chunk_count": chunk_count}
    ).ilike("name", name).execute()


def delete_repo(name: str) -> bool:
    sb = get_client()
    res = sb.table("repos").delete().ilike("name", name).execute()
    return len(res.data) > 0


# ── Query History CRUD ─────────────────────────────────────────────────────────

def save_query(
    query: str,
    answer: str,
    routed_repos: list[str],
    routed_types: list[str],
    citations: list[dict],
    latency_ms: float,
    ambiguity_flag: bool = False,
    ambiguity_detail: str = "",
) -> int:
    """Insert a query record and return its ID."""
    sb = get_client()
    res = sb.table("query_history").insert({
        "query": query,
        "answer": answer,
        "routed_repos": routed_repos,
        "routed_types": routed_types,
        "citations": citations,
        "latency_ms": latency_ms,
        "ambiguity_flag": ambiguity_flag,
        "ambiguity_detail": ambiguity_detail,
    }).execute()
    return res.data[0]["id"] if res.data else -1


def get_history(limit: int = 100) -> list[dict]:
    """Return most recent queries, newest first."""
    sb = get_client()
    res = (
        sb.table("query_history")
        .select("id,query,answer,routed_repos,routed_types,citations,latency_ms,ambiguity_flag,ambiguity_detail,saved,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def toggle_history_saved(history_id: int, saved: bool) -> None:
    sb = get_client()
    sb.table("query_history").update({"saved": saved}).eq("id", history_id).execute()


def delete_history_item(history_id: int) -> None:
    sb = get_client()
    sb.table("query_history").delete().eq("id", history_id).execute()


def bulk_delete_history(ids: list[int]) -> None:
    if not ids:
        return
    sb = get_client()
    sb.table("query_history").delete().in_("id", ids).execute()


# ── Feedback CRUD ──────────────────────────────────────────────────────────────

def save_feedback(
    query: str,
    answer_snippet: str,
    rating: str,
    routed_repos: list[str],
) -> None:
    sb = get_client()
    sb.table("feedback").insert({
        "query": query,
        "answer_snippet": answer_snippet[:200],
        "rating": rating,
        "routed_repos": routed_repos,
    }).execute()
