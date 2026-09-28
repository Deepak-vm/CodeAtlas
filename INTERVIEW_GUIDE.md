# CodeAtlas — Complete Technical Interview Preparation Guide

---

## 1. Elevator Pitch (30 Seconds)

> **"I built CodeAtlas — a multi-agent RAG system that lets you ask natural-language questions about your own GitHub repositories and get back cited answers pointing to exact file names and line numbers.**
>
> **The problem:** Developers managing multiple projects struggle with "codebase amnesia" — forgetting where specific things were implemented. Grep requires knowing what to search for; GitHub search is too broad.
>
> **The solution:** CodeAtlas indexes every repo's source code, git commit history, and README documentation into a hybrid vector+keyword search engine. A LangGraph pipeline classifies your question, retrieves the right chunks from the right repos, detects if the same concept appears differently across repos, and synthesises a grounded answer with `repo/file:line` citations using the Groq LLM.
>
> **Stack:** Python · FastAPI · LangGraph · FAISS · BM25 · Jina Embeddings API · Groq LLM · React + Vite · Supabase."

---

## 2. Architecture Overview

### System diagram

```
Browser (React/Vite — Vercel)
    │
    └── POST /query ──────────────────────────────────────────────────┐
                                                                       │
FastAPI (Render free tier)                                             │
    │                                                                  │
    └── ChatService.chat()                                             │
          │                                                            │
          └── LangGraph StateGraph ─────────────────────────────────► │
                │                                                      │
                ├─ route_query         ← Groq LLM: classify repos      │
                │                        + content types               │
                │                                                      │
                ├─ retrieve_code   ─┐                                  │
                ├─ retrieve_commits ─┼── 3 parallel fan-out branches   │
                └─ retrieve_readme ─┘                                  │
                        │                                              │
                        ▼                                              │
                 check_ambiguity    ← cross-repo conflict detection    │
                        │                                              │
                        ▼                                              │
                 synthesize_answer  ← Groq LLM: grounded cited answer  │
                        │                                              │
                        ▼                                              │
                 format_citations   ← regex parse + chunk lookup       │
                        │                                              │
                        └──────────────────────────────────────────── ┘

Supabase PostgreSQL — repos, query_history, feedback tables
Supabase Storage    — kb-indexes bucket (FAISS + BM25 + JSONL)
```

### Data flow summary

| Phase | Directory | What happens |
|:---|:---|:---|
| **Ingestion** | `backend/app/ingestion/` | Clone repo → AST chunk code → GitPython commits → Markdown sections → JSONL |
| **Indexing** | `backend/app/indexing/` | Jina API embeddings → FAISS + BM25 → upload to Supabase Storage |
| **Startup** | `backend/app/main.py` | Download indexes from Supabase Storage to local disk |
| **Query** | `backend/app/agent/` | LangGraph pipeline → Groq synthesis → citations |
| **UI** | `frontend/src/` | React SPA → POST `/query` → render Markdown + citation popovers |

---

## 3. Full Step-by-Step Flow

### Adding a repository (offline / on-demand)

When a user clicks **Add** or **Sync** in the UI, `RepoService` orchestrates these steps:

**1. Clone**
```python
# backend/app/services/repo_service.py
git clone --depth 500 <url> backend/data/raw/repos/<name>/
```

**2. Ingestion — `ingest_and_write()` in `backend/app/ingestion/pipeline.py`**

Calls three parallel loaders:

- **Code** — `collect_code_files()` walks the repo, skipping `node_modules`, `.git`, `venv`, `__pycache__`, `dist`, `build`, `.next`, `coverage` etc. (defined in `settings.skip_dirs`). Supported extensions: `.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, `.java`, `.rs`, `.cpp`, `.c`, `.h`.

- **Python chunking** (`backend/app/ingestion/chunkers/python_chunker.py`):
  1. `ast.parse(source)` — AST-based
  2. `_ChunkVisitor` walks `FunctionDef`, `AsyncFunctionDef`, `ClassDef` at top level
  3. For `ClassDef`: emits the whole class AND each method individually
  4. Each chunk gets a header `# file_path\n# symbol: name\n# docstring: ...` prepended to improve embedding signal
  5. Fallback (no symbols found): sliding window of 50 lines, 10-line overlap

