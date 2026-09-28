# CodeAtlas — Multi-Repo Codebase Knowledge Agent

A self-hostable RAG (Retrieval-Augmented Generation) system that lets you **ask natural-language questions about your own code** and get cited, grounded answers. Add any GitHub repository from the UI, and the agent will index it so you can query across all your projects at once.

**Live demo:** [code-atlas-snowy.vercel.app](https://code-atlas-snowy.vercel.app)  
**Backend API:** [codeatlas-zyys.onrender.com](https://codeatlas-zyys.onrender.com/docs)

---

## What it does

- **Ask anything about your code** — "Where did I implement retry logic?", "Who changed the auth layer and why?", "How does the WebSocket connection work?"
- **Multi-repo search** — index multiple repos and filter by repo at query time
- **Three content types** — code (AST-chunked), git commit history, and README/docs
- **Hybrid retrieval** — FAISS dense search + BM25 keyword rerank for code; dense-only for commits and docs
- **Cross-repo ambiguity detection** — when the same concept appears in multiple repos, the agent compares implementations instead of picking one silently
- **Grounded answers** — every claim links to a specific file and line number
- **Multi-turn conversation** — follow-up questions use the last 3 turns of session context
- **Persistent history** — all queries and answers are saved to Supabase and visible in the History tab
- **Thumbs feedback** — rate answers up or down; feedback is saved to Supabase

---

## Architecture

```
Frontend (React/Vite, Vercel)
    │
    └── POST /query ──────────────────────────────────────────────────┐
                                                                       │
Backend (FastAPI, Render free tier)                                    │
    │                                                                  │
    └── LangGraph StateGraph pipeline                                  │
          │                                                            │
          ├── route_query          ← Groq LLM decides which repos      │
          │                          and content types to search       │
          │                                                            │
          ├── retrieve_code        ┐                                   │
          ├── retrieve_commits     ├── 3 parallel branches             │
          └── retrieve_readme      ┘                                   │
                    │                                                  │
                    ▼                                                  │
             check_ambiguity       ← detects cross-repo conflicts      │
                    │                                                  │
                    ▼                                                  │
            synthesize_answer      ← Groq LLM generates cited answer  │
                    │                                                  │
                    ▼                                                  │
            format_citations       ← structured citation list         │
                    │                                                  │
                    └──────────────────────────────────────────────────┘

Data layer
    ├── Supabase PostgreSQL  — repos table, query_history, feedback
    └── Supabase Storage     — FAISS + BM25 + JSONL chunks (bucket: kb-indexes)
                               (no persistent disk needed on Render free tier)
```

---

## Tech stack

| Layer | Technology |
|:---|:---|
| Frontend | React 18, Vite, Material UI icons, react-markdown |
| Backend | FastAPI + Uvicorn, Python 3.11+ |
| Agent orchestration | LangGraph (`StateGraph` with parallel fan-out) |
| LLM | Groq API (`openai/gpt-oss-120b` primary, `openai/gpt-oss-20b` fast) |
| Embeddings | Jina Embeddings API (`jina-embeddings-v2-base-code`, dim=768) |
| Vector index | FAISS `IndexFlatIP` (inner-product / cosine similarity) |
| Keyword index | BM25 (`rank-bm25`) with camelCase tokenisation |
| Code parsing | Python `ast` module; tree-sitter for JS/TS/JSX/TSX |
| Git history | GitPython |
| Database | Supabase (PostgreSQL via HTTPS REST API) |
| Index persistence | Supabase Storage bucket `kb-indexes` |
| Deployment | Render (backend, free tier) + Vercel (frontend) |

---

## Repository structure

```
Knowledge-Base-Agent/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory + startup (restores indexes from Supabase)
│   │   ├── agent/
│   │   │   ├── graph.py         # LangGraph StateGraph assembly
│   │   │   ├── state.py         # AgentState TypedDict
│   │   │   ├── nodes/
│   │   │   │   ├── router.py    # route_query node (Groq LLM → repos + content types)
│   │   │   │   ├── retrieve.py  # retrieve_code / retrieve_commits / retrieve_readme
│   │   │   │   ├── ambiguity.py # check_ambiguity node (cross-repo conflict detection)
│   │   │   │   ├── synthesize.py# synthesize_answer node (Groq LLM)
│   │   │   │   └── citations.py # format_citations node
│   │   │   └── prompts/
│   │   │       ├── router.py    # Router system prompt + few-shot examples
│   │   │       └── answer.py    # Synthesis prompts (normal + ambiguity mode)
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py      # POST /query, GET /history, POST /feedback, etc.
│   │   │       ├── repos.py     # GET /repos, POST /repos/add, DELETE, POST /update
│   │   │       └── health.py    # GET /health, GET /debug/disk, GET /debug/storage
│   │   ├── core/
│   │   │   ├── config.py        # All settings (env vars, paths, model names, thresholds)
│   │   │   ├── exceptions.py    # Typed exception hierarchy → clean JSON error responses
│   │   │   └── logging.py       # Structured JSON logging
│   │   ├── database/
│   │   │   ├── client.py        # Supabase client singleton
│   │   │   ├── storage.py       # Supabase Storage — upload/download index files
│   │   │   └── repositories/
│   │   │       ├── repos.py     # CRUD for `repos` table
│   │   │       ├── history.py   # CRUD for `query_history` table
│   │   │       └── feedback.py  # CRUD for `feedback` table
│   │   ├── ingestion/
│   │   │   ├── pipeline.py      # ingest_and_write() — orchestrates all loaders/chunkers
│   │   │   ├── loaders/
│   │   │   │   ├── filesystem.py# collect_code_files(), collect_doc_files()
│   │   │   │   └── git.py       # ingest_commits() via GitPython
│   │   │   ├── chunkers/
│   │   │   │   ├── python_chunker.py # AST-aware Python chunking (ast module)
│   │   │   │   └── javascript.py     # tree-sitter chunking for JS/TS/JSX/TSX
│   │   │   └── parsers/
│   │   │       └── markdown.py  # chunk_readme_file() — splits by heading
│   │   ├── indexing/
│   │   │   ├── pipeline.py      # build_all_indexes() — reads JSONL, embeds, saves
│   │   │   ├── vector/
│   │   │   │   ├── embedder.py  # Jina API or local sentence-transformers
│   │   │   │   └── faiss.py     # FaissStore — add/search/save/load/remove_repo
│   │   │   └── keyword/
│   │   │       └── bm25.py      # BM25Store — build/search/save/load/remove_repo
│   │   ├── retrieval/
│   │   │   └── pipeline.py      # RetrievalPipeline — search_code / commits / readme
│   │   ├── services/
│   │   │   ├── repo_service.py  # Business logic: add/update/delete repos + index lifecycle
│   │   │   └── chat_service.py  # Orchestrates LangGraph pipeline for a query
│   │   └── schemas/
│   │       ├── chat.py          # QueryRequest, QueryResponse, Citation, FeedbackRequest
│   │       └── repo.py          # AddRepoRequest, HealthResponse
│   ├── data/                    # Runtime data (gitignored)
│   │   ├── raw/repos/           # Cloned GitHub repos
│   │   ├── processed/           # JSONL chunk files
│   │   └── indexes/             # FAISS + BM25 binary indexes
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── App.jsx              # Main UI (sidebar nav, query input, citations, history)
│       ├── services/api.js      # Axios instance (dev proxy / prod Render URL)
│       └── components/repos/
│           ├── AddRepoModal.jsx
│           ├── ReposView.jsx
│           └── UpdateOverlay.jsx
├── requirements.txt
├── render.yaml                  # Render.com deployment blueprint
├── runtime.txt                  # Python 3.11
└── .env.example
```

---

## How ingestion works

When you click **Add** or **Sync** on a repo:

1. **Clone** the GitHub repo into `backend/data/raw/repos/<name>/` (depth 500)
2. **Code chunking** — Python files use `ast.parse()` to extract functions, async functions, and class methods as individual chunks. JS/TS/JSX/TSX use tree-sitter for accurate symbol boundaries (with a regex fallback if tree-sitter is unavailable).
3. **Commit chunking** — GitPython walks the last 500 commits (skipping merges), capturing hash, message, author, date, and changed files per commit.
4. **README / doc chunking** — Markdown files are split at heading boundaries.
5. All chunks are appended to JSONL files in `backend/data/processed/`.
6. **Embedding** — chunks are sent to the Jina Embeddings API in batches of 64 (`jina-embeddings-v2-base-code`, 768-dim). Rate-limit 429 responses are retried with exponential backoff (30s → 60s → 120s).
7. **FAISS indexing** — three separate `IndexFlatIP` indexes are built: code, commits, readme.
8. **BM25 indexing** — a BM25Okapi index is built on code chunks with camelCase/snake_case tokenisation.
9. **Supabase Storage upload** — all FAISS, BM25, and JSONL files are uploaded to the `kb-indexes` bucket so they survive Render restarts.

On every backend **startup**, the index files are downloaded from Supabase Storage back to local disk before the server starts accepting requests.

---

## How retrieval works

For each query:

1. **Routing** — the Groq LLM reads the query and decides which repos and content types (`code`, `commits`, `readme`) to search. If the user has already selected repo filters in the UI, those are honoured and the LLM only decides content types.
2. **Parallel retrieval** — three LangGraph nodes run simultaneously:
   - `retrieve_code`: FAISS dense search (top-10) → BM25 rerank → top-5 chunks. Hybrid score = 60% FAISS + 40% BM25.
   - `retrieve_commits`: FAISS dense only, top-5
   - `retrieve_readme`: FAISS dense only, top-5
3. **Ambiguity check** — if the top code chunks span ≥2 repos, the ambiguity flag is set and the synthesiser uses a compare-and-contrast prompt instead.
4. **Synthesis** — the Groq LLM receives all retrieved chunks and generates an answer with explicit `repo/file:line` citations. Last 3 turns of session conversation are included for follow-up context.
5. **Citations** — a regex parses citation markers from the answer text and merges with chunk metadata. All retrieved chunks are also included as supporting sources.

---

## Local development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Groq API key](https://console.groq.com/)
- A [Jina API key](https://jina.ai/) (free tier: 1M tokens)
- A [Supabase project](https://supabase.com/) with the schema below

### Supabase schema

Run this SQL in **Supabase → SQL Editor**:

```sql
-- Repos
create table if not exists repos (
  id           bigint generated always as identity primary key,
  name         text unique not null,
  url          text,
  last_synced  text,
  chunk_count  int default 0,
  created_at   timestamptz default now()
);

-- Query history
create table if not exists query_history (
  id               bigint generated always as identity primary key,
  query            text not null,
  answer           text,
  routed_repos     text[],
  routed_types     text[],
  citations        jsonb,
  latency_ms       float,
  ambiguity_flag   boolean default false,
  ambiguity_detail text,
  saved            boolean default false,
  created_at       timestamptz default now()
);

-- Feedback
create table if not exists feedback (
  id             bigint generated always as identity primary key,
  query          text,
  answer_snippet text,
  rating         text,
  routed_repos   text[],
  created_at     timestamptz default now()
);
```

### Setup

```bash
# 1. Clone
git clone https://github.com/Deepak-vm/CodeAtlas.git
cd CodeAtlas

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install backend deps
pip install -r requirements.txt

# 4. Copy and fill in env vars
cp .env.example .env
# Edit .env with your keys

# 5. Start backend
uvicorn backend.app.main:app --reload --port 8000

# 6. In a separate terminal — start frontend
cd frontend
npm install
npm run dev
# Opens at http://localhost:5173
```

The frontend dev server proxies `/query`, `/repos`, `/history` etc. to `localhost:8000` via the Vite config.

---

## Environment variables

| Variable | Required | Description |
|:---|:---|:---|
| `GROQ_API_KEY` | ✅ | Groq API key for LLM inference |
| `JINA_API_KEY` | ✅ | Jina API key for embeddings |
| `USE_JINA_API` | ✅ | Set `true` in production (skips local model download) |
| `SUPABASE_URL` | ✅ | `https://<project>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase `service_role` key (from Project Settings → API) |
| `FRONTEND_URL` | recommended | Your Vercel URL — added to CORS allow-list |
| `LANGCHAIN_API_KEY` | optional | LangSmith tracing |
| `LANGCHAIN_TRACING_V2` | optional | Set `true` to enable tracing |

---

## Deployment

### Backend — Render (free tier)

1. Push to GitHub.
2. Create a new **Web Service** on Render, connected to your repo.
3. Set **Start Command** to:
   ```
   uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Add all environment variables in **Render → Environment**.
5. The `render.yaml` in the repo configures the service blueprint.

> **No persistent disk needed.** Index files are stored in Supabase Storage bucket `kb-indexes` and restored on every startup.

### Frontend — Vercel

1. Import the repo to Vercel.
2. Set **Root Directory** to `frontend`.
3. Add the env var `VITE_API_BASE_URL=https://your-render-url.onrender.com`.
4. Deploy.

---

## API reference

All routes are available at both `/api/v1/<route>` and `/<route>` (legacy, for backward compatibility).

| Method | Route | Description |
|:---|:---|:---|
| `POST` | `/query` | Run the RAG pipeline. Body: `{ query, repos?, conversation_history? }` |
| `GET` | `/history` | Fetch query history from Supabase (newest first) |
| `POST` | `/history/{id}/save` | Toggle bookmark on a history item |
| `DELETE` | `/history/{id}` | Delete one history item |
| `POST` | `/history/bulk-delete` | Delete multiple items by ID list |
| `POST` | `/feedback` | Submit thumbs up/down rating |
| `GET` | `/repos` | List configured repos with chunk counts |
| `POST` | `/repos/add` | Add a repo (triggers clone + ingestion + indexing) |
| `DELETE` | `/repos/{name}` | Remove a repo and its index data |
| `POST` | `/repos/{name}/update` | Re-ingest and re-index a repo |
| `GET` | `/health` | Index status + configured repo names |
| `GET` | `/debug/disk` | Disk usage + local index file existence |
| `GET` | `/debug/storage` | Supabase Storage bucket status + local status |

Interactive API docs: [codeatlas-zyys.onrender.com/docs](https://codeatlas-zyys.onrender.com/docs)

---

## Supported languages

| Language | Chunking strategy |
|:---|:---|
| Python (`.py`) | AST — functions, async functions, class methods |
| JavaScript (`.js`, `.jsx`) | tree-sitter — function declarations, arrow functions, class declarations, React components |
| TypeScript (`.ts`, `.tsx`) | tree-sitter — same as JS |
| Markdown / README | Heading-based section splitting |
| Git commits | One chunk per commit (hash, message, author, date, files) |
| Other languages (`.go`, `.java`, `.rs`, `.cpp`, `.c`, `.h`) | Sliding window fallback |

---

## Known limitations

- **Render free plan cold starts** — the first request after inactivity can take 30–60 seconds while the service wakes up and downloads indexes from Supabase Storage.
- **Jina rate limits** — the free Jina tier has token-per-minute limits. Indexing large repos back-to-back may hit 429 errors (the embedder retries with exponential backoff: 30s, 60s, 120s). Index repos one at a time to avoid this.
- **Groq model availability** — available models depend on your Groq account tier. The active models are configured in `backend/app/core/config.py`.
- **No authentication** — query history is shared across all sessions. This is by design for a personal knowledge base, but not suitable for multi-user production use.

