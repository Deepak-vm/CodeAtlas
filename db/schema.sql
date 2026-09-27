-- Run this ONCE in Supabase SQL Editor
-- Go to: supabase.com → your project → SQL Editor → paste → Run

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
