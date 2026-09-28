# Knowledge Base Agent — Architecture

## System Overview

The Knowledge Base Agent (CodeAtlas) is a multi-repo RAG (Retrieval-Augmented Generation) system that lets developers ask natural-language questions about their own codebases and receive cited, grounded answers.

**Stack:** FastAPI · LangGraph · Groq LLM · Jina Embeddings · FAISS · BM25 · Supabase (PostgreSQL + Storage) · React (Vite)

**Deployment:** Render (backend) · Vercel (frontend) · Supabase Cloud (database & object storage)

---

## Request Lifecycle

```
Browser (React Frontend)
  │
  ▼ POST /query { query, repos?, conversation_history? }
FastAPI (backend/app/main.py)
  │
  ▼ call
ChatService (backend/app/services/chat_service.py)
  │  ├── validates: repos configured & valid
  │  ├── invokes: LangGraph workflow graph
  │  └── saves: query record → Supabase database (`query_history`)
  │
  ▼ invoke(initial_state)
LangGraph Workflow Graph (backend/app/agent/graph.py)
  │
  ├──[route_query]──────────────────────────────────────────────┐
  │  Groq LLM classifies → routed_repos, routed_types           │
  │                                                              │
  ├──[retrieve_code]────[retrieve_commits]────[retrieve_readme] │
  │  FAISS + BM25       FAISS dense            FAISS dense     │
  │  hybrid (alpha=0.6) search                 search          │
  │        │                  │                      │           │
  │        └──────────────────┴──────────────────────┘           │
  │                           │                                  │
  ├──[check_ambiguity]                                           │
  │  detects multi-repo architectural conflicts                  │
  │                                                              │
  ├──[synthesize_answer]                                         │
  │  Groq Llama-3.3-70b → grounded answer with inline citations  │
  │                                                              │
  └──[format_citations]                                          │
     extracts structured citation objects with code snippets     │
  │
  ▼ QueryResponse { answer, citations, routing_info, latency_ms }
```

---

## LangGraph Architecture

### Graph Topology

```
START → route_query → retrieve_code ─────┐
                    → retrieve_commits ──→ check_ambiguity → synthesize_answer → format_citations → END
                    → retrieve_readme ───┘
```

### Fan-out / Join

The three retrieval nodes (`retrieve_code`, `retrieve_commits`, `retrieve_readme`) run **in parallel** (LangGraph fan-out). The `AgentState` list fields (`code_chunks`, `commit_chunks`, `readme_chunks`) are annotated with `operator.add`, so LangGraph merges retrieved chunks from all three branches prior to executing `check_ambiguity`.

---

## Agent State

```python
class AgentState(TypedDict):
    query: str                                             # User question
    routed_repos: list[str]                                # Router output
    routed_types: list[str]                                # Router output
    code_chunks: Annotated[list[dict], operator.add]       # Hybrid search results
    commit_chunks: Annotated[list[dict], operator.add]     # Commit dense search results
    readme_chunks: Annotated[list[dict], operator.add]     # Readme dense search results
    ambiguity_flag: bool                                   # Ambiguity flag
    ambiguity_detail: str                                  # Conflict explanation
    conversation_history: list[dict]                       # Session multi-turn memory
    final_answer: str                                      # Generated output
    citations: list[dict]                                  # Structured citations
```

---

## Retrieval Pipeline

```
RetrievalPipeline (backend/app/retrieval/pipeline.py)
  │
  ├── search_code()
  │     FAISS IndexFlatIP (768-dim inner product / cosine similarity)
  │       ↓ top_k_dense candidates (default: 10)
  │     BM25 Okapi reranking (alpha=0.6 dense + 0.4 sparse)
  │       ↓ top_k_final results (default: 5)
  │
  ├── search_commits()
  │     FAISS dense search → top_k (default: 5)
  │
  └── search_readme()
        FAISS dense search → top_k (default: 5)

Embeddings: Jina Embeddings v2 Base Code (768-dimensional)
  → API Mode (USE_JINA_API=true): Jina REST API (lightweight runtime, no GPU/torch dependency)
  → Local Mode (USE_JINA_API=false): sentence-transformers / PyTorch
```

---

## Storage & Index Persistence Architecture