- **JS/TS chunking** (`backend/app/ingestion/chunkers/javascript.py`):
  1. tree-sitter AST — extracts `function_declaration`, `arrow_function`, `class_declaration`, `method_definition`, `lexical_declaration`
  2. Regex fallback if tree-sitter fails
  3. Last resort: 60-line sliding window

- **Commit history** (`backend/app/ingestion/loaders/git.py`):
  - `git.Repo(...).iter_commits(all=True)` — all branches
  - Skips merge commits (more than one parent)
  - Caps at `max_commit_history = 500` per repo
  - Each commit → one chunk: hash, author, date, message, changed files list

- **README / docs** (`backend/app/ingestion/parsers/markdown.py`):
  - Splits by Markdown headings (`#`, `##`, `###`)
  - Each section = one chunk
  - Heading text becomes `symbol_name`

All chunks append to three JSONL files:
```
backend/data/processed/
  code_chunks.jsonl
  commit_chunks.jsonl
  readme_chunks.jsonl
```

**Canonical chunk schema:**
```json
{
  "id": "uuid4",
  "chunk_type": "code",
  "repo": "SketchXPad",
  "file_path": "src/hooks/useDrawingSocket.jsx",
  "content": "# src/hooks/useDrawingSocket.jsx\n# symbol: useDrawingSocket\n\nconst useDrawingSocket = ...",
  "symbol_name": "useDrawingSocket",
  "language": "javascript",
  "start_line": 12,
  "end_line": 45,
  "commit_hash": null,
  "commit_message": null,
  "commit_date": null,
  "changed_files": []
}
```

**3. Indexing — `build_all_indexes()` in `backend/app/indexing/pipeline.py`**

- Reads all JSONL files
- **Embedder** (`backend/app/indexing/vector/embedder.py`):
  - Production: Jina Embeddings API (`jina-embeddings-v2-base-code`, 768-dim)
  - Local dev: optional sentence-transformers local model
  - Batches of 64, L2-normalized → cosine similarity = inner product
  - 429 rate-limit: exponential backoff — 30s, 60s, 120s
  - 1-second inter-batch delay to avoid hitting rate limits
- **FAISS** (`backend/app/indexing/vector/faiss.py`): `IndexFlatIP(768)` — exact brute-force, no approximation
- **BM25** (`backend/app/indexing/keyword/bm25.py`): `BM25Okapi` with camelCase + snake_case tokenization. Symbol names are repeated 3× in the corpus for upweighting.
- Saves to `backend/data/indexes/faiss/*.faiss`, `indexes/bm25/*.pkl`

**4. Supabase Storage upload — `index_storage.upload_all()`**

After indexing completes, all index + JSONL files are uploaded to the `kb-indexes` Supabase Storage bucket. This is how indexes persist across Render restarts (free tier has no persistent disk).

---

### Query flow (every request)

**Frontend → Backend**

`App.jsx → handleQuery()` sends:
```json
{
  "query": "Where have I implemented WebSocket real-time features?",
  "repos": ["SketchXPad"],
  "conversation_history": [{"query": "...", "answer": "..."}]
}
```

- `repos` is only included if the user selected filter chips
- `conversation_history` includes the last 3 session turns

**FastAPI route — `POST /query`**

`backend/app/api/routes/chat.py → query_endpoint()`:
1. Validates `QueryRequest` (Pydantic, 3–1000 chars)
2. Guards: no repos configured → HTTP 400
3. Delegates to `chat_service.chat(req)`

**ChatService builds `AgentState`:**
```python
initial_state = {
    "query": "Where have I implemented WebSocket real-time features?",
    "routed_repos": ["SketchXPad"],  # from req.repos
    "routed_types": [],
    "code_chunks": [],
    "commit_chunks": [],
    "readme_chunks": [],
    "ambiguity_flag": False,
    "ambiguity_detail": "",
    "conversation_history": [...],
    "final_answer": "",
    "citations": [],
}
```

