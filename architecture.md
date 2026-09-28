# Knowledge Base Agent — Architecture

## System Overview

The Knowledge Base Agent is a multi-repo RAG (Retrieval-Augmented Generation) system that lets developers ask questions about their own codebases and receive cited, grounded answers.

**Stack:** FastAPI · LangGraph · Groq LLM · Jina Embeddings · FAISS · BM25 · Supabase (PostgreSQL) · React

**Deployment:** Render (backend) · Vercel (frontend) · Supabase cloud (database)

---

## Request Lifecycle

```
Browser
  │
  ▼ POST /query { query, repos?, conversation_history? }
FastAPI (backend/app/main.py)
  │
  ▼ call
ChatService (services/chat_service.py)
  │  ├── validates: repos configured
  │  ├── invokes: LangGraph pipeline
  │  └── saves: query history → Supabase
  │
  ▼ invoke(initial_state)
LangGraph Graph (agent/graph.py)
  │
  ├──[route_query]──────────────────────────────────────────────┐
  │  LLM classifies → routed_repos, routed_types                │
  │                                                              │
  ├──[retrieve_code]────[retrieve_commits]────[retrieve_readme] │
  │  FAISS+BM25 hybrid   FAISS dense            FAISS dense     │
  │        │                  │                      │           │
  │        └──────────────────┴──────────────────────┘           │
  │                           │                                  │
  ├──[check_ambiguity]                                           │
  │  detects cross-repo conflicts                                │
  │                                                              │
  ├──[synthesize_answer]                                         │
  │  Groq Llama → grounded, cited answer                        │
  │                                                              │
  └──[format_citations]                                          │
     extracts structured citation objects                        │
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

The three retrieval nodes run **in parallel** (LangGraph fan-out). The `AgentState` fields `code_chunks`, `commit_chunks`, and `readme_chunks` are annotated with `operator.add`, so LangGraph merges results from all three branches before calling `check_ambiguity`.

---

## Agent State

```python
class AgentState(TypedDict):
    query: str                    # Input
    routed_repos: list[str]       # Router output
    routed_types: list[str]       # Router output
    code_chunks: Annotated[...]   # Retrieval output (merged from parallel branches)
    commit_chunks: Annotated[...] # Retrieval output
    readme_chunks: Annotated[...] # Retrieval output
    ambiguity_flag: bool          # Ambiguity detection
    ambiguity_detail: str
    conversation_history: list    # Multi-turn memory (session-only)
    final_answer: str             # Output
    citations: list               # Output
```

---

## Retrieval Pipeline

```
RetrievalPipeline (backend/app/retrieval/pipeline.py)
  │
  ├── search_code()
  │     FAISS IndexFlatIP (inner product = cosine on L2-normalized vecs)
  │       ↓ top_k_dense candidates (default: 10)
  │     BM25 hybrid rerank (alpha=0.6 dense, 0.4 BM25)
  │       ↓ top_k_final results (default: 5)
  │
  ├── search_commits()
  │     FAISS dense only → top-5
  │
  └── search_readme()
        FAISS dense only → top-5

Embeddings: Jina v2 base-code (768 dim)
  → API mode (USE_JINA_API=true): Jina REST API (no torch needed)
  → Local mode (USE_JINA_API=false): sentence-transformers (local inference)
```

---

## Tool & Index Architecture

```
data/
├── chunks/
│   ├── code_chunks.jsonl     ← produced by ingestion/
│   ├── commit_chunks.jsonl
│   └── readme_chunks.jsonl
└── indexes/
    ├── code.faiss + .meta    ← produced by indexing/
    ├── commits.faiss + .meta
    ├── readme.faiss + .meta
    └── bm25_code.pkl
```

**Index lifecycle:**
1. `scripts/ingest.py` → reads repos from Supabase → clones/walks → produces JSONL chunks
2. `scripts/build_index.py` → reads JSONL → embeds → writes FAISS + BM25 indexes
3. API startup → `RetrievalPipeline.load()` loads indexes into memory (once, cached)

---

## Database Architecture

```
Supabase PostgreSQL (via HTTPS REST API — no TCP 5432)
  │
  ├── repos          → RepoRepository (database/repositories/repos.py)
  ├── query_history  → HistoryRepository (database/repositories/history.py)
  └── feedback       → FeedbackRepository (database/repositories/feedback.py)

Tables:
  repos           : name, url, last_synced, chunk_count
  query_history   : query, answer, routed_*, citations, latency_ms, ambiguity_*
  feedback        : query, answer_snippet, rating (up|down), routed_repos
```

---

## API Architecture

All routes are thin — they call services, not agent or DB code directly.

```
POST /query                     → chat_service.chat()
GET  /history                   → history_repository.get_recent()
POST /history/{id}/save         → history_repository.toggle_saved()
DELETE /history/{id}            → history_repository.delete()
POST /history/bulk-delete       → history_repository.bulk_delete()
POST /feedback                  → feedback_repository.save()
GET  /health                    → repo_service.get_health()
GET  /debug/disk                → disk diagnostics
GET  /repos                     → repo_service.list_repos()
POST /repos/add                 → repo_service.add_repo()
DELETE /repos/{name}            → repo_service.delete_repo()
POST /repos/{name}/update       → repo_service.update_repo()
```

Versioned routes also available under `/api/v1/` prefix.

---

## Frontend Architecture

```
frontend/src/
├── App.jsx            ← Main component (feature-rich, 1600+ lines)
├── index.css          ← Global styles with CSS custom properties
├── main.jsx           ← React entrypoint
└── services/
    └── api.js         ← Axios instance (baseURL from VITE_API_BASE_URL)
```

**Key frontend features:**
- Chat interface with streaming-style rendering
- Citation popovers with code snippets
- Repository filter chips
- Query history with bookmarks
- Repo management (add/delete/update)
- Thumbs up/down feedback
- Multi-turn conversation with memory

---

## Observability

Structured logging via `backend/app/core/logging.py`:

```
format: {timestamp} {level} [{module}] req={request_id} {key}={value} {message}
```

Key events logged per request:
- `request_started`
- `pipeline_started` / `pipeline_completed`
- `route_query` (repos + types + source)
- `retrieve_code` / `retrieve_commits` / `retrieve_readme` (chunk counts)
- `ambiguity_detected`
- `answer_synthesized`
- `citations_formatted`
- `history_saved`
- `request_completed` (with latency_ms)
