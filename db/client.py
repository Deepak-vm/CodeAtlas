"""
db/client.py

Supabase PostgreSQL client using psycopg2 (direct connection, no extra SDK needed).

Tables managed here:
  - repos          : repo metadata (name, url, last_synced, chunk_count)
  - query_history  : every query + answer stored globally (shared across all users)
  - feedback       : thumbs up/down ratings

Connection string comes from DB_URL env var.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

# ── Connection pool (1-5 connections, Supabase free tier is generous) ─────────
_pool: ThreadedConnectionPool | None = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        db_url = os.getenv("DB_URL", "")
        if not db_url:
            raise RuntimeError(
                "DB_URL env var is not set. Add it to .env or Render dashboard."
            )
        _pool = ThreadedConnectionPool(1, 5, dsn=db_url, sslmode="require")
    return _pool


@contextmanager
def get_conn():
    """Context manager: borrow a connection from pool, return after use."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


# ── Schema bootstrap (called once at API startup) ─────────────────────────────

SCHEMA_SQL = """
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
    """Create tables if they don't exist. Safe to run on every startup."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
        print("[db] ✓ Supabase schema bootstrapped")
    except Exception as e:
        print(f"[db] ⚠ Schema bootstrap failed: {e} — app will continue without DB")


# ── Repos CRUD ─────────────────────────────────────────────────────────────────

def get_all_repos() -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT name, url, last_synced, chunk_count FROM repos ORDER BY created_at")
            return [dict(r) for r in cur.fetchall()]


def repo_exists(name: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM repos WHERE LOWER(name) = LOWER(%s)", (name,))
            return cur.fetchone() is not None


def upsert_repo(name: str, url: str, last_synced: str = "", chunk_count: int = 0) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO repos (name, url, last_synced, chunk_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET url = EXCLUDED.url,
                    last_synced = EXCLUDED.last_synced,
                    chunk_count = EXCLUDED.chunk_count
                """,
                (name, url, last_synced, chunk_count),
            )


def update_repo_sync(name: str, last_synced: str, chunk_count: int = 0) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE repos SET last_synced = %s, chunk_count = %s WHERE LOWER(name) = LOWER(%s)",
                (last_synced, chunk_count, name),
            )


def delete_repo(name: str) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM repos WHERE LOWER(name) = LOWER(%s)", (name,))
            return cur.rowcount > 0


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
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_history
                    (query, answer, routed_repos, routed_types, citations, latency_ms, ambiguity_flag, ambiguity_detail)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    query,
                    answer,
                    json.dumps(routed_repos),
                    json.dumps(routed_types),
                    json.dumps(citations),
                    latency_ms,
                    ambiguity_flag,
                    ambiguity_detail,
                ),
            )
            return cur.fetchone()[0]


def get_history(limit: int = 100) -> list[dict]:
    """Return most recent queries, newest first."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, query, answer, routed_repos, routed_types,
                       citations, latency_ms, ambiguity_flag, ambiguity_detail,
                       saved, created_at
                FROM query_history
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            result = []
            for r in rows:
                row = dict(r)
                # created_at → ISO string
                if isinstance(row["created_at"], datetime):
                    row["created_at"] = row["created_at"].isoformat()
                result.append(row)
            return result


def toggle_history_saved(history_id: int, saved: bool) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE query_history SET saved = %s WHERE id = %s", (saved, history_id))


def delete_history_item(history_id: int) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM query_history WHERE id = %s", (history_id,))


def bulk_delete_history(ids: list[int]) -> None:
    if not ids:
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM query_history WHERE id = ANY(%s)", (ids,))


# ── Feedback CRUD ──────────────────────────────────────────────────────────────

def save_feedback(
    query: str,
    answer_snippet: str,
    rating: str,
    routed_repos: list[str],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO feedback (query, answer_snippet, rating, routed_repos)
                VALUES (%s, %s, %s, %s)
                """,
                (query, answer_snippet[:200], rating, json.dumps(routed_repos)),
            )