**Node 1 — `route_query` (`backend/app/agent/nodes/router.py`)**

Repo names are loaded from **Supabase** (`repo_repository.get_all()`), not a local file. This is critical for production — the local `repos.json` doesn't exist on Render.

- If `routed_repos` is already set (user filter), only asks LLM for `routed_types`
- Otherwise, Groq LLM receives a few-shot JSON prompt and returns both
- Fallback on parse error: all repos, all types

```python
# System prompt (ROUTER_SYSTEM in backend/app/agent/prompts/router.py)
# Rules:
# 1. "where/how/show/find" → code + readme
# 2. "when/why/who changed/history" → commits
# 3. vague/cross-repo → include all
# 4. ALWAYS return valid JSON: {routed_repos: [...], routed_types: [...]}
```

**Nodes 2–4 — Parallel retrieval (fan-out)**

LangGraph fires all three nodes simultaneously. Each writes to a separate `Annotated[list, operator.add]` field — LangGraph merges the lists when all three complete.

`retrieve_code` (`backend/app/agent/nodes/retrieve.py`):
1. Skips if `"code" not in routed_types`
2. `Embedder.get().encode_query(query)` → 768-dim vector
3. `FaissStore.search(q_vec, top_k=10, repo_filter=routed_repos)` — internally over-fetches 30 candidates then filters
4. **Hybrid rerank** (`RetrievalPipeline._hybrid_rerank`):
   - BM25 scores for the FAISS candidate set
   - Normalize both to [0,1]
   - `score = 0.6 × dense + 0.4 × bm25`
   - Return top-5

`retrieve_commits`: FAISS dense only, no BM25, top-5
`retrieve_readme`: FAISS dense only, no BM25, top-5

**Node 5 — `check_ambiguity` (`backend/app/agent/nodes/ambiguity.py`)**

1. `Counter(c["repo"] for c in code_chunks)` — count repos in results
2. If ≥2 repos in top-6 chunks → `ambiguity_flag = True`
3. Builds human-readable `ambiguity_detail`: "• SketchXPad: wss, httpServer\n• CodeAtlas: STARTER_QUERIES"

**Node 6 — `synthesize_answer` (`backend/app/agent/nodes/synthesize.py`)**