To support free cloud hosting (e.g., Render free tier without persistent disk), FAISS vector indices and BM25 models are automatically backed up to and synchronized from **Supabase Storage** (`kb-indexes` bucket).

```
Local Data Directory (data/):
├── processed/
│   ├── code_chunks.jsonl        ← Ingested AST chunks
│   ├── commit_chunks.jsonl      ← Ingested git commit messages
│   └── readme_chunks.jsonl      ← Ingested doc chunks
└── indexes/
    ├── faiss/
    │   ├── code.faiss + .meta   ← FAISS index for code
    │   ├── commits.faiss + .meta← FAISS index for git commits
    │   └── readme.faiss + .meta ← FAISS index for documentation
    └── bm25/
        └── bm25_code.pkl        ← BM25 sparse index

Supabase Storage Sync (backend/app/database/storage.py):
  ├── On Startup: index_storage.download_all() downloads files if local disk is empty
  └── Post Indexing / Repo Add: index_storage.upload_all() persists index artifacts to cloud
```

---

## Database Schema (Supabase PostgreSQL)

Access is performed via Supabase HTTP REST API (`supabase-py` SDK):

```
Tables:
  1. repos
     - id (UUID), name (TEXT UNIQUE), url (TEXT), status (TEXT),
       chunk_count (INT), file_count (INT), commit_count (INT),
       last_synced (TIMESTAMPTZ), created_at (TIMESTAMPTZ)

  2. query_history
     - id (UUID), query (TEXT), answer (TEXT),
       routed_repos (JSONB), routed_types (JSONB),
       citations (JSONB), ambiguity_flag (BOOL), ambiguity_detail (TEXT),
       latency_ms (INT), is_saved (BOOL), created_at (TIMESTAMPTZ)

  3. feedback
     - id (UUID), query (TEXT), rating (TEXT: 'up' | 'down'),
       answer_snippet (TEXT), routed_repos (JSONB), created_at (TIMESTAMPTZ)
```

---

## API Architecture

FastAPI backend providing REST endpoints under root `/` and `/api/v1/`:

```
POST   /query                     → ChatService (executes LangGraph agent)
GET    /history                   → HistoryRepository (list recent queries)
POST   /history/{id}/save         → HistoryRepository (toggle bookmark/saved)
DELETE /history/{id}            → HistoryRepository (delete single entry)
POST   /history/bulk-delete       → HistoryRepository (bulk clear history)
POST   /feedback                  → FeedbackRepository (record user rating)
GET    /health                    → RepoService (healthcheck & statistics)
GET    /debug/disk                → Index & disk diagnostic status
GET    /repos                     → RepoService (list registered repositories)
POST   /repos/add                 → RepoService (clone, ingest & re-index repository)
DELETE /repos/{name}            → RepoService (delete repository & rebuild index)
POST   /repos/{name}/update       → RepoService (pull latest commits & re-index)
```

---

## Frontend Architecture

```
frontend/src/
├── App.jsx            ← React SPA (Chat UI, Repo Manager, History Sidebar, Filters)
├── main.jsx           ← Entry point
├── index.css          ← Dark UI design system (CSS variables, glassmorphism, animations)
└── services/
    └── api.js         ← Axios instance (configured via VITE_API_BASE_URL)
```

**Key Frontend Capabilities:**
- Chat interface with inline citations & code expandable details
- Interactive Repository Filter Chips (all vs specific repos)
- Repository Management Modal (Add GitHub Repo, Sync, Delete)
- Query History drawer with search, filter by saved, and bulk delete
- Helpful suggested starter questions per repository
- Micro-interactions, animated states, and responsive dark theme

---

## Observability & Logging

Structured logging via `backend/app/core/logging.py`:

```
Format: {timestamp} [{level}] [{module}] req={request_id} {key}={value} {message}
```

Key lifecycle events logged per request:
- `request_started`
- `route_query` (classified repos and node types)
- `retrieve_code` / `retrieve_commits` / `retrieve_readme` (chunk counts & latency)
- `ambiguity_detected` (cross-repo architectural conflict details)
- `answer_synthesized` (LLM token generation details)
- `citations_formatted` (extracted source references)
- `request_completed` (total latency in ms)