Formats all chunks into a structured context block:
```
=== CODE CHUNKS ===
[1] SketchXPad/src/hooks/useDrawingSocket.jsx:12-45 | symbol: useDrawingSocket
```code
const useDrawingSocket = (roomId) => { ...
```

=== COMMIT HISTORY ===
• [SketchXPad] a1b2c3d4 (2024-03-15): feat: add WebSocket reconnection logic

=== DOCUMENTATION ===
[doc: WebSocket Architecture @ SketchXPad/README.md]
The canvas uses a WebSocket server...
```

- Normal mode: system prompt instructs explicit `[repo/file:line]` citations
- Ambiguity mode: compare-and-contrast with recommendation
- Conversation history: last 3 turns injected as `=== PRIOR CONVERSATION ===`
- Groq: `temperature=0.0`, `max_tokens=2048`
- If context is empty → polite fallback, no LLM call

**Node 7 — `format_citations` (`backend/app/agent/nodes/citations.py`)**

1. Regex `[repo/file:start-end]` scans the answer text
2. Looks up matching chunk via `(repo, file_path, start_line)` dict
3. Step 2: all retrieved chunks are also included as supporting citations
4. De-duplicates by `repo::file_path::start_line`

**Response persisted to Supabase:**

`ChatService` saves to `query_history` table (best-effort, never fails the request). Includes: query, answer, routed_repos, routed_types, citations JSON, latency_ms, ambiguity flag.

---

## 4. Key Design Decisions

### Why LangGraph instead of a simple pipeline?

LangGraph's `StateGraph` gives you:
1. **Typed shared state** — `AgentState` TypedDict is the single source of truth. All nodes read from and write back to it.
2. **Parallel fan-out** — three retrieval nodes run simultaneously. The `Annotated[list, operator.add]` annotation tells LangGraph to merge the lists when all branches complete — no manual threading needed.
3. **Explicit topology** — the graph is declared once (`graph.py`) and is fully inspectable/visualisable.

### Why FAISS + BM25 hybrid for code?

**FAISS (dense)** excels at semantic similarity — it finds code that *does the same thing* even with different variable names.

**BM25 (sparse)** excels at exact token matching — it reliably retrieves code that contains the *exact function name or identifier* you asked about.

Combining them (`0.6 × dense + 0.4 × BM25`) handles both "find code that retries on failure" (semantic) and "find `useDrawingSocket`" (keyword) queries.

Commits and docs use dense-only because commit messages and documentation are prose — keyword matching is less precise there.

### Why Jina Embeddings API?

`jina-embeddings-v2-base-code` is trained specifically on code and supports a 8192-token context window. It's free up to 1M tokens/month. Using the API means no `torch` or `sentence-transformers` on Render (free tier has very limited memory). The `USE_JINA_API=true` environment variable switches the embedder from the local model to the HTTP API.

### Why Supabase Storage for index persistence?

Render free plan has no persistent disk. FAISS binary files and BM25 pickle files are written to the ephemeral local filesystem — wiped on every restart. Uploading to Supabase Storage after every indexing run and downloading on every startup gives "pseudo-persistence" with zero additional cost.

### Why per-chunk headers?

The Python chunker prepends:
```python
header = "# file_path\n# class: ClassName\n# symbol: method_name\n# docstring: ...\n\n"
```

This means the embedding for a chunk contains both the symbol name and its code. BM25 also sees the symbol name in the document. This dramatically improves retrieval when someone asks "how does `verify_token` work?" — the exact symbol name is in the chunk text and BM25 scores it highly.

### Why flat FAISS (`IndexFlatIP`) instead of `IndexIVFPQ`?

The total number of indexed vectors across all repos is typically 5,000–50,000. At this scale, brute-force `IndexFlatIP` is fast enough (< 5ms search time) and has **zero approximation error**. IVFPQ saves memory/speed at the cost of recall — only worth it for millions of vectors.

### Why `temperature=0.0` for synthesis?

Grounded citation generation requires determinism. At temperature 0, the model picks the most probable token at every step. This means the `[repo/file:line]` format is followed consistently rather than being paraphrased or forgotten mid-answer.

---

## 5. Complete API Reference

### POST `/query`
Run the full RAG pipeline.

Request body:
```json
{
  "query": "Where is the retry logic implemented?",
  "repos": ["CodeAtlas"],
  "conversation_history": [
    {"query": "What does this project do?", "answer": "It is a RAG system..."}
  ]
}
```

Response:
```json
{
  "answer": "## Retry Logic\n\nThe retry logic is in `[CodeAtlas/backend/app/indexing/vector/embedder.py:110-130]`...",
  "citations": [
    {
      "repo": "CodeAtlas",
      "file_path": "backend/app/indexing/vector/embedder.py",
      "start_line": 110,
      "end_line": 130,
      "symbol_name": "_encode_api",
      "commit_hash": null,
      "language": "python",
      "snippet": "for attempt in range(JINA_RETRY_MAX):\n    try:\n        resp = requests.post(...)",
      "chunk_type": "code"
    }
  ],
  "ambiguity_flag": false,
  "ambiguity_detail": "",
  "latency_ms": 4832.1,
  "routed_repos": ["CodeAtlas"],
  "routed_types": ["code", "readme"]
}
```

### GET `/repos`
Returns registered repos with chunk counts.

```json
{
  "repos": ["CodeAtlas", "SketchXPad"],
  "repos_detail": [
    {"name": "CodeAtlas", "url": "https://github.com/...", "chunk_count": 499},
    {"name": "SketchXPad", "url": "https://github.com/...", "chunk_count": 127}
  ],
  "count": 2
}
```

### POST `/repos/add`
```json
{"name": "MyRepo", "url": "https://github.com/user/MyRepo"}
```
Triggers: clone → ingest → index → upload to Supabase Storage.

### POST `/repos/{name}/update`
Re-ingests and re-indexes a single repo. Removes old data first.

### GET `/debug/storage`
Diagnostic: shows what's in the `kb-indexes` Supabase Storage bucket vs local disk.

### GET `/health`
```json
{
  "status": "ok",
  "indexes_loaded": {"code": true, "commits": true, "readme": true, "bm25_code": true},
  "repos_configured": ["CodeAtlas", "SketchXPad"]
}
```

---

## 6. Data Models

### AgentState TypedDict (`backend/app/agent/state.py`)

```python
class AgentState(TypedDict):
    query: str
    routed_repos: list[str]      # subset of repo names
    routed_types: list[str]      # ["code", "commits", "readme"]
    code_chunks:   Annotated[list[dict], operator.add]   # merged across parallel branches
    commit_chunks: Annotated[list[dict], operator.add]
    readme_chunks: Annotated[list[dict], operator.add]
    ambiguity_flag: bool
    ambiguity_detail: str
    conversation_history: list[dict]   # [{query, answer}, ...] — session only
    final_answer: str
    citations: list[dict]
```

The `Annotated[list, operator.add]` is the key to LangGraph fan-out/join: each parallel retrieval node returns `{"code_chunks": [...]}` and LangGraph concatenates them automatically.

### QueryRequest (`backend/app/schemas/chat.py`)
```python
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)
    repos: list[str] | None = None
    conversation_history: list[ConversationTurn] | None = None
```

### Supabase tables

**repos**
| Column | Type | Notes |
|:---|:---|:---|
| id | bigint | auto PK |
| name | text unique | repo identifier |
| url | text | GitHub URL |
| last_synced | text | ISO timestamp |
| chunk_count | int | total chunks |
| created_at | timestamptz | |

**query_history**
| Column | Type | Notes |
|:---|:---|:---|
| id | bigint | auto PK |
| query | text | user's question |
| answer | text | LLM response |
| routed_repos | text[] | repos searched |
| routed_types | text[] | content types |
| citations | jsonb | citation list |
| latency_ms | float | end-to-end |
| ambiguity_flag | boolean | |
| ambiguity_detail | text | |
| saved | boolean | bookmarked |
| created_at | timestamptz | |

---

## 7. Frontend Architecture

**`App.jsx`** — 1600-line single-file React SPA. Key state:

| State | Type | Purpose |
|:---|:---|:---|
| `selectedRepos` | `string[]` | UI filter chips → sent as `repos` in request |
| `conversationHistory` | `object[]` | Session-only multi-turn memory |
| `history` | `object[]` | Fetched from Supabase via `/history` |
| `result` | `object` | Last `QueryResponse` from the API |
| `reposList` | `object[]` | Repos from `/repos` with chunk counts |
| `backendAvailable` | `bool\|null` | Backend health check state |

**Repo filter logic** — when the user clicks a repo chip:
```javascript
const toggleRepoFilter = (repoName) => {
  setSelectedRepos(prev =>
    prev.includes(repoName) ? prev.filter(r => r !== repoName) : [...prev, repoName]
  )
}
```
The selected repos are included in `payload.repos` and flow through to the LangGraph `routed_repos` initial state.

**Citation popovers** — `CitationPopover` renders a clickable numbered badge. On click, shows file path, line range, and code snippet in a floating card.

**Color stability** — `getRepoStyle(name)` uses a djb2 hash of the repo name to pick from `EXTENDED_PALETTE`. The same repo always gets the same color, even across page reloads.

**History** — fetched from Supabase via `GET /history` on mount. Supports search, saved filter, bulk delete, and per-item bookmark toggle (persisted via `POST /history/{id}/save`).

---

## 8. Configuration Reference

All settings live in `backend/app/core/config.py`. Key values:

| Setting | Default | Notes |
|:---|:---|:---|
| `embedding_model` | `jina-embeddings-v2-base-code` | 768-dim |
| `embedding_dim` | 768 | must match FAISS index dim |
| `groq_model_primary` | `openai/gpt-oss-120b` | router + synthesizer |
| `groq_temperature` | 0.0 | deterministic |
| `groq_max_tokens` | 2048 | answer length cap |
| `max_commit_history` | 500 | commits per repo |
| `top_k_dense` | 10 | FAISS candidates |
| `top_k_final` | 5 | after hybrid rerank |
| `ambiguity_min_repos` | 2 | threshold for compare mode |
| `python_fallback_chunk_lines` | 50 | sliding window size |
| `js_fallback_chunk_lines` | 60 | sliding window size |

---

## 9. Persistence Architecture

```
Render ephemeral disk
  backend/data/
    raw/repos/<name>/          ← cloned repos (re-cloned if missing)
    processed/*.jsonl          ← chunk files (restored from storage)
    indexes/faiss/*.faiss      ← FAISS indexes (restored from storage)
    indexes/bm25/*.pkl         ← BM25 indexes (restored from storage)

Supabase Storage bucket: kb-indexes
  faiss/code.faiss
  faiss/code.faiss.meta
  faiss/commits.faiss
  faiss/commits.faiss.meta
  faiss/readme.faiss
  faiss/readme.faiss.meta
  bm25/bm25_code.pkl
  chunks/code_chunks.jsonl
  chunks/commit_chunks.jsonl
  chunks/readme_chunks.jsonl

Supabase PostgreSQL
  repos              ← repo registry
  query_history      ← all queries + answers
  feedback           ← thumbs ratings
```

**Startup flow** (`backend/app/main.py → startup_event`):
1. `index_storage.download_all()` — download all files from `kb-indexes` bucket
2. `retrieval_pipeline = RetrievalPipeline.load()` — load FAISS + BM25 into memory
3. Server begins accepting requests

**After indexing** (`repo_service.py`):
1. `build_all_indexes()` — build FAISS + BM25 on local disk
2. `index_storage.upload_all()` — upload to Supabase Storage

---

## 10. Exception Hierarchy

```python
KnowledgeAgentError (base)
├── ConfigurationError         ← missing env var
├── AgentError                 ← LangGraph pipeline failure
│   ├── RouterError            ← intent classification failed
│   └── SynthesisError         ← LLM generation failed
├── RetrievalError             ← index query failed
│   └── IndexNotFoundError     ← FAISS/BM25 file missing
├── DatabaseError              ← Supabase operation failed
│   └── RepositoryNotFoundError← repo not in Supabase
├── ValidationError            ← business validation failed
│   └── NoReposConfiguredError ← no repos indexed yet
└── IngestionError             ← clone/index subprocess failed
    └── RepoDuplicateError     ← repo already registered
```

All exceptions have `http_status` and `error_code` for clean JSON error responses.

---

## 11. Common Interview Questions

### Q: What is RAG and why did you use it?

RAG (Retrieval-Augmented Generation) combines a retrieval system with an LLM. Instead of relying on the LLM's training data (which doesn't include your private repos), you first retrieve relevant documents from an index and pass them as context. The LLM then generates an answer grounded in those documents rather than hallucinating. This is the right architecture here because the repos change frequently and are private — you can't fine-tune the LLM on them.

### Q: How does the hybrid retrieval work?

Code search uses two signals:
1. **FAISS dense search** — encodes the query into a 768-dim vector with Jina Code Embeddings and finds the most semantically similar code chunks using inner-product similarity.
2. **BM25 keyword search** — scores the FAISS candidate set using term frequency. Good at exact identifier matching (`useDrawingSocket`, `retry_with_backoff`).

The final score is `0.6 × dense + 0.4 × BM25`. FAISS has higher weight because semantic understanding is more general.

### Q: How does LangGraph's fan-out/join work?

LangGraph's `StateGraph` allows adding multiple edges from one node to several others. All nodes with an incoming edge from the same source run in parallel. The join is handled by the `Annotated[list, operator.add]` type annotation on the state fields — when `retrieve_code`, `retrieve_commits`, and `retrieve_readme` all write `{"code_chunks": [...]}` etc., LangGraph concatenates the lists via `operator.add` and produces the merged state before passing it to `check_ambiguity`.

### Q: How does the cross-repo ambiguity detection work?

After retrieval, `check_ambiguity` counts how many distinct repos appear in the top code chunks. If ≥2 repos are present in the top 6 results, it sets `ambiguity_flag=True` and builds a detail string listing which symbols came from which repos. The synthesizer then uses a compare-and-contrast prompt instead of the normal one.

### Q: How do indexes persist on Render free tier?

Render free tier has no persistent disk — the filesystem is wiped on every restart/deploy. To solve this, after every indexing run, `IndexStorage.upload_all()` uploads all FAISS, BM25, and JSONL files to a Supabase Storage bucket (`kb-indexes`). On every startup, `IndexStorage.download_all()` fetches them back to the local ephemeral disk before the server starts accepting requests.

### Q: How does the repo filter reach the retrieval layer?

1. User selects repo chips in the UI → `selectedRepos` state
2. Frontend sends `{"repos": ["SketchXPad"]}` in the POST body
3. `ChatService` puts it into `initial_state["routed_repos"]`
4. `route_query` node sees `already_filtered_repos = ["SketchXPad"]`, validates against Supabase repo list, and returns those repos unchanged (only asks LLM for `routed_types`)
5. `retrieve_code/commits/readme` nodes receive `repo_filter=["SketchXPad"]` and pass it to `FaissStore.search()`, which filters results client-side after FAISS retrieval

A bug existed previously where `_load_repo_names()` read from a local `repos.json` that doesn't exist on Render, causing `available_repos=[]` and making user filters silently ignored. This was fixed to read from Supabase.

### Q: Why tree-sitter for JS/TS chunking?

JavaScript functions can be expressed many ways: `function foo(){}`, `const foo = () => {}`, `class Foo { bar(){} }`, React components as arrow functions, etc. Regex cannot reliably handle all cases. tree-sitter builds a proper AST and lets you query for specific node types (`function_declaration`, `arrow_function`, `method_definition`). The fallback regex handles the most common patterns if tree-sitter is unavailable.

### Q: How does multi-turn conversation work?

The session `conversationHistory` array in React state stores `{query, answer}` pairs. When submitting a new query, the last 3 turns are sent in the request. `ChatService` puts them in `initial_state["conversation_history"]`. The synthesizer node injects them into the prompt as a `=== PRIOR CONVERSATION ===` block so the LLM can resolve references like "what about the one in the other file?". This is **session-only** — not persisted to Supabase.

### Q: What does `temperature=0.0` do?

At temperature 0, the model always picks the highest-probability token (greedy decoding). This makes outputs deterministic and structured — the `[repo/file:line]` citation format is followed consistently. Higher temperatures introduce randomness which could cause the LLM to paraphrase the citation format or forget it entirely.

---

## 12. Known Limitations and Trade-offs

| Limitation | Why | Trade-off |
|:---|:---|:---|
| Render cold starts (30–60s) | Free tier spins down after 15 min inactivity | Accepted — free hosting |
| Jina 429 rate limits | Free tier token budget | Exponential backoff mitigates; index one repo at a time |
| No authentication | Query history is shared | Designed for personal use; not multi-tenant |
| Brute-force FAISS | `IndexFlatIP` is O(N) | Fine for 50K vectors; switch to `IndexIVFPQ` at 1M+ |
| No streaming | Full answer returned at once | Could add SSE streaming; not prioritized |
| Python + JS only (AST) | AST chunkers cover `.py`, `.js`, `.jsx`, `.ts`, `.tsx` | Other languages fall back to sliding window |
