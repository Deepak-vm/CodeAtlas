# CodeAtlas — Personal Codebase Knowledge Agent
## Complete Technical Interview Preparation Guide

> Generated from actual codebase analysis. Every section is grounded in the real source code.

---

# 1. Elevator Pitch (30 Seconds)

**"I built CodeAtlas — a multi-agent RAG system that lets you ask natural language questions about your own GitHub repositories and get back precise, cited answers pointing to exact file names and line numbers.**

**The problem:** As a developer managing multiple projects, it's hard to remember where you implemented specific things — "where did I handle authentication?", "which repo has my retry logic?", "when did I add WebSocket support?" You end up grep-ping through repos or wasting time searching Git history.

**The solution:** CodeAtlas indexes all your repos — source code, git commit history, and README docs — into a hybrid vector+keyword search engine. You ask a question; a LangGraph multi-agent pipeline classifies your intent, retrieves the right code chunks from the right repos, detects if the same concept is implemented differently across repos (ambiguity), and synthesizes a grounded explanation with exact `[repo/file:line]` citations.

**Users:** Individual developers and engineering teams who work across multiple codebases.

**Technology:** Python · LangGraph · FastAPI · FAISS · BM25 · Jina Code Embeddings · Groq Llama 3.3 70B · React + Vite.

**Impact:** 89% repo-hit rate · 100% answer quality · ~11 second end-to-end latency on a 20-question benchmark suite."**

---

# 2. Project Overview

## Why This Project Exists

Developers experience "codebase amnesia" — working across multiple repositories over months, it becomes genuinely difficult to recall which repo or file contains a specific implementation. Traditional tools force you to:
- Write exact grep patterns (you need to know what to search for)
- Manually browse GitHub
- Re-read unfamiliar code cold

CodeAtlas acts as a **"GitHub Copilot for your own history"** — it understands intent, not just keywords.

## Who Uses It

- Solo developers with 2–5+ active repositories
- Teams onboarding new members who need to navigate an unfamiliar codebase
- Engineers doing code reviews who need to find prior implementations

## How Users Interact

1. **Web UI:** Open `http://localhost:5173`. Type `"Where have I implemented WebSocket features?"` and receive a cited, Markdown-formatted answer with inline code snippets within ~11 seconds.
2. **CLI:** `python -m agents.graph "where is my retry logic?"` outputs a Rich-formatted answer directly in the terminal.
3. **REST API:** POST `/query` — integrate into any tool or CI pipeline.

## Major Features

1. AST-aware code chunking (Python `ast` module + Tree-sitter for JS/TS)
2. Three independent vector indexes: code, git commits, README/docs
3. Hybrid dense + sparse retrieval (FAISS + BM25 with linear interpolation)
4. Cross-repo ambiguity detection — compare-and-contrast mode when the same concept appears differently in multiple repos
5. Groq Llama 3.3 70B synthesis with strict grounded citations (`[repo/file:line]`)
6. Session multi-turn conversation memory
7. Query history with bookmarking, search, and bulk operations
8. Single-repo isolated updates — pull and re-embed one repo without rebuilding the full index
9. LangSmith tracing integration for monitoring the agent graph
10. 20-question evaluation suite with automated metrics

## Business Value

- Reduces "context-switching overhead" — answering questions in seconds instead of minutes
- Scales linearly with the number of repos indexed
- Zero vendor lock-in on vector storage (FAISS is local, fully offline after setup)

---

# 3. Complete Architecture

## High-Level System Diagram

```mermaid
graph TD
    User["👤 User (Browser / CLI)"]
    Frontend["React 18 + Vite\n(Port 5173)"]
    Backend["FastAPI\n(Port 8000)"]
    Router["route_query Node\nGroq Llama 3.3 70B\n• Classify repo subset\n• Classify content types"]
    CodeRet["retrieve_code Node\nFAISS + BM25 Hybrid\ncode.faiss + bm25_code.pkl"]
    CommitRet["retrieve_commits Node\nFAISS Dense\ncommits.faiss"]
    ReadmeRet["retrieve_readme Node\nFAISS Dense\nreadme.faiss"]
    Ambiguity["check_ambiguity Node\nCross-repo conflict detection"]
    Synth["synthesize_answer Node\nGroq Llama 3.3 70B\nGrounded answer + citations"]
    CitFmt["format_citations Node\nStructured citation list\n(chunk metadata lookup)"]
    FAISS["FAISS Indexes\ndata/indexes/\n• code.faiss\n• commits.faiss\n• readme.faiss"]
    BM25["BM25 Index\nbm25_code.pkl"]
    Jina["Jina Code Embeddings\njina-embeddings-v2-base-code\n768-dim local model"]
    Groq["Groq Cloud API\nLlama 3.3 70B\n(Router + Synthesizer)"]
    LangSmith["LangSmith\n(Optional tracing)"]

    User -->|HTTP / CLI| Frontend
    Frontend -->|POST /query| Backend
    Backend --> Router
    Router -->|Fan-out| CodeRet
    Router -->|Fan-out| CommitRet
    Router -->|Fan-out| ReadmeRet
    CodeRet --> Ambiguity
    CommitRet --> Ambiguity
    ReadmeRet --> Ambiguity
    Ambiguity --> Synth
    Synth --> CitFmt
    CitFmt -->|citations + answer| Backend
    Backend -->|QueryResponse JSON| Frontend

    CodeRet <-->|search| FAISS
    CommitRet <-->|search| FAISS
    ReadmeRet <-->|search| FAISS
    CodeRet <-->|re-rank| BM25
    FAISS <-->|encode_query| Jina
    Router -->|invoke| Groq
    Synth -->|invoke| Groq
    Backend -.->|traces| LangSmith
```

## Ingestion Pipeline (Offline / One-time)

```mermaid
graph LR
    repos["repos.json\n(GitHub URLs or local paths)"]
    walker["repo_walker.py\nRecursive file walk\nSkips: node_modules, .git,\nvenv, eval/, migrations/"]
    py["python_chunker.py\nast.parse() → FunctionDef\nAsyncFunctionDef, ClassDef\n+ method sub-chunks"]
    js["js_chunker.py\ntree-sitter AST\n(regex fallback)"]
    commit["commit_ingester.py\nGitPython log --all\nMax 500 commits/repo"]
    readme["readme_ingester.py\nMarkdown heading splits\n## / ### sections"]
    jsonl["JSONL Chunk Files\ndata/chunks/\n• code_chunks.jsonl\n• commit_chunks.jsonl\n• readme_chunks.jsonl"]
    embed["embedder.py\nJina v2 Code Embeddings\n768-dim, batch=8\nL2-normalized float32"]
    faiss_build["faiss_store.py\nIndexFlatIP\n(cosine sim via inner product)"]
    bm25_build["bm25_store.py\nBM25Okapi\nCamelCase + snake_case tokenizer\nSymbol names weighted 3×"]
    indexes["data/indexes/\n• code.faiss + .meta\n• commits.faiss + .meta\n• readme.faiss + .meta\n• bm25_code.pkl"]

    repos --> walker
    walker --> py
    walker --> js
    walker --> commit
    walker --> readme
    py --> jsonl
    js --> jsonl
    commit --> jsonl
    readme --> jsonl
    jsonl --> embed
    embed --> faiss_build
    embed --> bm25_build
    faiss_build --> indexes
    bm25_build --> indexes
```

## Data Flow Summary

| Phase | Where | What Happens |
|---|---|---|
| **Ingestion** | `ingestion/` | Walk repos → AST parse → chunk code/commits/docs → JSONL |
| **Indexing** | `indexing/` | Jina embeddings → FAISS + BM25 → disk |
| **Query (Runtime)** | `agents/` → `api/` | FastAPI → LangGraph → router → parallel retrieval → ambiguity → synthesis → citations |
| **UI** | `frontend/` | React SPA → axios POST `/query` → render Markdown answer + popover citations |

---

# 4. Complete Project Flow (Step by Step)

## Offline Phase (Run Once Before First Query)

### Step 1: User Configuration
User creates `repos.json`:
```json
[
  {"name": "MyBackend", "url": "https://github.com/user/MyBackend"},
  {"name": "MyRAGProject", "path": "/home/user/local/rag-project"}
]
```

### Step 2: Ingestion (`python -m ingestion.run_ingestion`)
1. `run_ingestion.py` reads `repos.json` via `_load_repos_config()`
2. For each entry with a `url`, `_resolve_repo_path()` runs `git clone --depth 500 <url>` into `repos/` directory
3. `repo_walker.py → collect_code_files()` traverses the repo, pruning `SKIP_DIRS` (node_modules, .git, `eval/`, migrations, etc.) via `os.walk(topdown=True)`. It also skips binary files using a null-byte heuristic.
4. **Python files** → `python_chunker.py → chunk_python_file()`:
   - `ast.parse(source)` builds the AST
   - `_ChunkVisitor` traverses top-level `FunctionDef`, `AsyncFunctionDef`, `ClassDef` nodes
   - For classes: emits whole class chunk PLUS each method as a sub-chunk (two levels of granularity)
   - Each chunk gets a header `# file_path\n# symbol: name\n# docstring: "..."` prepended for better embedding signal
   - Fallback: if no symbols found (pure script/imports file), sliding window of 50 lines with 10-line overlap
5. **JS/TS files** → `js_chunker.py → chunk_js_file()`:
   - Tries tree-sitter: parses CST, walks `function_declaration`, `arrow_function`, `class_declaration`, `method_definition`, `lexical_declaration` node types
   - Falls back to regex: `_TOP_LEVEL_RE` pattern catches `function name(`, `class Name`, `const name =`
   - Last resort: 60-line sliding window with 10-line overlap
6. **Git commits** → `commit_ingester.py → ingest_commits()`:
   - `git.Repo(...).iter_commits(all=True)` walks all branches
   - Skips merge commits (2+ parents)
   - Caps at 500 commits per repo
   - Each commit → chunk with: hash, author, date, message, changed_files list
   - `primary_file = changed_files[0]` enables file-hit scoring in eval
7. **README/Docs** → `readme_ingester.py → chunk_readme_file()`:
   - Regex `^(#{1,4})\s+(.+)$` finds Markdown headings
   - Each section (from one heading to the next) becomes one chunk
   - Heading text becomes `symbol_name`
   - No-heading files → one big chunk, or sliding window for RST/TXT
8. All chunks written to `data/chunks/code_chunks.jsonl`, `commit_chunks.jsonl`, `readme_chunks.jsonl`

**Canonical chunk schema:**
```json
{
  "id": "uuid4",
  "chunk_type": "code | commit | readme",
  "repo": "MyBackend",
  "file_path": "src/auth/middleware.py",
  "content": "# src/auth/middleware.py\n# symbol: verify_token\n\ndef verify_token(...):",
  "symbol_name": "verify_token",
  "language": "python",
  "start_line": 42,
  "end_line": 78,
  "commit_hash": null,
  "commit_message": null,
  "commit_date": null,
  "changed_files": []
}
```

### Step 3: Indexing (`python -m indexing.build_indexes`)
1. `build_indexes.py` reads all three JSONL files
2. `Embedder.get()` returns a lazy singleton wrapping `SentenceTransformer("jinaai/jina-embeddings-v2-base-code", trust_remote_code=True)`
3. `embedder.encode_documents(texts)` generates `(N, 768)` float32 vectors in batches of 8, L2-normalized → cosine similarity = inner product
4. `FaissStore()` creates `faiss.IndexFlatIP(768)` (flat inner product = brute-force, no approximation error)
5. `store.add(vectors, chunks)` adds vectors to FAISS, chunks to a parallel Python list `_chunks`
6. `store.save(path)` → `faiss.write_index()` for the FAISS binary + `pickle.dump(self._chunks)` for the metadata `.meta` file
7. `BM25Store(chunks)` tokenizes each chunk's content + symbol_name (symbol repeated 3× for upweighting), builds `BM25Okapi` corpus, pickles to `bm25_code.pkl`
8. Result: 4 index files in `data/indexes/`

---

## Online Phase (Every Query)

### Step 4: Frontend Query Submission
1. User types `"where have I implemented WebSocket features?"` in the React search box
2. `handleQuery()` in `App.jsx` builds payload:
   ```json
   {
     "query": "where have I implemented WebSocket features?",
     "repos": ["SketchXPad"],  // optional — user selected repo filter chips
     "conversation_history": [{"query": "...prev", "answer": "...prev"}]  // last 3 turns
   }
   ```
3. `axios.post('/query', payload)` — Vite dev proxy routes `/query` → `http://localhost:8000/query`
4. React sets `loading=true`, shows skeleton spinner

### Step 5: FastAPI Endpoint (`POST /query`)
1. `api/main.py → query_endpoint()` receives `QueryRequest` Pydantic model
2. Validates: `query` must be 3–1000 chars (Pydantic `Field` constraint)
3. Guards: if `repos.json` is empty, raises `HTTP 400` with user-friendly message
4. Builds `initial_state: AgentState` TypedDict:
   - `query`: the user's question
   - `routed_repos`: user-provided filter or `[]` (empty = let router decide)
   - All other fields initialized to empty/False defaults
   - `conversation_history`: deserialized from request's `conversation_history`
5. Calls `graph.invoke(initial_state)` — this runs the full LangGraph pipeline synchronously
6. Records `latency_ms` via `time.perf_counter()`
7. Assembles `QueryResponse` Pydantic model from result dict

### Step 6: LangGraph Pipeline Execution

#### Node 1: `route_query` (Router)
**File:** `agents/router.py`

1. Loads available repo names from `repos.json` via `_load_repo_names()`
2. **If `routed_repos` is already set in state** (user filter): skips LLM repo routing, only asks LLM for content types
3. **Otherwise:** calls Groq Llama 3.3 70B with a few-shot JSON prompt:

System prompt structure:
```
You are a query router for a personal codebase knowledge base.
Available content types: "code" | "commits" | "readme"
Rules:
  1. "where/how/show/find" → code + readme
  2. "when/why/who changed/history" → commits
  3. vague/cross-repo → include all
  4. narrow if query implies specific repo
  5. over-retrieval > missing context
  6. ALWAYS return JSON: {routed_repos: [], routed_types: []}
Available repos: ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"]
```

4. Strips markdown code fences if LLM wraps JSON in ` ```json ``` `
5. `json.loads(raw)` → validates repo names and content types against known values
6. **Fallback:** on any parse error → `routed_repos=all`, `routed_types=["code","commits","readme"]`
7. Returns `{"routed_repos": [...], "routed_types": [...]}`

**Output example:**
```json
{"routed_repos": ["SketchXPad", "MultiSource-RAG-Agent"], "routed_types": ["code", "readme"]}
```

#### Nodes 2–4: Parallel Retrieval (Fan-Out)
LangGraph fires all three retrieval nodes **simultaneously** (fan-out pattern). Each writes to a separate `Annotated[list, operator.add]` field in AgentState — LangGraph merges them automatically when all three complete.

**`retrieve_code` (`agents/retrieval_nodes.py`):**
1. Checks `"code" in routed_types` — if not, returns `{"code_chunks": []}`
2. Loads `_code_faiss()` via `@lru_cache(maxsize=1)` — first call loads from disk, subsequent calls free (cached in memory for the process lifetime)
3. `Embedder.get().encode_query(query)` → 768-dim float32 vector
4. `store.search(q_vec, top_k=10, repo_filter=routed_repos)`:
   - Internally over-fetches `top_k * 3 = 30` if repo_filter is set (to compensate for filter shrinkage)
   - `faiss.IndexFlatIP.search()` → returns top-K (index, score) pairs
   - Filters by repo and returns `list[(chunk, score)]`
5. **Hybrid re-ranking (`_hybrid_rerank`):**
   - Gets corresponding BM25 scores for the same candidate set via `bm25.search(query, candidate_indices=...)`
   - Normalizes both dense and BM25 scores to [0,1]
   - Linear combination: `score = 0.6 * dense_score + 0.4 * bm25_score`
   - Re-sorts → returns top-5 chunks
6. Returns `{"code_chunks": [chunk1, chunk2, ..., chunk5]}`

**`retrieve_commits`:** FAISS dense only (no BM25) → top-5 commit chunks filtered by repo.

**`retrieve_readme`:** FAISS dense only → top-5 readme section chunks filtered by repo.

#### Node 5: `check_ambiguity`
**File:** `agents/ambiguity_checker.py`

1. Reads `code_chunks` from merged state
2. Uses `collections.Counter` to count repos present in chunks
3. **Conditions for ambiguity flag:**
   - At least `AMBIGUITY_MIN_REPOS = 2` distinct repos in retrieved chunks
   - The top-6 code chunks contain ≥2 different repos
4. **If ambiguous:** builds a human-readable `ambiguity_detail` string listing which symbols came from which repos
5. Returns `{"ambiguity_flag": True/False, "ambiguity_detail": "..."}`

#### Node 6: `synthesize_answer`
**File:** `agents/synthesizer.py`

1. Serializes all retrieved chunks into a structured prompt block:
   - Code: `[N] repo/file:start-end | symbol: name \n \`\`\` content[:1500] \`\`\``
   - Commits: `• [repo] hash8 (date): message[:200]`
   - README: `[doc: heading @ repo/file] content[:800]`
2. **System prompt selection:**
   - Normal: "cite every claim with `[repo/file:line]`, be concrete, use markdown headers"
   - Ambiguity mode: "compare and contrast implementations, add comparison table, give recommendation"
3. **Conversation history:** last 3 turns appended as `=== PRIOR CONVERSATION ===` block
4. Calls Groq Llama 3.3 70B (`temperature=0.0`, `max_tokens=2048`)
5. Returns `{"final_answer": "..."}`

**If no context:** returns a polite fallback message without calling the LLM.

#### Node 7: `format_citations`
**File:** `agents/citation_formatter.py`

1. Parses LLM answer text for `[repo/file_path:start_line]` or `[repo/file:start-end]` markers using regex `_CITATION_RE`
2. For each marker, looks up the matching chunk in a `(repo, file_path, start_line) → chunk` dict
3. Builds a `Citation` dict with all chunk metadata (snippet, language, commit_hash, etc.)
4. **Step 2:** regardless of LLM citation markers, includes ALL retrieved chunks as supporting citations (prevents hallucinated citations from being the only ones)
5. De-duplicates by `repo::file_path::start_line` key
6. Returns `{"citations": [...]}`

### Step 7: Response Returned to Frontend
FastAPI assembles `QueryResponse`:
```json
{
  "answer": "## WebSocket Implementation\n\nThe WebSocket feature is implemented in `[SketchXPad/src/hooks/useDrawingSocket.jsx:12-45]` ...",
  "citations": [
    {"repo": "SketchXPad", "file_path": "src/hooks/useDrawingSocket.jsx", "start_line": 12, "end_line": 45, "symbol_name": "useDrawingSocket", "language": "javascript", "snippet": "const useDrawingSocket = ..."},
    ...
  ],
  "ambiguity_flag": false,
  "ambiguity_detail": "",
  "latency_ms": 9842.3,
  "routed_repos": ["SketchXPad"],
  "routed_types": ["code", "readme"]
}
```

### Step 8: Frontend Rendering
1. `setResult(data)` triggers re-render
2. `result.answer` rendered via `ReactMarkdown` with `remarkGfm` for GitHub-flavored Markdown
3. Custom `renderMarkdownComponents` override: `code` blocks → `<pre className="code">`, `[doc: ...]` tags → styled `<DescriptionIcon>` badge
4. `processCitations()` groups citations by file → builds `keyFiles`, `evidenceGroups`, `sourceGroups` arrays
5. `CitationPopover` component: numbered superscript `[1]`, click opens a popover card with file path + code snippet
6. `setConversationHistory(prev => [...prev, {query, answer}])` — session memory updated
7. `setHistory(prev => [historyItem, ...prev.slice(0, 49)])` — persists to `localStorage`

---

# 5. Folder Structure

```
Knowledge-Base-Agent/
├── .env                    # GROQ_API_KEY, LANGCHAIN_API_KEY — never committed
├── config.py               # SINGLE SOURCE OF TRUTH for all paths, model names, thresholds
├── repos.json              # Runtime repo list — user-edited, git-ignored
├── requirements.txt        # Python dependencies
│
├── ingestion/              # PHASE 1: Raw data extraction
│   ├── __init__.py         # Exports chunk_python_file, chunk_js_file, ingest_commits, chunk_readme_file
│   ├── repo_walker.py      # Filesystem traversal + noise filtering
│   ├── python_chunker.py   # Python AST → function/class chunks
│   ├── js_chunker.py       # tree-sitter / regex → JS/TS function chunks
│   ├── commit_ingester.py  # GitPython → commit history chunks
│   ├── readme_ingester.py  # Markdown heading splitter → doc chunks
│   └── run_ingestion.py    # Typer CLI entry point (ties it all together)
│
├── indexing/               # PHASE 2: Embeddings + vector store
│   ├── __init__.py         # Exports Embedder, FaissStore, BM25Store
│   ├── embedder.py         # Jina v2 singleton wrapper
│   ├── faiss_store.py      # FAISS IndexFlatIP + pickle metadata
│   ├── bm25_store.py       # BM25Okapi + camelCase tokenizer
│   └── build_indexes.py    # Typer CLI index builder
│
├── agents/                 # PHASE 3: LangGraph multi-agent engine
│   ├── __init__.py         # Exports build_graph, get_app
│   ├── state.py            # AgentState TypedDict (shared state schema)
│   ├── router.py           # route_query LangGraph node
│   ├── retrieval_nodes.py  # retrieve_code, retrieve_commits, retrieve_readme nodes
│   ├── ambiguity_checker.py# check_ambiguity node
│   ├── synthesizer.py      # synthesize_answer node
│   ├── citation_formatter.py# format_citations node
│   └── graph.py            # StateGraph assembly + CLI + singleton get_app()
│
├── api/                    # PHASE 4: REST layer
│   ├── __init__.py
│   ├── main.py             # FastAPI app: /query, /health, /repos, /repos/add, /repos/{name}/update, /repos/{name}, /feedback
│   └── schemas.py          # Pydantic models: QueryRequest, QueryResponse, Citation, AddRepoRequest, FeedbackRequest
│
├── frontend/               # PHASE 5: React SPA
│   ├── index.html          # Single HTML shell (Vite entry)
│   ├── vite.config.js      # API proxy: /query + /health + /repos → localhost:8000
│   ├── package.json        # React 18, axios, react-markdown, @mui/icons-material
│   └── src/
│       ├── main.jsx        # ReactDOM.createRoot(root).render(<App />)
│       ├── App.jsx         # Monolithic 1572-line SPA (all state, all views, all API calls)
│       ├── index.css       # CSS custom properties design system + all utility classes
│       └── components/
│           └── repos/
│               ├── AddRepoModal.jsx  # Modal form (name + URL)
│               ├── ReposView.jsx     # Repos management page
│               └── UpdateOverlay.jsx  # 4-step progress overlay during re-indexing
│
├── data/                   # Generated artifacts (git-ignored)
│   ├── chunks/             # JSONL: code_chunks.jsonl, commit_chunks.jsonl, readme_chunks.jsonl
│   └── indexes/            # Binary: code.faiss, code.faiss.meta, commits.faiss, etc.
│
├── repos/                  # Auto-cloned remote repos (git-ignored)
│   ├── LearnSphere/
│   ├── SketchXPad/
│   └── MultiSource-RAG-Agent/
│
└── eval/                   # Offline evaluation harness
    ├── test_questions.py   # 20 ground-truth questions with expected_repo, expected_file labels
    └── run_eval.py         # Evaluation runner: runs all questions, computes 5 metrics
```

**Why this structure?**
- **`config.py` is the only file that knows paths:** No other file hardcodes paths. This is the "*no magic strings*" principle — change one line and the whole system adjusts.
- **`ingestion/` and `indexing/` are completely independent:** You can re-run ingestion without touching indexes and vice versa.
- **`agents/` is pure LangGraph:** No FastAPI imports. Can be tested standalone via `python -m agents.graph`.
- **`api/` is a thin shim:** All business logic lives in `agents/`. FastAPI just orchestrates state initialization and response serialization.

---

# 6. File-by-File Explanation

## `config.py`
**Purpose:** Single source of truth for every tuneable constant.

**Key exports:**
- `ROOT_DIR`: `Path(__file__).parent.resolve()` — avoids relative-path fragility
- `REPOS_CONFIG_FILE`, `REPOS_DIR`, `CHUNKS_DIR`, `INDEXES_DIR`: all derived from ROOT_DIR
- `EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-code"`: model name
- `EMBEDDING_BATCH_SIZE = 8`: reduced from default 32 to prevent OOM on 8GB RAM Linux machines
- `GROQ_MODEL_PRIMARY = "llama-3.3-70b-versatile"`: router + synthesizer
- `GROQ_MODEL_FAST = "llama-3.1-8b-instant"`: available for cheap pre-filter steps (not yet used)
- `TOP_K_DENSE = 10`: how many FAISS candidates before BM25 re-rank
- `TOP_K_FINAL = 5`: how many chunks passed to synthesis
- `AMBIGUITY_SCORE_DELTA = 0.05`, `AMBIGUITY_MIN_REPOS = 2`: ambiguity thresholds
- `SKIP_DIRS`: set of directory names to prune during walk
- `SKIP_FILENAMES`: specific file basenames to block (e.g. `check_all.py` — a debug script committed to target repos)

**Design:** Reads `GROQ_API_KEY` from `.env` via `python-dotenv`. Defaults to `""` if missing — API calls will then fail at runtime with a clear auth error, not a cryptic import error.

---

## `agents/state.py`
**Purpose:** Define the shared state schema for the LangGraph StateGraph.

**`AgentState` TypedDict fields:**
| Field | Type | Purpose |
|---|---|---|
| `query` | `str` | User's natural language question |
| `routed_repos` | `list[str]` | Repos to search (set by router or user filter) |
| `routed_types` | `list[str]` | Content types to search: code/commits/readme |
| `code_chunks` | `Annotated[list[dict], operator.add]` | **Reducible field** — merged across parallel branches |
| `commit_chunks` | `Annotated[list[dict], operator.add]` | Same — merged |
| `readme_chunks` | `Annotated[list[dict], operator.add]` | Same — merged |
| `ambiguity_flag` | `bool` | Whether cross-repo conflict was detected |
| `ambiguity_detail` | `str` | Human-readable conflict description |
| `conversation_history` | `list[dict]` | Prior session turns (session-only, not persisted) |
| `final_answer` | `str` | LLM-generated Markdown answer |
| `citations` | `list[dict]` | Structured citation objects |

**Key design:** `Annotated[list, operator.add]` is LangGraph's way of handling **concurrent writes** from parallel nodes. When `retrieve_code`, `retrieve_commits`, and `retrieve_readme` all run simultaneously and each write to their respective `_chunks` field, LangGraph applies `operator.add` (list concatenation) to merge them automatically when the join point (`check_ambiguity`) is reached.

---

## `agents/graph.py`
**Purpose:** Compile the StateGraph topology and expose `build_graph()` and `get_app()`.

**`build_graph()` function:**
1. `builder = StateGraph(AgentState)` — typed state graph
2. Registers 7 nodes: `route_query`, `retrieve_code`, `retrieve_commits`, `retrieve_readme`, `check_ambiguity`, `synthesize_answer`, `format_citations`
3. Adds edges:
   - `START → route_query` (entry)
   - `route_query → retrieve_code` (fan-out edge 1)
   - `route_query → retrieve_commits` (fan-out edge 2)
   - `route_query → retrieve_readme` (fan-out edge 3)
   - `retrieve_code → check_ambiguity` (join)
   - `retrieve_commits → check_ambiguity` (join)
   - `retrieve_readme → check_ambiguity` (join)
   - `check_ambiguity → synthesize_answer → format_citations → END`
4. Returns `builder.compile()` — compiled executable graph

**`get_app()` lazy singleton:** The compiled graph is expensive to build (loads indexes). `get_app()` is called once at FastAPI startup and the same compiled object reused for every query across the process lifetime.

**CLI usage:** `if __name__ == "__main__": app.invoke(initial_state)` — usable standalone without FastAPI.

---

## `agents/router.py`
**Purpose:** Classify a natural language query into (repos, content_types) using Groq LLM.

**`route_query(state)` function flow:**
1. Read `state["query"]` and `state.get("routed_repos", [])`
2. Load available repos from `repos.json` (dynamically, not hardcoded)
3. If user pre-selected repos: skip LLM repo routing, only ask for content types
4. Build system prompt with few-shot examples showing JSON output format
5. `ChatGroq(model="llama-3.3-70b-versatile", temperature=0.0).invoke([SystemMessage, HumanMessage])`
6. Strip markdown code fences, `json.loads()` response
7. Validate repo names against known list; fallback to all-repos on any error
8. **Fallback strategy:** "over-retrieval is better than missing context"

**Why temperature=0.0?** Routing is a classification task — we want deterministic, consistent output, not creative variation.

---

## `agents/retrieval_nodes.py`
**Purpose:** Three parallel retrieval nodes + hybrid re-ranking logic.

**Index caching:** All four indexes (`_code_faiss`, `_commit_faiss`, `_readme_faiss`, `_code_bm25`) are loaded via `@lru_cache(maxsize=1)`. This means:
- First query: ~2–3s to load FAISS indexes from disk into RAM
- Subsequent queries: instant (Python objects cached in process memory)

**`_hybrid_rerank()` algorithm:**
```
Input: 10 FAISS candidates + BM25 object + query string
For each candidate:
  dense_score  = FAISS inner product score (already cosine, ~0..1)
  bm25_score   = BM25Okapi score for same chunk
Normalize both to [0,1] within the candidate set
combined = 0.6 * dense_score + 0.4 * bm25_score
Sort descending → return top 5
```

**Why 0.6/0.4?** Dense embeddings capture semantic similarity well. BM25 catches exact function/class name matches that embeddings might miss (e.g., if you search for "useDrawingSocket", BM25 scores it heavily because the symbol name is repeated 3× in the BM25 corpus). The 60/40 split was tuned manually.

---

## `agents/ambiguity_checker.py`
**Purpose:** Detect cross-repo conflicts in retrieved code and switch synthesis to compare-and-contrast mode.

**Detection heuristic:**
1. Count unique repos in `code_chunks`
2. If top-6 chunks span ≥2 repos → flag as ambiguous
3. Build `per_repo` dict mapping `repo → [symbol_names]`
4. Format `ambiguity_detail` string: "Multiple repos implement related functionality:\n  • RepoA: func1, func2\n  • RepoB: func3"

**Note:** This is a heuristic, not a perfect semantic comparison. The key insight is: if FAISS retrieves chunks from multiple repos for the same query, those chunks are likely semantically similar, suggesting the same concept is implemented in different places.

---

## `agents/synthesizer.py`
**Purpose:** Generate a grounded, cited answer using retrieved chunk context.

**Two system prompts:**
- **Normal:** "Answer using ONLY the provided context. Cite every claim with `[repo/file:line]`."
- **Ambiguity:** "Compare and contrast implementations. Add repo sections + comparison table + recommendation."

**Context assembly (`_format_chunks_for_prompt`):**
- Code chunks: full content, capped at 1500 chars each (token budget management)
- Commit chunks: top 5 only, compact format
- README chunks: top 3 only, capped at 800 chars

**Conversation memory:** Last 3 turns prepended as `=== PRIOR CONVERSATION ===` block. `temperature=0.0` for reproducibility.

---

## `agents/citation_formatter.py`
**Purpose:** Extract and verify citations, always grounded in real chunk metadata.

**Two-pass strategy (important design choice):**
1. **Parse:** regex `[repo/file:line]` from LLM answer → try to match against real chunk
2. **Include all:** append all retrieved chunks to citations list regardless of LLM mention

**Why?** The LLM might not cite every relevant chunk in its answer text, but we still want the UI to show all supporting evidence. Also prevents hallucinated citations from being the only ones.

**`_CITATION_RE`:** `\[(?P<repo>[^/\]]+)/(?P<path>[^\]:]+):(?P<start>\d+)(?:-(?P<end>\d+))?\]`

---

## `indexing/embedder.py`
**Purpose:** Singleton wrapper around Jina Code Embeddings model.

**Key facts about the model:**
- `jinaai/jina-embeddings-v2-base-code` — specifically trained for code across 30+ languages
- 768-dimensional output
- Requires `trust_remote_code=True` — uses a custom JinaBERT architecture not in Hugging Face core
- Symmetric retrieval: same encoding for queries and documents
- `normalize_embeddings=True` → L2-normalized → inner product = cosine similarity

**Memory optimization:** `EMBEDDING_MAX_SEQ_LEN = 512` (capped from the model's 8192 max) to prevent OOM on 8GB RAM machines. `EMBEDDING_BATCH_SIZE = 8` for the same reason.

**Singleton pattern:** `Embedder._instance` class variable. `Embedder.get()` creates it once; models are ~550MB, expensive to reload.

---

## `indexing/faiss_store.py`
**Purpose:** FAISS IndexFlatIP + parallel metadata list.

**Why `IndexFlatIP`?**
- Flat = brute-force (no approximation, no index training)
- IP = inner product = cosine similarity (since vectors are L2-normalized)
- Exact results, no recall tradeoff
- Codebase scale (hundreds to low thousands of chunks) fits comfortably in memory — no need for approximate indexes like HNSW or IVF

**`search()` with `repo_filter`:** Over-fetches `top_k * 3` from FAISS, then filters by repo name. This compensates for shrinkage when only a subset of repos are targeted.

**`remove_repo_and_save()` — elegant in-place deletion:**
1. Load index
2. Find indices of chunks to KEEP
3. `store._index.reconstruct(i)` extracts raw float32 vector for each kept index
4. Build new `IndexFlatIP`, add kept vectors, save
5. **No re-embedding needed** — vectors are reconstructed from the existing FAISS index

**Persistence:** Two files per index — `code.faiss` (binary FAISS) + `code.faiss.meta` (pickle of `_chunks` list).

---

## `indexing/bm25_store.py`
**Purpose:** BM25 sparse keyword index over code chunks, specifically for exact symbol name matching.

**Custom tokenizer `_tokenize()`:**
1. `re.sub(r"([a-z])([A-Z])", r"\1 \2", text)` — splits `useDrawingSocket` → `use Drawing Socket`
2. `re.split(r"[^a-z0-9_]+", text.lower())` — split on punctuation
3. `t.split("_")` — splits `snake_case_name` → `snake case name`
4. Remove 1-char tokens

**Symbol upweighting:** `tokens = _tokenize(symbol) * 3 + _tokenize(doc_text)` — symbol repeated 3× so BM25 heavily favors exact symbol name matches.

**`candidate_indices` parameter in `search()`:** Called with the FAISS result indices — BM25 only scores those specific chunks, not the full corpus. This keeps BM25 as a re-ranker, not a primary retriever.

---

## `api/main.py`
**Purpose:** FastAPI application exposing 6 REST endpoints.

**Endpoints:**
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/query` | Main RAG endpoint |
| `GET` | `/health` | Index existence + repo list |
| `GET` | `/repos` | Repos with chunk counts + sync timestamps |
| `POST` | `/repos/add` | Add repo + trigger ingestion |
| `DELETE` | `/repos/{name}` | Remove repo + patch indexes |
| `POST` | `/repos/{name}/update` | Isolated re-index (strip + re-embed) |
| `POST` | `/feedback` | Record thumbs-up/down to `data/feedback.jsonl` |

**`_ingest_and_index_single_repo()`:** Uses `subprocess.run([sys.executable, "-m", "ingestion.run_ingestion", "--only-repo", name])` — runs ingestion as a subprocess to avoid memory leaks from the Jina model being loaded twice in the same process.

**`_delete_repo_and_reindex()`:** 4-step in-place deletion:
1. Strip JSONL lines for the repo
2. Patch FAISS indexes via `remove_repo_and_save()`
3. Patch BM25 index
4. Clear `lru_cache` on retrieval stubs so next query loads fresh data

**`/feedback` endpoint:** Appends to `data/feedback.jsonl` — building a labeled dataset for future fine-tuning or RAG evaluation.

---

## `api/schemas.py`
**Purpose:** Pydantic v2 request/response contracts.

**`QueryRequest`:** `query: str = Field(..., min_length=3, max_length=1000)` — server-side validation prevents empty or extremely long queries.

**`Citation`:** Contains all chunk metadata fields. `chunk_type`: `"code" | "commit" | "readme"` — UI uses this to style citations differently.

**`FeedbackRequest`:** `rating: Literal["up", "down"]` — Pydantic enforces only valid values.

---

## `ingestion/repo_walker.py`
**Purpose:** Filesystem traversal with noise filtering.

**`walk_repo()` key design:** `dirnames[:] = [...]` modifies the list in-place — this tells `os.walk(topdown=True)` not to descend into pruned directories. Much more efficient than post-filtering.

**Binary detection `_is_binary()`:** Reads first 8KB as bytes, checks for null byte `\x00`. Simple and fast.

**`collect_code_files()` vs `collect_doc_files()`:** Two separate entry points with different extension sets — callers don't need to know about extension routing.

---

## `ingestion/python_chunker.py`
**Purpose:** AST-aware Python chunking.

**`_ChunkVisitor.visit_ClassDef()`:**
- Emits the **whole class** as one chunk (for retrieval by class concept)
- ALSO emits each **method** as a sub-chunk (for retrieval by specific method name)
- Two levels of granularity = higher recall for both "how does MyClass work?" (class chunk) and "show me MyClass.process()" (method chunk)

**Docstring injection:** `ast.get_docstring(node)` extracts docstring and prepends it to the chunk content header. This improves embedding quality because the docstring often contains human-language description of what the code does.

**`async` → same handler:** `visit_AsyncFunctionDef = visit_FunctionDef` — Python `asyncio` functions are treated identically to sync functions for indexing purposes.

---

## `ingestion/js_chunker.py`
**Purpose:** tree-sitter-powered JS/TS chunking with graceful regex fallback.

**`_TREE_SITTER_AVAILABLE` flag:** Checked at module load time. If tree-sitter import fails (not installed, wrong version), the entire module still works via regex. No exceptions propagated to callers.

**Tree-sitter node types captured:** `function_declaration`, `function_expression`, `arrow_function`, `class_declaration`, `method_definition`, `lexical_declaration` (for `const MyComp = () =>`), `variable_declaration`

**`_extract_symbol_name()`:** Walks to the first `identifier` child node and reads the raw bytes. This handles `const myFunc = ...` where the identifier node is `myFunc`.

**Regex fallback `_TOP_LEVEL_RE`:** Matches named functions, classes, and const assignments. Won't catch anonymous inline functions or template literals, but handles the 90% case.

---

## `frontend/src/App.jsx`
**Purpose:** Monolithic 1572-line SPA combining all state management, routing, views, and API calls.

**State managed:**
- `query`, `loading`, `result`, `error` — current query lifecycle
- `activeTab` — 'ask' | 'history' | 'repos' navigation
- `reposList`, `selectedRepos`, `healthStatus`, `backendAvailable` — repo/backend state
- `history` — `localStorage`-persisted array of past queries (max 50)
- `conversationHistory` — session-only multi-turn context (NOT persisted)
- `feedbackSent`, `copied`, `feedbackToast` — UI micro-states

**Repo color system:** `getRepoStyle(name)` uses a djb2 hash of the repo name to deterministically pick a color from `EXTENDED_PALETTE`. Preset styles exist for the 3 demo repos.

**`CitationPopover` component:** Click-to-toggle popover that reads chunk metadata directly. Uses `useRef` + `mousedown` event listener for click-outside detection.

**`renderMarkdownComponents`:** Custom ReactMarkdown renderer that:
- Renders `code` blocks with mono font
- Intercepts `[doc: label]` text patterns in paragraphs and renders them as styled file badges with a document icon

**History persistence:** `useEffect(() => { localStorage.setItem('kb_query_history', JSON.stringify(history)) }, [history])` — every history state change auto-saves.

---

## `eval/run_eval.py`
**Purpose:** Rigorous evaluation harness for the full pipeline.

**5 metrics computed:**
1. **Repo hit rate:** expected repo name in retrieved chunks/citations
2. **File hit rate:** expected file substring in file paths
3. **Answer quality:** non-empty response, or correct refusal for negative tests
4. **Ambiguity detection:** flag raised on questions tagged `is_ambiguity_test=True`
5. **Avg latency:** end-to-end `time.perf_counter()` per query

**Negative test handling (scored separately):** Questions with `expected_repo="NONE"` are excluded from repo_hit and file_hit denominators. They only count toward answer_ok — did the system correctly say "I don't know" instead of hallucinating?

**Rate-limit guard:** `time.sleep(5)` between queries to stay under Groq's free-tier 12k TPM cap.

---

# 7. Complete Frontend Flow

## Routing
Single-page application with **tab-based navigation** (no client-side router):
- `activeTab` state: `'ask'` | `'history'` | `'repos'`
- Navigation rail in sidebar triggers `setActiveTab()`
- No URL routing — all state lives in React

## Pages/Views

### Ask Tab
1. **Search bar:** Controlled `<input>` with `query` state. `onKeyDown` fires `handleQuery()` on Enter.
2. **Repo filter chips:** `reposList.map(r => <div onClick={() => toggleRepoFilter(r.name)}>)`. Selected chips show colored border + glow using CSS custom properties.
3. **Loading state:** Skeleton animation div while `loading=true`
4. **Empty state:** Starter query suggestion chips (onboarding)
5. **Conversation indicator:** Shown when `conversationHistory.length > 0`. "Continue thread (N turns)" with clear button.
6. **Result panel:** Collapsible sections — Summary, Key Files, Evidence, Sources
7. **File hit miss table:** Just for eval runs, not shown in production UI

### History Tab
- `history.filter(h => historyFilter === 'saved' ? h.saved : true)` — filter pills
- `historySearchQuery` — `h.query.toLowerCase().includes(...)` full-text search
- Selection with `selectedHistoryIds: Set<number>` — bulk delete/save
- Each item: timestamp, query, repo tags, bookmark toggle, delete button, "View" button

### Repos Tab
- `ReposView` component receives all CRUD handlers as props
- Renders repo cards with chunk count + last sync time
- Vector Index Status grid shows `code.faiss`, `commits.faiss`, `readme.faiss`, `bm25_code.pkl`

## State Management
**No Redux, no Context API.** All state lives in `App.jsx` and is passed down via props. The app is small enough that prop drilling to 2–3 levels is fine. This was a deliberate tradeoff: simplicity over scalability.

**`localStorage` persistence:** Only `history` is persisted. `conversationHistory` is session-only (cleared on refresh by design — avoids stale context from a previous session).

## Forms
- `AddRepoModal.jsx`: controlled inputs with `required` HTML attribute. `disabled` during loading. Form `onSubmit` preventDefault.
- Query input: no form element — `onKeyDown` with `Enter` key detection.

## API calls
All via `axios` (not `fetch`). Vite proxy in `vite.config.js` forwards:
- `/query` → `http://localhost:8000/query`
- `/health` → `http://localhost:8000/health`
- `/repos` → `http://localhost:8000/repos`

Error handling: `err.response?.data?.detail || err.message` — reads FastAPI's `HTTPException.detail` string.

---

# 8. Complete Backend Flow

## Server Startup
```bash
uvicorn api.main:app --reload --port 8000
```
1. FastAPI app created with title, description, version
2. `CORSMiddleware` added with `allow_origins=["http://localhost:3000", "http://localhost:5173"]`
3. `_graph_app = None` — graph is NOT loaded at startup (lazy init)
4. First `POST /query` triggers `_get_graph()` → `get_app()` → `build_graph()` → loads FAISS indexes from disk

## Middleware
Only `CORSMiddleware` — handles preflight OPTIONS requests and adds CORS headers. No authentication middleware (this is a personal local tool).

## Request Lifecycle
```
POST /query
→ Pydantic validation (QueryRequest)
→ Guard: check repos configured
→ Lazy load graph (first request only)
→ build initial_state AgentState
→ graph.invoke(initial_state)  ← synchronous LangGraph execution
→ build QueryResponse
→ return JSON
```

## Error handling
- Pydantic validation errors → `HTTP 422 Unprocessable Entity` (automatic)
- No repos configured → `HTTP 400` with user-friendly detail
- Pipeline errors (FAISS not found, Groq API error) → `HTTP 500` with `"Pipeline error: {e}"`
- Not found repo in delete → `HTTP 404`
- Duplicate repo in add → `HTTP 400`

---

# 9. Database Design

This project uses **no traditional database**. Data is stored in:

## Chunk Storage: JSONL Files
```
data/chunks/
├── code_chunks.jsonl      # One JSON object per line, one per code symbol/window
├── commit_chunks.jsonl    # One per git commit
└── readme_chunks.jsonl    # One per Markdown section
```

**Why JSONL?** Append-friendly, human-readable, easily streamed. Each line is a standalone record. `_remove_repo_from_jsonl()` deletes by repo name without loading the entire file.

## Vector Storage: FAISS + Pickle
```
data/indexes/
├── code.faiss          # FAISS IndexFlatIP binary (vector matrix)
├── code.faiss.meta     # Pickle: list[dict] chunk metadata, parallel to FAISS vectors
├── commits.faiss
├── commits.faiss.meta
├── readme.faiss
├── readme.faiss.meta
└── bm25_code.pkl       # Pickle: {chunks, bm25} dict
```

**Parallel structure:** FAISS index position `i` corresponds to `_chunks[i]`. FAISS returns integer indices; we look up metadata directly.

## Configuration: JSON Files
- `repos.json`: array of `{name, url?, path?, last_synced?}` — modified by API
- `data/feedback.jsonl`: append-only feedback log

## "Schema" (Canonical Chunk Dict)

| Field | Type | Code | Commit | Readme |
|---|---|---|---|---|
| `id` | UUID4 | ✓ | ✓ | ✓ |
| `chunk_type` | str | "code" | "commit" | "readme" |
| `repo` | str | ✓ | ✓ | ✓ |
| `file_path` | str | relative posix path | first changed file | relative posix path |
| `content` | str | header + source | full text description | section text |
| `symbol_name` | str | function/class name | commit subject line | heading text |
| `language` | str | python/javascript/etc | null | "markdown" |
| `start_line` | int | AST lineno | null | heading line number |
| `end_line` | int | AST end_lineno | null | section end line |
| `commit_hash` | str | null | full SHA | null |
| `commit_message` | str | null | full message | null |
| `commit_date` | str | null | ISO-8601 | null |
| `changed_files` | list[str] | [] | all changed files | [] |

---

# 10. Authentication

**There is no authentication in CodeAtlas.** This is by design — it's a personal local developer tool.

- No login flow
- No JWT tokens
- No sessions
- No OAuth
- API is localhost-only (CORS allows only `localhost:3000` and `localhost:5173`)

**If deploying to a team:** The obvious next step is to add:
1. Python `passlib` + JWT via `python-jose`
2. FastAPI `Depends(verify_token)` dependency injection on protected routes
3. Simple username/password for individual users, or GitHub OAuth for team access

---

# 11. API Documentation

## `POST /query`
**Purpose:** Run the full multi-agent RAG pipeline.

**Request:**
```json
{
  "query": "where have I implemented WebSocket features?",
  "repos": ["SketchXPad"],  // optional — if omitted, router decides
  "conversation_history": [  // optional — last N turns
    {"query": "previous question", "answer": "previous answer"}
  ]
}
```

**Validation:** `query` min 3, max 1000 characters.

**Response:**
```json
{
  "answer": "## WebSocket Implementation\n\nThe main WebSocket hook is `useDrawingSocket` [SketchXPad/src/hooks/useDrawingSocket.jsx:12-45]...",
  "citations": [
    {
      "repo": "SketchXPad",
      "file_path": "src/hooks/useDrawingSocket.jsx",
      "start_line": 12,
      "end_line": 45,
      "symbol_name": "useDrawingSocket",
      "commit_hash": null,
      "language": "javascript",
      "snippet": "const useDrawingSocket = (roomId) => {\n  const socket = useRef(null)...",
      "chunk_type": "code"
    }
  ],
  "ambiguity_flag": false,
  "ambiguity_detail": "",
  "latency_ms": 9842.3,
  "routed_repos": ["SketchXPad"],
  "routed_types": ["code", "readme"]
}
```

**Status codes:**
- `200 OK`: success
- `400 Bad Request`: no repos configured, or body validation error
- `422 Unprocessable Entity`: Pydantic field validation failed
- `500 Internal Server Error`: pipeline error (FAISS not found, Groq API down)

---

## `GET /health`
**Response:**
```json
{
  "status": "ok",
  "indexes_loaded": {
    "code": true,
    "commits": true,
    "readme": true,
    "bm25_code": true
  },
  "repos_configured": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"]
}
```

---

## `GET /repos`
**Response:**
```json
{
  "repos": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"],
  "repos_detail": [
    {"name": "SketchXPad", "url": "https://github.com/...", "chunk_count": 842, "last_synced": "2:34 PM"}
  ],
  "count": 3,
  "chunk_counts": {"LearnSphere": 1203, "SketchXPad": 842, "MultiSource-RAG-Agent": 567},
  "last_sync": "12 min ago"
}
```

---

## `POST /repos/add`
**Request:** `{"name": "MyProject", "url": "https://github.com/user/MyProject"}`

**What happens:**
1. Validates name uniqueness (case-insensitive)
2. Appends to `repos.json`
3. Calls `subprocess.run(["python", "-m", "ingestion.run_ingestion", "--only-repo", name])`
4. Then `subprocess.run(["python", "-m", "indexing.build_indexes"])`
5. Clears lru_cache on retrieval nodes

**Response:** `{"status": "ok", "message": "Repository 'MyProject' added and indexed successfully."}`

---

## `DELETE /repos/{repo_name}`
**What happens:** In-place removal without re-embedding. Removes from JSONL, patches FAISS and BM25 indexes.

---

## `POST /repos/{repo_name}/update`
**What happens:** Strip old data + re-ingest + re-embed **only this repo**. Other repos untouched.

---

## `POST /feedback`
**Request:**
```json
{"query": "...", "answer_snippet": "first 200 chars...", "rating": "up", "routed_repos": ["SketchXPad"]}
```
Appends to `data/feedback.jsonl`.

---

# 12. Component Communication

## Backend → Frontend
HTTP REST JSON — no WebSockets, no SSE (streaming not yet implemented).

## React Component Hierarchy
```
App.jsx (all state)
  ├── Sidebar (nav items, repo list — data flows down as props)
  ├── Hero search bar (query, loading — controlled component pattern)
  ├── Result panel (result object passed as prop processing)
  ├── CitationPopover (citation data + repoStyle → inline popover)
  ├── HighlightedCode (code string → syntax-highlighted JSX)
  └── components/repos/
      └── ReposView (reposList, onAddRepo, onUpdateRepo, onDeleteRepo — all callbacks up via props)
          ├── AddRepoModal (form state local to component + onSubmit callback)
          └── UpdateOverlay (isUpdating, targetRepo, step — display only, no state)
```

**Data flow:** Classic React prop drilling. `App.jsx` owns all state; child components receive data and callback functions as props. Events bubble up via callbacks.

---

# 13. State Management

**Global state:** `App.jsx` acts as a store. All state is React `useState` with hooks.

**State categories:**

| State | Scope | Persisted |
|---|---|---|
| `query`, `loading`, `result`, `error` | Current query lifecycle | No |
| `activeTab` | Navigation | No |
| `reposList`, `healthStatus`, `backendAvailable` | System info | No (refreshed on load) |
| `selectedRepos` | User filter | No |
| `history` | Query records | Yes (localStorage) |
| `conversationHistory` | Multi-turn context | No (session-only) |
| `feedbackSent`, `copied`, `feedbackToast` | Micro UI | No |

**Why no Redux/Zustand?** The app is small (single page, ~10 state variables). The overhead of a state management library would add complexity without benefit. `localStorage` is sufficient for history persistence. This decision would need revisiting if the app grew to multiple pages with shared complex state.

---

# 14. AI / LLM Flow

## LLM Usage in CodeAtlas

The system uses Groq Cloud API with Llama 3.3 70B in **two specific places only:**

### Router (Classification Task)
- **Input:** User query + available repo names + few-shot examples
- **Task:** JSON classification — which repos? which content types?
- **Constraints:** Temperature=0.0, JSON-only output format enforced, markdown fence stripping on output, `json.loads()` with full fallback
- **Model:** `llama-3.3-70b-versatile` (high accuracy needed for correct routing)

### Synthesizer (Generation Task)
- **Input:** User query + serialized retrieved chunks + conversation history
- **Task:** Generate grounded Markdown answer with `[repo/file:line]` citations
- **Constraints:** Temperature=0.0 for reproducibility, max_tokens=2048
- **Two system prompt modes:** Normal vs Ambiguity (compare-and-contrast)
- **Grounding rule:** "Answer ONLY from the provided context. Do not hallucinate."

## Prompt Engineering Decisions

**Few-shot examples in router:** The system prompt includes 4 example (query, JSON) pairs. This dramatically improves JSON format compliance compared to zero-shot.

**Chunk content headers:** Each code chunk has `# file_path\n# symbol: name\n# docstring: ...` prepended during ingestion. This ensures the embedding captures location metadata, not just code semantics. When the LLM receives chunks, the location is immediately obvious from the header.

**Context window management:**
- Code chunks capped at 1500 chars each
- Commit chunks: top 5 only
- README chunks: top 3 × 800 chars = 2400 chars max
- With 5 code chunks × 1500 chars ≈ 7500 chars + overhead ≈ ~2500 tokens — well within context limit

---

# 15. RAG Pipeline

## The Full RAG Flow

```
1. OFFLINE — Document Preparation
   repo_walker → python_chunker/js_chunker/commit_ingester/readme_ingester
   → JSONL chunks → Jina embeddings → FAISS + BM25 indexes

2. ONLINE — Query Time
   User Query
   → Router: classify intent (repos, content types)
   → Dense Retrieval: FAISS cosine similarity search (top-K=10)
   → Sparse Re-rank: BM25 re-scores FAISS candidates (hybrid 0.6/0.4)
   → Join: merge code + commit + readme chunks
   → Ambiguity check: cross-repo conflict detection
   → Context assembly: format chunks into LLM prompt
   → LLM Generation: Groq Llama 3.3 70B with strict citation rules
   → Citation verification: regex parse + ground-truth metadata merge
   → Response: answer + citations returned to UI
```

## Chunking Strategy
| Content Type | Strategy | Why |
|---|---|---|
| Python | AST `FunctionDef/ClassDef` → method sub-chunks | Exact boundaries, no line splits inside functions |
| JS/TS | tree-sitter > regex > sliding window | Progressive fallback for reliability |
| Git commits | One commit = one chunk | Atomic unit for temporal queries |
| Markdown | `## heading` boundaries | Logical sections, not arbitrary line counts |

## Retrieval Design Decisions

**Why three separate indexes (code, commits, readme)?**
- Different content types have different semantics
- A query about "when did X happen" → commits only
- A query about "what does X do" → code + readme
- Mixing all in one index would dilute ranking signals

**Why BM25 only for code?**
- Code has exact symbol names (camelCase, snake_case function names) that matter critically
- BM25 excels at exact keyword matching — "useDrawingSocket" query should score `useDrawingSocket` function highly
- Commits and README benefit less from symbol-exact matching

---

# 16. LangGraph Flow

## StateGraph Topology

```mermaid
graph TD
    START --> route_query
    route_query --> retrieve_code
    route_query --> retrieve_commits
    route_query --> retrieve_readme
    retrieve_code --> check_ambiguity
    retrieve_commits --> check_ambiguity
    retrieve_readme --> check_ambiguity
    check_ambiguity --> synthesize_answer
    synthesize_answer --> format_citations
    format_citations --> END
```

## Key LangGraph Concepts Used

**StateGraph:** Uses `StateGraph(AgentState)` where `AgentState` is a `TypedDict`. Every node reads from and writes back to this typed schema.

**Fan-out + Fan-in (parallel execution):**
- Three edges from `route_query` → all three retrieval nodes run simultaneously
- Three edges into `check_ambiguity` → LangGraph waits for all three to complete before running `check_ambiguity`
- `Annotated[list, operator.add]` fields enable safe concurrent writes

**Nodes:** Regular Python functions with signature `(state: AgentState) -> dict`. The return dict must contain only the fields that node modifies.

**Compiled graph:** `builder.compile()` produces an executable `CompiledGraph` object. Call `.invoke(initial_state)` to run.

**Why LangGraph instead of raw Python?**
- Fan-out parallelism is built-in — no manual threading/asyncio needed
- State typing via `TypedDict` catches bugs at development time
- LangSmith tracing works automatically with LangGraph
- Graph topology is declarable and inspectable (can visualize the graph)

---

# 17. External Services

## Groq Cloud (LLM API)
- **What:** HTTP API for fast LLM inference
- **Models used:** `llama-3.3-70b-versatile` (router + synthesizer), `llama-3.1-8b-instant` (available for future fast steps)
- **Integration:** `langchain-groq → ChatGroq(model=..., api_key=GROQ_API_KEY)`
- **Rate limits:** Free tier: ~12k tokens/minute. Eval suite adds `time.sleep(5)` between queries to avoid 429 errors.
- **Key:** Stored in `.env` as `GROQ_API_KEY`, loaded via `python-dotenv`

## Jina AI (Embedding Model)
- **What:** Open-source code embedding model, downloaded and run locally
- **Model:** `jinaai/jina-embeddings-v2-base-code` via Hugging Face hub
- **Integration:** `sentence_transformers → SentenceTransformer(model_name, trust_remote_code=True)`
- **Note:** Downloaded once (~550MB) into `~/.cache/huggingface`. After that, completely offline.
- **No API key required** — runs locally on CPU

## LangSmith (Optional Tracing)
- **What:** LangChain's observation/tracing platform
- **Integration:** Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` in `.env`
- **What it captures:** Every LangGraph node invocation, every LLM call, token counts, timing
- **Used for:** Debugging retrieval quality, monitoring synthesis quality in production

## GitHub (Source Code)
- **What:** Remote repository hosting
- **Integration:** `subprocess.run(["git", "clone", "--depth", "500", url, dest])` — plain git CLI
- **`--depth 500`:** Shallow clone to cap history fetched (init speed vs commit history depth tradeoff)

## No other external services.** No Redis, Kafka, S3, Firebase, or Stripe. All storage is local filesystem.

---

# 18. Deployment

## Current Setup (Local Development)
```bash
# Terminal 1: Backend
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

## Environment Variables
```env
GROQ_API_KEY=gsk_...          # Required
LANGCHAIN_TRACING_V2=true     # Optional: enable LangSmith
LANGCHAIN_API_KEY=lsv2_...    # Optional: LangSmith key
LANGCHAIN_PROJECT=Knowledge-Base-Agent  # Optional
```

## Production Improvements (Not Yet Implemented)
1. **Docker:** `Dockerfile` for FastAPI with Python 3.11, `docker-compose.yml` with nginx reverse proxy
2. **Process manager:** `supervisord` or `gunicorn` with `uvicorn` workers for the FastAPI server
3. **Frontend build:** `npm run build` → static files served by nginx
4. **Persistent volume:** mount `data/` directory to avoid losing indexes between container restarts
5. **Health checks:** Docker healthcheck hitting `GET /health`

## CI/CD (Not Implemented)
Would add:
- GitHub Actions workflow: run `python -m eval.run_eval` on push → fail if metrics drop below threshold
- `pytest` unit tests for chunkers and retrieval nodes

---

# 19. Security

## What's Secured
- **CORS:** Only `localhost:3000` and `localhost:5173` are allowed origins. Cross-origin requests from any other domain are rejected.
- **Input validation:** Pydantic models enforce field types and lengths. `query` max 1000 chars prevents absurdly large prompts.
- **API key in `.env`:** `GROQ_API_KEY` never hardcoded, never committed. `.gitignore` excludes `.env`.

## What's Not Secured (Local Tool)
- No auth — anyone who can reach port 8000 can query the system
- No rate limiting on the FastAPI server itself
- No HTTPS (localhost only)
- `subprocess.run` for ingestion — if a user-supplied `repo_name` contained shell metacharacters it could be a concern, mitigated because the name is passed as a CLI `--only-repo` argument value (not interpolated into a shell string)

## Prompt Injection Mitigation
- System prompt clearly states "Answer ONLY from the provided context"
- User query is placed in a `HumanMessage`, not interpolated into the system prompt
- Retrieved chunks are enclosed in clearly delimited `=== CODE CHUNKS ===` blocks
- **Not perfectly secure:** A sophisticated prompt injection in a code chunk could potentially confuse the LLM, but this is a known limitation of RAG systems

## SQL Injection
Not applicable — no SQL database used.

---

# 20. Error Handling

## Frontend
- `try/catch` around every `axios` call
- `err.response?.data?.detail || err.message` — reads FastAPI detail if available
- `setError(...)` → renders red banner with error text
- `backendAvailable=false` state → renders "Backend Not Reachable" screen with retry button
- Loading spinner prevents double-submission during in-flight requests

## Backend (FastAPI)
- Pydantic validation → automatic `422` with validation details
- `HTTPException(status_code=400, detail="...")` for business logic errors
- `try/except Exception as e: raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")` wraps the graph invocation
- Subprocess errors: `returncode != 0` check, stderr logged and propagated as `RuntimeError`

## Ingestion
- `ast.parse()` `SyntaxError` → falls back to sliding window (file not lost)
- `git.InvalidGitRepositoryError` → skip commits with warning, continue other operations
- `OSError` on file read → return empty list
- `tree-sitter` import failure → regex fallback

## LLM Routing Failures
- Any `json.loads()` or `json.parse()` exception → fallback to `routed_repos=all_repos`, `routed_types=all_types`
- "Over-retrieval is better than missing context"

## FAISS Not Found
- `FaissStore.load()` raises `FileNotFoundError` → `_code_faiss()` catches it → returns `None` → `retrieve_code` returns `{"code_chunks": []}` → synthesizer returns "no context" message to user

---

# 21. Performance Optimizations

## Embedding Model (Biggest Bottleneck)
- **Singleton pattern:** Model loaded once, reused for all queries
- **`lru_cache` on index loaders:** FAISS indexes loaded once per process, cached in RAM
- **Batch processing:** `EMBEDDING_BATCH_SIZE=8` — GPU/CPU optimal batch size
- **`EMBEDDING_MAX_SEQ_LEN=512`:** Caps context window to prevent OOM on 8GB RAM

## FAISS
- **`IndexFlatIP`:** Brute-force (100% recall), suitable for thousands of vectors. Scalability boundary: ~1M vectors would require moving to `IndexIVFFlat` or `IndexHNSWFlat` for approximate nearest neighbors.
- **In-memory:** Entire index kept in RAM during server process lifetime

## React Frontend
- No memoization yet (not needed at this scale)
- `useCallback` not used (functions recreated each render, but re-renders are infrequent)
- `localStorage` debounced by React state batching — writes happen in `useEffect`, not during every keystroke

## Ingestion
- **Parallel repo ingestion:** Currently sequential. Could use `concurrent.futures.ProcessPoolExecutor` to ingest multiple repos simultaneously.
- **Incremental indexing:** `--only-repo` flag + `_remove_repo_from_jsonl` enables updating one repo without reprocessing others.

---

# 22. Design Patterns

## Singleton
- `Embedder._instance` — embedding model loaded once, shared across all queries
- `_app` in `graph.py` — compiled LangGraph graph loaded once per process
- `@lru_cache(maxsize=1)` on FAISS/BM25 loaders — effectively a singleton per index

## Strategy Pattern
- JavaScript chunking: tree-sitter → regex → sliding window (three strategies, same interface `chunk_js_file(file_path, repo, repo_root) -> list[dict]`)
- Synthesizer system prompt: Normal strategy vs Ambiguity strategy selected at runtime

## Factory Pattern
- `_make_chunk()` helper functions in `python_chunker.py` and `js_chunker.py` — centralized chunk dict construction ensuring consistent schema

## Command Pattern
- Typer CLI in `run_ingestion.py` and `build_indexes.py` — each CLI command encapsulates a complete operation

## Observer (via React state)
- `useEffect(() => { localStorage.setItem(...) }, [history])` — state change observer auto-syncs to localStorage

## Adapter Pattern
- `FaissStore` wraps raw FAISS `IndexFlatIP` into a user-friendly `search(query_vec, top_k, repo_filter)` API
- `BM25Store` wraps `rank-bm25 BM25Okapi` into the same interface pattern

## Fan-out / Fan-in (Parallel Execution)
- LangGraph edges from `route_query` to three retrieval nodes implement classic fan-out
- Three edges into `check_ambiguity` implement fan-in with automatic state merging

---

# 23. SOLID Principles

## Single Responsibility
- `repo_walker.py`: **only** walks file system
- `python_chunker.py`: **only** chunks Python files
- `embedder.py`: **only** encodes text to vectors
- `faiss_store.py`: **only** stores/retrieves vectors
- `router.py`: **only** classifies query intent
- `synthesizer.py`: **only** generates the answer
- `citation_formatter.py`: **only** builds citation objects

## Open/Closed
- `FaissStore` and `BM25Store` both expose `remove_repo_and_save()` static methods — new deletion strategies can be added without modifying existing `search()` or `save()` logic
- New content types (e.g., API docs, test files) can be added by creating new chunkers + a new `retrieve_*` node, without modifying existing nodes

## Liskov Substitution
- `BM25Store.search()` and `FaissStore.search()` return the same `list[tuple[dict, float]]` type — interchangeable in callers

## Interface Segregation
- LangGraph nodes have minimal interface: `(state: AgentState) -> dict` — only return the fields they modify, not the full state

## Dependency Inversion
- `run_ingestion.py` depends on `chunk_python_file`, `chunk_js_file`, `ingest_commits`, `chunk_readme_file` — abstractions, not concrete implementations. Chunking implementations can change without modifying the ingestion runner.
- `api/main.py` depends on `get_app()` — not on specific graph topology or node implementations

---

# 24. Interview Questions & Answers

## Beginner (100 Questions)

**Q1. What does CodeAtlas do in simple terms?**
It's a search engine for your own code. You ask it a question like "where is my authentication code?" and it finds the exact file and line number across all your GitHub repos.

**Q2. What is RAG?**
Retrieval-Augmented Generation — first retrieve relevant documents, then pass them to an LLM to generate an answer grounded in those documents. Prevents hallucination.

**Q3. What programming language is the backend written in?**
Python.

**Q4. What framework is the backend API built with?**
FastAPI — an async Python web framework with automatic OpenAPI docs and Pydantic validation.

**Q5. What framework is the frontend built with?**
React 18 with Vite as the build tool.

**Q6. What is FAISS?**
Facebook AI Similarity Search — a library for efficient similarity search over dense vector embeddings. Used to find the most semantically similar code chunks to a query.

**Q7. What is BM25?**
Best Match 25 — a classic information retrieval algorithm that scores documents based on keyword frequency. Used alongside FAISS for exact symbol name matching.

**Q8. What is the embedding model used?**
`jinaai/jina-embeddings-v2-base-code` — a 768-dimensional model specifically trained for code embedding across 30+ languages.

**Q9. What LLM does CodeAtlas use?**
Groq's Llama 3.3 70B via the Groq Cloud API.

**Q10. What is LangGraph?**
A library from LangChain for building stateful multi-agent workflows as directed graphs. Each node is a Python function; edges define execution order.

**Q11. What are the three types of content indexed?**
Source code files, git commit history, and Markdown README/documentation files.

**Q12. How does a user add a new repository?**
In the Repositories tab, click "Add Repository", enter a name and GitHub URL. The backend clones the repo, runs ingestion, builds embeddings, and updates the vector indexes.

**Q13. How long does indexing take?**
Depends on repo size. For a medium Python/JS repo (~200 files, 500 commits), roughly 10–30 seconds with a CPU-only setup (Jina inference in batches of 8).

**Q14. What is the `repos.json` file?**
A JSON array of repository configurations `[{"name": "X", "url": "..."}, ...]`. It's the user-maintained list of repos to index.

**Q15. What format are the chunk files stored in?**
JSONL (JSON Lines) — one JSON object per line in `data/chunks/`.

**Q16. What does AST mean?**
Abstract Syntax Tree — a tree representation of source code structure. Python's `ast` module parses Python source and returns an AST that you can walk to find function and class definitions.

**Q17. Why is tree-sitter used for JavaScript?**
Python has a built-in `ast` module. JavaScript/TypeScript doesn't have an equivalent in the Python standard library. Tree-sitter is a high-performance incremental parser that works for 40+ languages including JS/TS/JSX/TSX.

**Q18. What does `SKIP_DIRS` contain and why?**
`node_modules`, `.git`, `__pycache__`, `venv`, `eval/`, `migrations/`, etc. These directories contain auto-generated or non-user code that would pollute the index with noise.

**Q19. What is a chunk?**
A unit of text (code, commit message, README section) stored with metadata: `id`, `repo`, `file_path`, `content`, `start_line`, `end_line`, `symbol_name`.

**Q20. What happens when you query a repo that doesn't have an index?**
FastAPI returns an `HTTP 400` error with a message telling the user to add and index a repository first.

**Q21. What port does the FastAPI backend run on?**
Port 8000 (`uvicorn api.main:app --reload --port 8000`).

**Q22. What port does the React frontend run on?**
Port 5173 (Vite default).

**Q23. How does the frontend talk to the backend without cross-origin issues?**
Vite's `server.proxy` config in `vite.config.js` forwards `/query`, `/health`, and `/repos` to `http://localhost:8000` — so from the browser's perspective, API calls go to the same origin (5173).

**Q24. What is CORS and why is it configured here?**
Cross-Origin Resource Sharing — browser security policy preventing one origin from making requests to another. FastAPI's `CORSMiddleware` adds response headers allowing requests from the React dev server origins.

**Q25. What is Pydantic used for?**
Request/response schema validation in FastAPI. `QueryRequest`, `QueryResponse`, `Citation`, `AddRepoRequest`, `FeedbackRequest` are Pydantic models that validate types and constraints automatically.

**Q26. How is conversation history handled?**
Session-only in React `conversationHistory` state — last 3 turns sent with each POST `/query` request. Not persisted in localStorage or database. Cleared on page refresh.

**Q27. How is query history stored?**
In `localStorage` under key `kb_query_history`. Max 50 items, newest first.

**Q28. What is `AgentState`?**
A `TypedDict` defining the schema of the shared state object that flows through the LangGraph execution. Every node reads from and writes to this object.

**Q29. Why is `operator.add` used in `AgentState`?**
`Annotated[list, operator.add]` tells LangGraph to merge (concatenate) list writes from parallel branches automatically. Without this, parallel nodes writing to the same field would conflict.

**Q30. What is the vector dimension of Jina embeddings?**
768 dimensions.

**Q31. What does `IndexFlatIP` mean in FAISS?**
Flat = brute-force (no approximation), IP = Inner Product. Using L2-normalized vectors, inner product equals cosine similarity.

**Q32. Why are vectors L2-normalized?**
Cosine similarity = inner product when both vectors are unit-length. FAISS IndexFlatIP computes inner product, so normalizing makes it equivalent to cosine similarity without changing the index type.

**Q33. What is the hybrid score formula?**
`score = 0.6 * dense_score + 0.4 * bm25_score`. Dense captures semantic similarity; BM25 captures exact keyword matches.

**Q34. What does the router node do?**
Uses Groq LLM with a few-shot JSON prompt to classify the query into target repos and content types (code/commits/readme).

**Q35. What happens if the router LLM fails to produce valid JSON?**
Falls back to `routed_repos=all available repos`, `routed_types=["code","commits","readme"]` — safe over-retrieval rather than a broken response.

**Q36. What does the `check_ambiguity` node do?**
Detects if code chunks from multiple different repos appear in the top results, suggesting the same concept is implemented differently across repos.

**Q37. What is "ambiguity mode" in synthesis?**
When `ambiguity_flag=True`, the synthesizer uses a different system prompt that instructs the LLM to compare and contrast implementations across repos, add a comparison table, and provide a recommendation.

**Q38. What is `format_citations` doing?**
Parsing `[repo/file:line]` markers from the LLM answer text, matching them against real chunk metadata, and adding all retrieved chunks as supporting citations.

**Q39. How many commits per repo does the ingester index?**
Maximum 500 (`MAX_COMMIT_HISTORY` in config).

**Q40. Are merge commits included?**
No — `skip_merges=True` by default. `len(commit.parents) > 1` identifies merge commits.

**Q41. What library is used to read git history?**
GitPython (`import git`).

**Q42. What library is used for BM25?**
`rank-bm25` — `BM25Okapi` specifically.

**Q43. Why do symbol tokens appear 3× in BM25 corpus?**
`_tokenize(symbol) * 3 + _tokenize(doc_text)` — BM25 term frequency favors terms that appear more. Repeating symbol tokens artificially inflates their frequency, making BM25 heavily favor exact symbol name matches.

**Q44. What does `trust_remote_code=True` mean in SentenceTransformer?**
The Jina model uses a custom PyTorch architecture (`JinaBERT`) not in the Hugging Face core library. `trust_remote_code=True` allows executing the model's custom Python code downloaded from the Hub.

**Q45. How is the Jina model downloaded?**
Automatically by `SentenceTransformer()` on first call — fetched from Hugging Face Hub (~550MB), cached locally in `~/.cache/huggingface`. Subsequent calls use the cache without downloading.

**Q46. What is the LangSmith integration for?**
LangChain's observability platform. When `LANGCHAIN_TRACING_V2=true`, every LangGraph node execution and LLM call is traced and visible in the LangSmith dashboard for debugging.

**Q47. What does `_ingest_and_index_single_repo()` do?**
Called by the `/repos/add` and `/repos/{name}/update` endpoints. Runs ingestion and indexing for a single repo via `subprocess.run()` — using a subprocess to avoid loading the Jina model twice in the same process.

**Q48. What does `_delete_repo_and_reindex()` do?**
Removes a repo's data from all three JSONL files and all three FAISS/BM25 indexes (in-place), then clears lru_cache so the next query loads fresh data. **No re-embedding of any other repo.**

**Q49. What are the frontend dependencies?**
React 18, ReactDOM, axios (HTTP), react-markdown (Markdown rendering), remark-gfm (GitHub Flavored Markdown), @mui/icons-material (icon library), @emotion/react + @emotion/styled (MUI peer deps).

**Q50. What is the evaluation harness?**
`eval/run_eval.py` — a Typer CLI that runs 20 labeled questions through the full LangGraph pipeline and computes repo hit rate, file hit rate, answer quality, ambiguity detection rate, and avg latency.

**Q51. What was the repo hit rate in the benchmark?**
89% (17/19 questions — one negative test excluded from denominator).

**Q52. What was Answer Quality?**
100% (20/20) — every query produced a non-empty, grounded response or correctly refused to answer for out-of-domain questions.

**Q53. What does `expected_repo="NONE"` mean in eval questions?**
It marks a negative/hallucination test — the query is about something not in any indexed repo (e.g., Kubernetes deployment). The system should **decline** to answer, not hallucinate code.

**Q54. What is the `--fresh` flag in ingestion?**
Deletes existing chunk JSONL files before ingesting — useful for a clean slate rebuild.

**Q55. What is the `--only-repo` flag?**
`python -m ingestion.run_ingestion --only-repo my-repo` — processes only that one named repo from `repos.json`, leaving other repos' existing chunks untouched.

**Q56. How are files determined to be binary?**
`_is_binary()` reads the first 8KB as bytes and checks for a null byte `\x00`. If present, the file is treated as binary and skipped.

**Q57. Why SQLite/PostgreSQL is not used for chunk storage?**
Chunks are write-once (ingestion), read in bulk for embedding, then superseded by FAISS indexes. A key-value or relational DB would add overhead without benefit. JSONL is simpler and fast enough for tens of thousands of chunks.

**Q58. What does the `feedback` endpoint do?**
Records user thumbs-up/down to `data/feedback.jsonl` — building a labeled dataset that could be used for future RAG evaluation or fine-tuning.

**Q59. What does `_get_repo_chunk_counts()` do?**
Reads all three JSONL files, parses each line, and counts chunks by `repo` name. Used by `GET /repos` to show how many chunks each repo contributed.

**Q60. What is the sliding window fallback in chunkers?**
If no AST symbols are found in a file (e.g., a pure script with only `if __name__ == "__main__"`), the chunker falls back to fixed-size windows. Python: 50 lines × 10 overlap. JS: 60 lines × 10 overlap.

**Q61. What Python version is this project written for?**
Python 3.10+ (uses `TypedDict` with `from __future__ import annotations`, `list[str] | None` union syntax, `match` statements not used).

**Q62. What is `typer` used for?**
A library for building CLI applications with type hints. Used in `run_ingestion.py` and `build_indexes.py` to parse command-line arguments cleanly.

**Q63. What is `rich` used for?**
Beautiful terminal output — colored text, progress bars (`track()`), styled tables (`Table`), Markdown rendering (`Markdown`), panel boxes (`Panel`).

**Q64. What is `tqdm` used for?**
Progress bar in `embedder.encode_documents()` — shows embedding progress in the terminal.

**Q65. How does the UI know if the backend is down?**
`loadSystemInfo()` calls both `/repos` and `/health` with `.catch(() => null)`. If both return null, `setBackendAvailable(false)` — shows "Backend Not Reachable" UI with a retry button.

**Q66. What is `RepoStyle` and how is it computed?**
`getRepoStyle(name)` applies a djb2 hash of the repo name to pick a color/soft-background pair from `EXTENDED_PALETTE`. Preset styles exist for 3 demo repos. This ensures each repo always gets the same color deterministically.

**Q67. What is `CitationPopover`?**
An inline React component that renders a numbered superscript badge. When clicked, shows a popover card with the citation's repo name, file path, line range, and code snippet.

**Q68. What is `HighlightedCode`?**
A simple custom syntax highlighter: splits code by line, applies regex for keywords, function names, and string literals, wraps in `<span className="kw/fn/str">` for color styling.

**Q69. What is the `--depth 500` flag in `git clone`?**
Limits git history to the 500 most recent commits when cloning. Speeds up cloning for large repos. The ingester also caps at `MAX_COMMIT_HISTORY=500` commits anyway.

**Q70. What files are in SKIP_FILENAMES?**
`check_all.py` — a root-level debug script committed to one of the target repos (`MultiSource-RAG-Agent`) that would otherwise compete with real implementation files in retrieval.

**Q71. What does `_load_repo_names()` return?**
`[r["name"] for r in _load_repos_config()]` — a list of repo name strings from `repos.json`. Used to validate LLM routing output.

**Q72. How are selected repos sent to the backend?**
`axios.post('/query', { repos: selectedRepos })` — if the user selected repo filter chips, they're sent as an optional `repos` array in the request body.

**Q73. What is `UpdateOverlay.jsx`?**
A full-screen overlay shown during single-repo update operations. Displays a 4-step progress indicator (Stripping old data → Git pull → JinaAI embedding → Append to indexes) with spinner, done, and pending icons.

**Q74. What is `remark-gfm`?**
A ReactMarkdown plugin that enables GitHub Flavored Markdown: tables, strikethrough, task lists, and auto-linking URLs.

**Q75. How does multi-turn conversation work technically?**
Frontend keeps `conversationHistory: [{query, answer}, ...]` in React state. Each new query includes `conversation_history: conversationHistory.slice(-3)` in the POST body. Backend puts last 3 turns in a `=== PRIOR CONVERSATION ===` block prepended to the LLM user message.

**Q76. Why is conversation history NOT persisted in localStorage?**
Design decision: stale conversation context from a previous session could confuse answers. Starting fresh each session is safer for a query-based tool.

**Q77. What happens when I clear the conversation thread?**
`setConversationHistory([])` — resets to empty array. Next query has no prior context.

**Q78. How does the repo chip filter work with the router?**
If `selectedRepos = ["SketchXPad"]`, POST `/query` sends `repos: ["SketchXPad"]`. The router node sees `already_filtered_repos=["SketchXPad"]`, validates against known repos, skips LLM repo routing, and only asks LLM to determine content types.

**Q79. What does `_get_last_sync_time()` do?**
Reads the `st_mtime` of the `code.faiss` or `code_chunks.jsonl` file and computes a relative time string ("Just now", "12 min ago", "3 h ago").

**Q80. What validation does `AddRepoModal` have?**
HTML `required` on both inputs, `disabled` submit button when either field is empty, server-side duplicate name check in `/repos/add` endpoint.

**Q81. What is `parent_class` in a Python chunk?**
When a method is emitted as a sub-chunk, `extra={"parent_class": "MyClass"}` is added. This allows queries like "show me MyClass.process()" to match correctly even when the method is indexed as a standalone chunk.

**Q82. What is the `_HEADING_RE` regex?**
`r"^(#{1,4})\s+(.+)$"` — matches Markdown headings at any level (h1-h4), capturing the heading text. Used to split README into sections.

**Q83. What does `min_section_chars=50` do?**
Sections shorter than 50 characters (e.g., just a heading with no body) are dropped. Prevents tiny, content-less chunks from polluting the index.

**Q84. What is the `commit hash` used for in citations?**
Displayed in the citation UI as `commit:abc1234`. Allows the user to look up the exact commit on GitHub to understand why code was written.

**Q85. What does `primary_file = changed_files[0]` in commit ingester enable?**
Each commit chunk gets a `file_path` equal to the first changed file. This allows file-hit scoring in the eval harness to work for commit chunks — if the expected file is `router.py` and a commit chunk has `file_path="router.py"`, it's a file hit.

**Q86. What was the file hit rate in the benchmark?**
57% (11/19) — noted as "actively being improved." Root cause: eval/debug scripts inside target repos competing with implementation files in retrieval. Fixed by adding `eval/` to `SKIP_DIRS` and debug filenames to `SKIP_FILENAMES`.

**Q87. What is `TOP_K_DENSE`?**
10 — the number of FAISS candidates fetched before BM25 re-ranking. After re-ranking, `TOP_K_FINAL=5` chunks are kept.

**Q88. What is `AMBIGUITY_SCORE_DELTA`?**
0.05 — a threshold value defined in config but currently not directly used in the ambiguity heuristic (the heuristic uses top-6 repo presence instead). Retained for future use.

**Q89. How is citation snippet extracted?**
`_extract_snippet()` in `citation_formatter.py`: takes first 10 non-header lines of chunk content, trims to 300 chars. Filters out `# ` prefixed header lines added during ingestion.

**Q90. What does `from __future__ import annotations` do?**
Enables postponed evaluation of type annotations (PEP 563). Allows using `list[str] | None` syntax in Python 3.9 without runtime errors, and forward references in TypedDicts.

**Q91. How does `lru_cache(maxsize=1)` work on FAISS loaders?**
Python decorates the function with a dictionary-based cache. Since `maxsize=1`, only one result is cached. A no-argument function is called identically every time, so the first call loads from disk and the cached result is returned forever after (until process restart or `cache_clear()` is called).

**Q92. When does `cache_clear()` get called on FAISS loaders?**
After repo addition, deletion, or update operations in `api/main.py`. This forces the next query to reload fresh indexes from disk.

**Q93. What is `uuid.uuid4()` used for in chunks?**
Each chunk gets a globally unique `id`. Used for deduplication in `format_citations` via `seen_ids: set[str]`.

**Q94. What is `textwrap.dedent()` used for in python_chunker?**
Removes common leading whitespace from extracted code lines. A method extracted from an indented class body would otherwise have 4 spaces of indentation on every line — dedent removes it.

**Q95. What is the `shell` CSS class?**
`App.jsx` root element: `<div className="shell">`. Defined in `index.css` as a `display: grid; grid-template-columns: auto 1fr; height: 100vh;` layout giving sidebar + main content areas.

**Q96. What does `dangerouslySetInnerHTML` do in HighlightedCode?**
Injects HTML string as inner content of a DOM element, bypassing React's XML escaping. Used for syntax highlighting regex replacements that inject HTML `<span>` tags. Risky if user content could contain XSS payloads, but here the content is code from the user's own repos.

**Q97. What does `axios.delete(\`/repos/\${encodeURIComponent(repoName)}\`)` do?**
`encodeURIComponent()` URL-encodes the repo name to handle special characters in repo names. Maps to `DELETE /repos/{repo_name}` FastAPI endpoint.

**Q98. What format does the feedback endpoint store data in?**
JSONL at `data/feedback.jsonl`. Each line: `{"timestamp": "...", "query": "...", "answer_snippet": "...", "rating": "up|down", "routed_repos": [...]}`.

**Q99. How is `loadSystemInfo()` called?**
`useEffect(() => { loadSystemInfo() }, [])` — runs once on component mount (empty dependency array). Also called after add/delete/update repo operations to refresh the repos list.

**Q100. What is the `STARTER_QUERIES` array?**
5 example queries shown on the empty state before a user's first question. Examples include "Where have I implemented WebSocket real-time features?" and "What authentication patterns are used?"

---

## Intermediate (100 Questions)

**Q101. Explain the FAISS inner product vs cosine similarity relationship.**
FAISS `IndexFlatIP` computes inner product: `score = a · b = |a||b|cos(θ)`. If both vectors are L2-normalized (`|a|=|b|=1`), then `a · b = cos(θ)`. So inner product equals cosine similarity when inputs are unit vectors. Jina's `normalize_embeddings=True` ensures all stored vectors are L2-normalized.

**Q102. Why use `IndexFlatIP` instead of HNSW or IVF?**
`IndexFlatIP` is exact (100% recall, zero approximation error). HNSW and IVF are approximate (trade recall for speed). For CodeAtlas's scale (hundreds to low thousands of vectors), brute-force search takes microseconds — approximation would only matter at millions of vectors.

**Q103. How would you scale to 1M+ code chunks?**
Switch to `IndexIVFFlat` (inverted file + flat quantizer) or `IndexHNSWFlat` (hierarchical navigable small world). Both require training on a representative sample of vectors before adding data. `IndexIVFFlat` uses cluster centroids to narrow search to a subset of vectors (nprobe parameter tunable for recall/speed tradeoff).

**Q104. Explain the fan-out → fan-in pattern in LangGraph.**
In `graph.py`, three edges from `route_query` to each retrieval node create fan-out. Three edges from each retrieval node to `check_ambiguity` create fan-in. LangGraph's execution engine runs all fan-out branches concurrently. The fan-in node waits for all producers to complete. `Annotated[list, operator.add]` tells LangGraph how to merge concurrent writes to the same state field (list concatenation in this case).

**Q105. How does the BM25 re-ranking work step by step?**
1. FAISS returns 10 (chunk, dense_score) pairs
2. Map chunk IDs to BM25 corpus indices
3. `bm25.get_scores(tokenized_query)` → scores for the entire corpus
4. Extract scores only for the 10 FAISS candidates (`candidate_indices`)
5. Normalize both score sets to [0,1] within the candidate set
6. Linear combination: `0.6 * dense + 0.4 * bm25`
7. Sort descending, return top 5

**Q106. What is the memory layout of FAISS + pickle metadata?**
FAISS stores only float32 vectors as a contiguous C array. Metadata (chunk dicts) are stored in a Python list `_chunks` pickled separately. The FAISS index at position `i` corresponds to `_chunks[i]`. When loading, both files are deserialized independently and the parallel structure is maintained.

**Q107. Why does FAISS `reconstruct(i)` work without re-embedding?**
`IndexFlatIP` stores the actual raw float32 vectors (unlike compressed indexes like PQ). `reconstruct(i)` reads the vector at position `i` directly from the stored C float array. This enables the `remove_repo_and_save()` operation to extract kept vectors without re-running Jina inference.

**Q108. How does `_ChunkVisitor.visit_ClassDef` avoid double-counting nested classes?**
`_inside_class` flag: set to the class name when entering a ClassDef, reset to None (or outer class name) when leaving. `for child in ast.walk(node)` visits all descendants. The check `if child is not node` ensures the class itself is not emitted again, only its method children.

**Q109. What is the conversation history token budget management?**
`conversation_history[-3:]` — only last 3 turns included. Each turn's answer is capped to 500 chars in the prompt: `f"A: {turn.get('answer', '')[:500]}..."`. This prevents conversation history from consuming too much of the 2048-token output budget.

**Q110. How does the ambiguity detection heuristic differ from a similarity threshold?**
The README describes `AMBIGUITY_SCORE_DELTA = 0.05` (if top-2 FAISS scores are within 0.05 of each other AND from different repos → ambiguous). But the actual implementation checks if the top-6 code chunks span ≥2 different repos. The score delta approach would require storing FAISS scores in AgentState (complex); the repo-presence heuristic is simpler to implement.

**Q111. What's the difference between `routed_types` "code" vs "commits" in retrieval?**
- `"code"` → search `code.faiss` + BM25 re-ranking → exact function/class level results
- `"commits"` → search `commits.faiss` dense only → temporal/authorship results
- `"readme"` → search `readme.faiss` dense only → documentation results
The router selects which of the three retrieval nodes actually do work.

**Q112. How does the `repo_filter` work in FAISS search?**
`fetch_k = top_k * 3 if repo_filter else top_k`. FAISS returns the top `fetch_k` without repo filtering (FAISS doesn't natively support filtered search on non-vector metadata). Then Python post-filters: `if repo_filter and chunk.get("repo") not in repo_filter: continue`.

**Q113. What is `_CITATION_RE` and how does it work?**
`\[(?P<repo>[^/\]]+)/(?P<path>[^\]:]+):(?P<start>\d+)(?:-(?P<end>\d+))?\]`
- `(?P<repo>[^/\]]+)` — repo name: everything until `/` or `]`
- `/` literal separator
- `(?P<path>[^\]:]+)` — file path: everything until `:` 
- `:` separator
- `(?P<start>\d+)` — start line number
- `(?:-(?P<end>\d+))?` — optional `-end_line`
- `\]` closing bracket

**Q114. Why does `synthesizer.py` cap code chunks at 1500 chars?**
Token budget management. The LLM context window is 32K+, but: 5 code chunks × 1500 chars ≈ 7500 chars ≈ 1875 tokens (4 chars/token). Plus 5 commits + 3 README sections + system prompt ≈ ~3000 total tokens passed as context. 2048 output tokens leaves room for a detailed answer.

**Q115. What problem does `_clean_label()` in synthesizer.py solve?**
Strips emoji and non-ASCII characters from README section headings. Some README headings use emoji (e.g., "🚀 Quick Start"). Emoji in prompt text can cause encoding issues or confuse the LLM's JSON output parser. `re.sub(r'[^\x00-\x7F]+', '', text)` removes all non-ASCII characters.

**Q116. How does `_format_dt()` handle timezone-naive datetimes?**
`if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)` — GitPython can return timezone-naive datetime objects for old commits. Forcing UTC avoids "can't compare naive and aware datetimes" errors in `isoformat()`.

**Q117. Explain `processAnswerText` in App.jsx.**
In the current implementation, `processAnswerText()` builds a `citationMap` from citation list but then returns `answerText` unchanged (`return answerText`). This function is a stub — the intended feature (replacing `[repo/file:line]` markers with numbered `CitationPopover` components) is partially implemented. The citation popovers are rendered separately below the answer text, not inline.

**Q118. What does the `BookmarkIcon` in history do technically?**
`toggleBookmark(id)` calls `setHistory(prev => prev.map(h => h.id === id ? { ...h, saved: !h.saved } : h))`. Since `history` is in `useEffect` with `localStorage.setItem`, the bookmark is immediately persisted. The History tab's `historyFilter="saved"` filter then shows only `h.saved=true` items.

**Q119. What is `djb2 hash` used for in `getRepoStyle()`?**
djb2 is a simple non-cryptographic hash: `h = ((h << 5) + h) + char_code`. Used to deterministically map a repo name string to an index in `EXTENDED_PALETTE`. The same repo name always maps to the same color — no collision handling needed at this palette size.

**Q120. What is the difference between `chunking with tree-sitter` vs `regex`?**
Tree-sitter builds a full Concrete Syntax Tree — it understands the actual language grammar, handles nested structures, template literals, JSX, decorators correctly. Regex pattern matching is line-based and can misfire on multi-line arrow functions, nested braces in template literals, or complex destruring patterns.

**Q121. Why does `BM25Okapi` work well for symbol name retrieval?**
BM25 is a TF-IDF variant that scores based on term frequency relative to document length and inverse document frequency (how rare the term is). Symbol names like `useDrawingSocket` are: (1) high TF in the specific chunk (symbol repeated 3×), (2) low DF across the corpus (rare). So IDF is very high and the overall BM25 score is very high — BM25 effectively learns that this symbol is highly discriminative.

**Q122. What would break if you removed the `operator.add` annotation from AgentState?**
LangGraph would not know how to resolve concurrent writes. The last writer would win (undefined behavior for parallel branches), silently dropping chunks from 2 of the 3 retrieval nodes. Queries would only return results from one content type.

**Q123. Explain the `Annotated` type hint usage.**
`Annotated[list[dict], operator.add]` is Python's way of attaching metadata to a type hint. The first argument is the actual type (`list[dict]`), the second is arbitrary metadata (`operator.add`). LangGraph reads the metadata to decide how to merge state from parallel branches.

**Q124. What is `sys.path.insert(0, str(Path(__file__).parent.parent))` doing?**
Adds the project root to `sys.path` before the local `config` import. Without this, running ingestion as `python -m ingestion.run_ingestion` from the root works (Python adds root to sys.path), but running `python ingestion/run_ingestion.py` directly would fail to find `config.py`. This line handles both cases.

**Q125. How does single-repo update (isolated re-index) work?**
```
1. _delete_repo_and_reindex(repo_name)
   → strip JSONL chunks for this repo
   → FaissStore.remove_repo_and_save() on all 3 indexes
   → BM25Store.remove_repo_and_save()
   → cache_clear()
2. _ingest_and_index_single_repo(repo_name)
   → subprocess: ingestion --only-repo (git pull + chunk)
   → subprocess: build_indexes (embed + FAISS.add() + BM25 rebuild)
   → cache_clear()
```
Other repos' embeddings are never touched.

**Q126. How does `FaissStore.remove_repo_and_save()` work precisely?**
1. `store.load(path)` — load existing FAISS + metadata
2. `keep_indices = [i for i, chunk in enumerate(store._chunks) if chunk.get("repo") != repo_name]`
3. `kept_vectors = np.array([store._index.reconstruct(i) for i in keep_indices])` — extract raw vectors
4. `new_store = FaissStore(); new_store.add(kept_vectors, kept_chunks); new_store.save(path)` — rebuild and overwrite
5. The key: `remove_repo_and_save` is a class method that doesn't modify the calling instance — it's a pure static operation on files.

**Q127. Why does `BM25Store.remove_repo_and_save()` rebuild the entire BM25 index?**
BM25 `BM25Okapi` is a bag-of-words model that stores inverted token frequency data. Unlike FAISS, there's no concept of "removing a document" — you must rebuild the entire `BM25Okapi` object from the remaining corpus. This is fast (just tokenization + TF-IDF computation, no neural inference).

**Q128. What is `os.walk(topdown=True)` and why does it matter?**
`os.walk` traverses a directory tree. `topdown=True` (default) means the generator yields the current directory before its subdirectories. Crucially, when `topdown=True`, modifying `dirnames` in-place `dirnames[:] = [...]` prevents descending into pruned directories. This is the `SKIP_DIRS` pruning mechanism.

**Q129. How does the `UpdateOverlay` progress tracking work?**
`updateStep` state in `App.jsx` is a number 1–4 (currently not implemented — the overlay always shows all steps without real progress tracking). In the current code, `setUpdatingRepoName(repoName)` shows the overlay, but `updateStep` is not actually incremented through the 4 sub-steps. The overlay is a UI improvement opportunity.

**Q130. What is the `_SYSTEM_NORMAL` prompt doing technically?**
```
Rules:
1. Answer ONLY from provided context — prevents hallucination
2. Cite every claim with [repo/file:line] — structured reference
3. Use commit messages for "WHY" — temporal context
4. Quote exact function names, line numbers
5. If context insufficient, say so — graceful degradation
6. Use markdown headers + code blocks — structured output
```

**Q131. Why is `ChatGroq` instantiated freshly in each `synthesize_answer()` call?**
Python objects have no connection state — creating `ChatGroq(...)` just sets configuration parameters. LangChain's `ChatGroq` client uses `httpx` internally which pools connections. There's no meaningful overhead from re-construction. An alternative would be to create it at module level, but the per-call pattern is clearer for reading.

**Q132. What happens to the session if a synthesizer call fails (Groq API timeout)?**
`graph.invoke(initial_state)` would raise an exception. FastAPI catches it: `except Exception as e: raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")`. Frontend catches it: `setError(err.response?.data?.detail || err.message)`. The conversation history is NOT updated (no answer was produced).

**Q133. If I add 100,000 chunks for one repo, what breaks first?**
Likely RAM. `IndexFlatIP` stores float32 vectors: `100000 × 768 × 4 bytes = ~295MB`. Plus pickle metadata (each chunk dict ~500 bytes): `100000 × 500 = ~50MB`. Total ~350MB just for code index. On an 8GB machine this is fine. The real bottleneck is the embedding step (100K chunks at batch=8 ≈ 12,500 batches × Jina inference time).

**Q134. How would you add a fourth content type (e.g., API documentation)?**
1. Create `ingestion/api_doc_ingester.py` with a `chunk_api_doc()` function
2. Add `API_CHUNKS_FILE` and `API_FAISS_PATH` to `config.py`
3. Add `api_chunks: Annotated[list[dict], operator.add]` to `AgentState`
4. Add `retrieve_api_docs` function to `retrieval_nodes.py`
5. Register it as a node in `graph.py` with edges (route_query → retrieve_api_docs → check_ambiguity)
6. Update router system prompt to include `"api_docs"` as a content type option
7. Update indexing `build_indexes.py` to build the API docs FAISS index

**Q135. What would database indexing look like if you used a real DB?**
Instead of pickled FAISS + JSONL, you'd use PostgreSQL with `pgvector` extension:
- Table `chunks(id UUID, chunk_type, repo, file_path, content, symbol_name, embedding vector(768), ...)`
- `CREATE INDEX ON chunks USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100)`
- Query: `SELECT * FROM chunks ORDER BY embedding <=> query_embedding LIMIT 10`

**Q136. What is the purpose of `conversation_history` being missing from the initial state in eval?**
`eval/run_eval.py` doesn't include `conversation_history` key in `initial_state`. Since `state.get("conversation_history", [])` defaults to `[]`, multi-turn context is disabled in evaluation. This ensures each eval question is answered independently with no cross-contamination.

**Q137. How would you add streaming to the synthesis?**
FastAPI `StreamingResponse` + `async generator`. `ChatGroq.stream()` returns a generator of chunks. Pipe via SSE (Server-Sent Events) or WebSocket to the frontend. Frontend accumulates chunks with `setResult(prev => ({...prev, answer: prev.answer + chunk.content}))`.

**Q138. What is the `pre-filter` pattern in FAISS search?**
Over-fetch (3 × top_k), then post-filter by `repo_filter`. The alternative (pre-filter) would require FAISS to support metadata filtering before distance computation — FAISS doesn't natively support this on `IndexFlatIP`. Systems like Weaviate, Qdrant, and Milvus support pre-filtering via their own metadata systems.

**Q139. Explain the symbiosis between FAISS + BM25 in hybrid retrieval.**
FAISS captures semantic similarity — "show me retry logic" can find a function called `exponential_backoff` even without exact keyword overlap. BM25 captures exact symbol matches — if you search "exponential_backoff" by name, BM25 will score the exact function very highly. Combining both ensures: (1) conceptual queries work via dense, (2) precise name queries work via BM25.

**Q140. What is the `seen_ids` set in `format_citations` for?**
Deduplication. A chunk might be cited both in the LLM answer text (step 1) and added from the all_chunks list (step 2). The `seen_ids` set prevents duplicates: `if cid in seen_ids: continue`. IDs use `chunk["id"]` (UUID4) for the step-2 check and `f"{repo}::{path}::{start}"` for step-1 answer-marker check.

**Q141. Why is there no session-level persistence (database)?**
Design decision for simplicity and privacy. Each user runs CodeAtlas locally with their own repos. Adding a database would require: migration management, connection pooling, backup strategy — unnecessary complexity for a personal tool. `localStorage` for query history is sufficient.

**Q142. How does the `handleKeyDown` handler prevent form submission loops?**
`e.preventDefault()` prevents the `<input>`'s default Enter key behavior (form submission if inside a form). Then `handleQuery()` is called manually. Since the input is not inside a `<form>` element, this is mostly defensive coding.

**Q143. What is `React.StrictMode` in `main.jsx` doing?**
In development, React StrictMode renders components twice to detect side effects. It also warns about deprecated lifecycle methods and legacy refs. Has no effect in production build.

**Q144. What is `useRef` used for in `CitationPopover`?**
`ref={ref}` attaches the ref to the popover's wrapping `<span>`. In the `mousedown` event listener: `if (ref.current && !ref.current.contains(e.target)) setOpen(false)` — if the click target is outside the popover DOM node, close the popover. `ref.current` gives direct access to the DOM element without triggering re-render.

**Q145. Why `axios` over native `fetch`?**
Automatic JSON parse (no `response.json()` needed), better error objects (`err.response.data.detail` readable), easier request/response interceptor support, `axios.get/post/delete` semantic clarity. For this project's scope, `fetch` would work equally well.

**Q146. What is `Promise.all` used for in `loadSystemInfo`?**
```javascript
const [reposRes, healthRes] = await Promise.all([
  axios.get('/repos').catch(() => null),
  axios.get('/health').catch(() => null),
])
```
Both API calls run simultaneously (parallel). If either fails, `.catch(() => null)` prevents the Promise.all from failing — both results are checked independently.

**Q147. How does the `historyFilter` work with `historySearchQuery`?**
```javascript
history
  .filter(h => historyFilter === 'saved' ? h.saved : true)
  .filter(h => !historySearchQuery || h.query.toLowerCase().includes(historySearchQuery.toLowerCase()))
```
Two sequential filters: first by saved/all, then by search text. Combined with `Array.filter` chaining — filtering only matters when `historySearchQuery` is non-empty (short-circuit `||`).

**Q148. Explain the `selectedHistoryIds: Set<number>` pattern.**
JavaScript `Set` is used for O(1) lookup (`has(id)`), insertion (`add(id)`), and deletion (`delete(id)`). React state with a `Set` requires creating a new Set on each update (`new Set(prev)`) because React compares state by reference equality — mutating the existing Set wouldn't trigger re-render.

**Q149. What is `bulkSave(ids)` doing?**
Sets `saved: true` on all selected history items: `setHistory(prev => prev.map(h => ids.has(h.id) ? {...h, saved: true} : h))`. Immutable update pattern — creates a new array with the modified items.

**Q150. What performance overhead does `JSON.parse(localStorage.getItem('kb_query_history') || '[]')` have on mount?**
Minimal — `localStorage` is synchronous and in-memory (not disk I/O in modern browsers). JSON.parse of 50 history items is microseconds. The lazy initializer `useState(() => {...})` runs only once on mount.

**Q151–Q200:** (Continued with architecture deep-dives, complex scenarios, advanced internals — see Advanced section below for the hardest 100.)

---

## Advanced (100 Questions)

**Q201. Design the system from scratch. What would you change architecturally?**
1. Replace JSONL+FAISS+pickle with PostgreSQL+pgvector for ACID guarantees and query flexibility
2. Move Jina inference to a dedicated model-serving sidecar (TorchServe or vLLM) — prevents main API from OOM-killing
3. Add a job queue (Celery + Redis) for async ingestion — `/repos/add` returns immediately, job processes in background
4. Implement webhook-based incremental indexing (GitHub webhooks → only re-index modified files)
5. Add proper auth (JWT + refresh tokens) for team use

**Q202. How would you handle a 1,000 repo enterprise use case?**
- **Indexing:** Distribute across multiple workers (Ray, Celery, AWS Batch). One worker per repo, results aggregated.
- **FAISS:** Switch to `IndexIVFPQ` (Inverted File + Product Quantization) — 16-32x memory reduction with ~95% recall. Or use Milvus/Qdrant which have native distributed vector search.
- **Retrieval:** Add a pre-filter step using repo metadata (team, language, last modified) to narrow the search space before embedding.
- **LLM:** Rate limiting, token counting, cost tracking per user/team.

**Q203. What are the failure modes of the ambiguity detector?**
1. **False positive:** Two repos happen to implement similar-sounding but unrelated functions (e.g., both have a `parse()` function). Top-6 chunks span 2 repos → incorrectly flagged as ambiguous.
2. **False negative:** One repo has 9 highly-relevant chunks; the other repo's chunk is ranked #10. Ambiguity check only looks at top-6 → flag missed.
3. **Threshold sensitivity:** `AMBIGUITY_MIN_REPOS=2` is a hard threshold. A single chunk from a "noise" repo in position 5 could trigger the flag.
**Fix:** Compute actual embedding similarity between top chunks from different repos. If semantic similarity > threshold, flag as ambiguous. This would require storing query embedding in state and comparing against chunk embeddings.

**Q204. Explain why `IndexFlatIP` with L2-normalization is equivalent to cosine similarity.**
Cosine similarity: `cos(θ) = (A · B) / (|A| × |B|)`. If `|A|=|B|=1` (unit vectors), then `cos(θ) = A · B`. FAISS `IndexFlatIP` computes exactly `A · B` (inner product). Jina's `normalize_embeddings=True` applies L2 normalization: `v_norm = v / ||v||_2` making `||v_norm||_2 = 1`. Therefore, `IndexFlatIP` score = cosine similarity score.

**Q205. What are the tradeoffs of using a flat FAISS index vs HNSW?**
| | IndexFlatIP | IndexHNSWFlat |
|---|---|---|
| Build time | O(N), instant | O(N log N) — graph construction |
| Search time | O(N·D) brute force | O(log N · D) approximate |
| Memory | N·D·4 bytes | N·D·4 + graph edges |
| Recall | 100% | 95-99% (tunable) |
| Suitable for | < 100K vectors | > 100K vectors |
| Mutations | Trivial | Complex (rebuild needed) |

For CodeAtlas's scale (a few thousand chunks), `IndexFlatIP` is strictly better — faster to build, same search time, perfect recall.

**Q206. Explain the time and space complexity of the hybrid re-ranking.**
```
Time:
  FAISS search: O(N·D) where N=total chunks, D=768 (brute force)
  BM25 scoring: O(Q·N) where Q=query tokens, N=candidate set (10)
  Normalization + sort: O(K log K) where K=10
  Total: O(N·D) dominated by FAISS
Space:
  FAISS index: O(N·D) = O(768N) float32 = 3KB per chunk
  Metadata: O(N·M) where M=chunk dict size ≈ 500 bytes
  BM25 model: O(V·N) where V=vocabulary size ≈ some MB
```

**Q207. Why doesn't CodeAtlas use vector databases like Pinecone, Weaviate, or Qdrant?**
Design decision: local-first, offline-capable, zero cloud dependencies (beyond Groq). FAISS + pickle achieves the same functionality for a personal tool. Pinecone would add: managed infrastructure cost, internet dependency for every query, vendor lock-in. Qdrant/Milvus would be appropriate for a larger-scale or team deployment.

**Q208. How would you implement exact match retrieval for function names?**
Currently approximated via BM25 Okapi with 3× symbol repetition. For exact match:
1. Build a separate inverted index: `{symbol_name: [chunk_id, ...]}`
2. For queries matching exact function name patterns, bypass embedding entirely and return exact match results directly
3. Merge with semantic results using RRF (Reciprocal Rank Fusion)

**Q209. Explain Reciprocal Rank Fusion (RRF) as an alternative to linear interpolation.**
`RRF_score(d) = Σ (1 / (k + rank_i(d)))` where k=60 (tunable constant) and rank_i is the position of document d in ranked list i. RRF is more robust than linear interpolation because it doesn't require score normalization — ranks are naturally bounded. Empirically shown to outperform linear interpolation on most retrieval benchmarks.

**Q210. What's wrong with the current evaluation methodology?**
1. **20 questions is tiny** — insufficient statistical power; variance between runs is high
2. **Ground truth is manual** — subjective, may not reflect real user intent
3. **Single-run evaluation** — Groq's `temperature=0` should be deterministic, but should still run 3× for reliability
4. **File hit rate uses substring matching** — "router" matches "router.py" but also "error_router.py" — imprecise
5. **No semantic answer quality** — just checks for non-empty response and absence of error phrases
**Better:** Use LLM-as-judge for answer quality, larger synthetic question set generated from known code facts, semantic similarity for file path matching.

**Q211. How would you implement reranking with a cross-encoder?**
A cross-encoder (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) takes `(query, document)` pairs and outputs a relevance score:
```python
from sentence_transformers import CrossEncoder
ce = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
pairs = [(query, chunk["content"]) for chunk in top_10_chunks]
scores = ce.predict(pairs)
reranked = sorted(zip(top_10_chunks, scores), key=lambda x: x[1], reverse=True)[:5]
```
This would replace the FAISS→BM25 hybrid with FAISS→CrossEncoder. More accurate but ~10x slower (cross-encoder is O(K) inference calls for K candidates).

**Q212. Describe the exact token flow through the LLM synthesis call.**
```
System message:  ~200 tokens (_SYSTEM_NORMAL)
User message (breakdown):
  Prior conversation: last 3 turns × avg 150 tokens = ~450 tokens
  Question: ~20 tokens
  Code chunks: 5 × 375 tokens (1500 chars / 4 chars per token) = ~1875 tokens
  Commit chunks: 5 × 50 tokens (200 chars) = ~250 tokens
  README chunks: 3 × 200 tokens (800 chars) = ~600 tokens
  Prompt boilerplate: ~100 tokens
Total input: ~3495 tokens (well under 32K context)
Max output: 2048 tokens
```

**Q213. What is the risk of pickle for storing chunk metadata and how would you mitigate it?**
`pickle.load()` executes arbitrary Python code during deserialization — a malicious `.meta` file could achieve remote code execution. Risk is low here (local only, user controls the data), but for team/cloud deployment: replace pickle with JSON serialization (`json.dump/load`). FAISS binary format itself is safe (pure C float array).

**Q214. How would you implement webhook-triggered incremental indexing?**
```
GitHub repo push → GitHub webhook → POST /repos/{name}/refresh
→ FastAPI: start background task (asyncio or Celery)
→ Background: git pull → _get_changed_files_since_last_sync()
→ Only chunk changed .py/.js/.ts files (not whole repo)
→ Remove old FAISS vectors for those files (by file_path)
→ Add new vectors for updated chunks
→ Save updated indexes
→ cache_clear()
```
Challenge: `IndexFlatIP` doesn't support deletion by metadata — must reconstruct (same pattern as `remove_repo_and_save()`).

**Q215. Explain the `git clone --depth 500` tradeoff.**
`--depth N` creates a shallow clone — only N commits of history. Benefits: much faster clone, smaller disk usage. Downsides: `git log` history is limited to N commits; git operations that need full history (merge, rebase) may fail. The ingester also caps at `MAX_COMMIT_HISTORY=500` anyway, so depth=500 is a well-matched choice.

**Q216. What is the LangChain `ChatGroq` doing under the hood?**
`ChatGroq` inherits from `BaseChatModel`. `.invoke([SystemMessage, HumanMessage])` calls the Groq API's `/openai/v1/chat/completions` endpoint (OpenAI-compatible). It serializes messages to `[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]`, POST to Groq, and deserializes the response into a `ChatMessage` with `.content`.

**Q217. What would happen if two concurrent users sent queries at the same time?**
FastAPI is async — `async def query_endpoint()` runs in the event loop. `graph.invoke()` is synchronous, so it would block the event loop for ~10 seconds. Two concurrent queries would queue behind each other in the same thread. Fix: `await asyncio.run_in_executor(None, graph.invoke, initial_state)` to run the synchronous LangGraph call in a thread pool.

**Q218. How does LangGraph handle exceptions inside nodes?**
LangGraph propagates exceptions from nodes to the caller of `graph.invoke()`. If `synthesize_answer()` throws a `GroqException`, it bubbles up through `graph.invoke()` to the FastAPI `try/except Exception as e: raise HTTPException(500)` wrapper. There's no built-in node-level retry in this graph — future improvement: add `RetryPolicy` at the LangGraph level.

**Q219. What is the `AllKeyError` problem in `route_query` and how is it handled?**
If `parsed.get("routed_repos")` returns a list containing a repo name that doesn't exist in `available_repos`, the validation step `[r for r in routed_repos if r in available_repos]` would return an empty list. The `or available_repos` fallback ensures at least all-repos is used: `routed_repos = [...] or available_repos`.

**Q220. How would you add A/B testing for different prompt strategies?**
Track `strategy_version` in the feedback record. Test two prompts: A (current) and B (e.g., more concise). Route 50% of requests to each via `random.random() < 0.5`. After 100 rated queries, compare thumbs-up rates per strategy. Adjust accordingly.

**Q221. Explain the `_system_prompt.format(repos_list=repos_str)` security concern.**
If `available_repos` contained a repo named `"}}\n\nIgnore all previous instructions..."`, it would be injected into the system prompt as: `Available repos: ["}}\n\nIgnore all..."]`. This is a prompt injection via the repo name field. Fix: validate repo names (alphanumeric + hyphens only) in `/repos/add` endpoint before accepting them.

**Q222. What is the memory leak risk in the retrieval nodes?**
`@lru_cache(maxsize=1)` on module-level functions means FAISS indexes are kept in memory for the process lifetime. If indexes are rebuilt while the server is running (via `/repos/add`), `cache_clear()` is called, and the old FAISS objects are garbage collected — no leak. The risk would be if `cache_clear()` was forgotten.

**Q223. How would you implement confidence scores in the final answer?**
1. Expose `scores` from retrieval nodes in AgentState
2. Average top-K retrieval scores as a "retrieval confidence" (0–1)
3. Ask the LLM to self-rate its confidence in the synthesis prompt
4. Combine: `final_confidence = 0.7 * retrieval_conf + 0.3 * llm_conf`
5. Display as a colored badge in the UI (green >0.8, yellow 0.5–0.8, red <0.5)

**Q224. Why `uuid.uuid4()` for chunk IDs vs deterministic hashes?**
`uuid4()` is random — same chunk ingested twice would get different IDs. Pros: always unique, no hash collision risk. Cons: re-ingesting the same repo creates new IDs — `_remove_repo_from_jsonl` + re-append means old citations could reference IDs that no longer exist in the index. A deterministic hash `hash(repo + file_path + start_line + content[:50])` would enable idempotent re-ingestion but risks hash collisions.

**Q225. How is the `star_line` vs `lineno` numbering alignment maintained?**
Python AST `node.lineno` is 1-indexed. `_extract_source_lines(lines, start, end)` uses `lines[start - 1 : end]` (0-indexed slice with 1-index adjustment). The resulting chunk has `start_line=node.lineno` (1-indexed). The citation `[repo/file:start_line]` in the LLM output is also 1-indexed. User sees "line 42" in the citation. If the user opens the file in an editor (also 1-indexed), they find the code at line 42. ✓

**Q226. Explain the BM25Okapi hyperparameters `k1=1.5, b=0.75`.**
BM25Okapi's default hyperparameters: `k1=1.5` (term saturation — controls how much repeated terms matter; higher = more emphasis on TF), `b=0.75` (length normalization — how much document length affects score; 0=no normalization, 1=full normalization). Code chunks are relatively uniform in length, so `b=0.75` is reasonable. CodeAtlas uses `rank-bm25` defaults without customization.

**Q227. What would happen if `EMBEDDING_BATCH_SIZE=1` vs `32`?**
`batch_size=1`: Jina model processes one chunk at a time. For 1000 chunks: 1000 forward passes. Slower but minimal RAM usage. `batch_size=32`: 32 chunks per forward pass. For 1000 chunks: 32 forward passes. ~30x faster but uses `32 × 768 × 4 bytes × sequence_len` more RAM. Current `batch_size=8` is a compromise for 8GB RAM machines.

**Q228. If a Python file has only `import` statements, what happens?**
`ast.parse(source)` succeeds. `ast.iter_child_nodes(tree)` yields only `Import`, `ImportFrom` nodes. The `_ChunkVisitor` only handles `FunctionDef`, `AsyncFunctionDef`, `ClassDef` — `visitor.chunks` remains `[]`. The check `if not visitor.chunks: return _sliding_window_chunks(...)` fires → file is chunked as a 50-line sliding window. The chunk content is the import block — useful for finding "where is module X imported from?"

**Q229. How does the feedback loop close — how does `feedback.jsonl` improve the system?**
Currently it doesn't — the feedback is recorded but never used. Future pipeline: (1) Load feedback.jsonl, (2) Extract (query, answer, rating) triples, (3) For thumbs-down: flag for manual review or fine-tuning data. (4) Build a RAG evaluation set from thumbs-up rated answers for automated regression testing. (5) Fine-tune a smaller LLM (e.g., Llama 3.1 8B) on the rated pairs for domain adaptation.

**Q230. What is the `ProcessPoolExecutor` vs `ThreadPoolExecutor` choice for async ingestion?**
`ProcessPoolExecutor`: True parallelism, separate memory spaces, avoids Python GIL. Preferred for CPU-bound embedding inference. Downside: higher overhead per task, no shared memory.
`ThreadPoolExecutor`: Thread-level parallelism, shared memory, limited by GIL for CPU-bound tasks. Better for I/O-bound tasks (git operations, file reading).
For CodeAtlas ingestion: best to use `ProcessPoolExecutor` for the Jina embedding step (CPU bound) and thread pool for file walking + git operations (I/O bound).

**Q231. Explain how LangSmith tracing captures LangGraph execution.**
LangChain's callback system (`CallbackManager`) intercepts every LangGraph node execution and LLM call. When `LANGCHAIN_TRACING_V2=true`, a `LangSmithCallbackHandler` is injected. It posts trace data (node name, inputs, outputs, timing, token counts) to `api.smith.langchain.com`. The dashboard shows a tree view of the execution: route_query → [retrieve_code, retrieve_commits, retrieve_readme] → check_ambiguity → synthesize_answer → format_citations.

**Q232. What happens if `repos.json` contains a URL to a private GitHub repo?**
`git clone` will fail with an authentication error (no credentials configured). Fix: Support GitHub Personal Access Tokens — accept `url` as `https://TOKEN@github.com/user/repo` and store the token (masked) in repos.json. Or support SSH URLs if the user's SSH key is configured.

**Q233. How would you implement semantic similarity deduplication before indexing?**
Compute all chunk embeddings → build a temporary FAISS index → for each chunk, check if top-1 neighbor has similarity > 0.95 → if yes, skip (it's a near-duplicate). Useful for repos that include vendored code or have many similar functions. Cost: O(N log N) instead of O(N) indexing — acceptable for large repos.

**Q234. What is the `star` rating scheme vs `up/down` for feedback and when would you prefer each?**
`up/down (binary)`: Simpler, higher response rate, clearer signal (like/dislike). Good for: "was this answer useful?" `star (1-5)`: More nuanced, can distinguish "bad" from "mediocre" from "great". Good for: "rate the quality of this answer" with different failure mode categories. For CodeAtlas, thumbs up/down is appropriate — users care binary: "did it find my code? yes/no."

**Q235. Explain the `SearchIcon`, `HistoryIcon`, `FolderIcon` choices for navigation.**
`SearchIcon` → "Ask" tab (searching through code). `HistoryIcon` → "History" tab (past queries). `FolderIcon` → "Repositories" tab (code repositories are conceptually folders). These are semantic icon selections from Material Icons, not arbitrary. The `@mui/icons-material` package provides SVG icons as React components.

**Q236. How does the `history.length > 50` truncation work?**
`setHistory(prev => [historyItem, ...prev.slice(0, 49)])`. `prev.slice(0, 49)` keeps max 49 existing items. Adding `historyItem` at front gives max 50 items total. FIFO — oldest items are dropped first. `localStorage` has a 5MB quota per origin; 50 history items (each ≤ ~10KB) ≈ 500KB — well within quota.

**Q237. Why is `GROQ_MODEL_FAST` defined but not used?**
Anticipatory design — a "cheap pre-filter" use case was planned (maybe using the fast model to quickly categorize query type before routing) but not yet implemented. The constant exists to avoid hardcoding the fast model name later. Good `config.py` hygiene.

**Q238. How would you add multi-language support (Go, Rust, Java)?**
1. Verify `tree_sitter_go`, `tree_sitter_rust`, `tree_sitter_java` packages exist
2. Add `.go`, `.rs`, `.java` to `SUPPORTED_CODE_EXTENSIONS` in config
3. Create `go_chunker.py`, `rust_chunker.py`, `java_chunker.py` (same interface as `js_chunker.py`)
4. Update `run_ingestion.py` to dispatch by extension
5. The embedding model (`jina-embeddings-v2-base-code`) already supports Go, Rust, Java — no change needed there

**Q239. What does `batch_size=8` imply about GPU vs CPU inference?**
`EMBEDDING_BATCH_SIZE=8` is CPU-optimal. GPU-optimal batches are typically 32–512 (larger batches better utilize GPU parallelism). The comment in config: "Reduced to 8 to prevent Linux OOM killer on 8GB RAM" — confirms this is a CPU setup. On a GPU machine with 16GB VRAM, you could safely use `batch_size=64` for ~8× throughput improvement.

**Q240. How would you implement a RAG quality guardrail?**
After synthesis: (1) Parse all `[repo/file:line]` citation markers from the answer. (2) Check each against the `chunk_lookup` in `format_citations`. (3) If any citation doesn't match a retrieved chunk → it's hallucinated. (4) Strip or mark hallucinated citations with a warning badge. (5) Lower answer confidence score.

**Q241. Describe the O(1) vs O(N) lookup in citation formatter.**
`chunk_lookup: dict[tuple, dict] = {(repo, file_path, start_line): chunk}` is built once before the citation parse loop → O(1) per lookup. Without this dict, each citation marker would require a linear scan: `next((c for c in all_chunks if c["repo"]==repo and c["file_path"]==path and c["start_line"]==start), None)` = O(N) per lookup.

**Q242. What's wrong with the `processAnswerText` function (frontend)?**
It returns `answerText` unchanged. The function builds `citationMap` but never uses it to transform the text. The intended behavior — replacing `[repo/file:line]` markers with `<CitationPopover>` components — is stubbed out. This is a code quality issue / dead code. The citation popovers are shown in a separate section below the answer, not inline.

**Q243. Explain the djb2 hash collision risk for repo colors.**
`EXTENDED_PALETTE` has 5 colors. With many repos, hash collisions are expected (pigeonhole principle — 5 slots, any N>5 repos will have collisions). Two repos could get the same color. This is acceptable — colors are visual differentiation aids, not unique identifiers. Repo names are shown separately. If uniqueness mattered, you'd use a set of picked colors and assign sequentially.

**Q244. Suggest 5 specific improvements to the chunking quality.**
1. **Import tracking:** Include file-level imports as a comment in each chunk — helps LLM understand dependencies
2. **Docblock cleaner:** For JSDoc/pydoc with @param/@return, parse and include in chunk header
3. **Cross-reference injection:** Add "called by: [funcB, funcC]" comments from call graph analysis
4. **Deduplication:** Skip near-identical chunks (similarity > 0.95) before indexing
5. **Dynamic window sizing:** Instead of fixed 50 lines, use indentation depth to detect logical blocks

**Q245. How would you handle a 10GB monorepo?**
1. **File-level incremental hashing:** Only re-chunk files whose SHA256 has changed since last ingestion
2. **Streaming JSONL write:** Don't accumulate all chunks in memory — write each chunk immediately
3. **Parallel chunking:** `concurrent.futures.ProcessPoolExecutor` with one worker per repo/file-type pair
4. **Distributed FAISS:** Use `IndexIVFFlat` or move to Milvus with sharding
5. **Priority indexing:** Index only recently modified files first (`git log --since="30 days ago"`)

**Q246. What would you use instead of pickle for the FAISS metadata if security was critical?**
JSON with a defined schema: `json.dumps(chunks, default=str)` → safe, human-readable, language-agnostic. For binary efficiency: MessagePack or Protocol Buffers. These have no code execution risk unlike pickle.

**Q247. How would you implement "search by file" (find all code in file X)?**
Dedicated endpoint: `GET /file?repo=MyRepo&path=src/auth/middleware.py`. Backend: load `code_chunks.jsonl`, filter by `repo + file_path` match. No embedding needed — pure metadata filtering. Return all chunks for that file, sorted by `start_line`. Fast O(N) scan over JSONL (or O(1) if you build a file→chunk inverted index).

**Q248. Explain why the graph uses `builder.compile()` instead of raw Python functions.**
`builder.compile()` creates a `CompiledGraph` that: (1) validates graph topology (no cycles in non-tool nodes, all referenced nodes exist), (2) enables checkpointing for long-running workflows, (3) integrates with LangSmith tracing automatically, (4) supports `graph.stream()` for streaming execution, (5) can be serialized for distributed execution. Raw Python functions would require manual orchestration of parallelism and state management.

**Q249. How does the ambiguity checker compare to MMR (Maximal Marginal Relevance)?**
MMR: selects diverse results by maximizing similarity to query while minimizing similarity to already-selected results. Goal: diversity of retrieved chunks.
Ambiguity checker: specifically detects if diverse chunks come from different repos implementing the same concept. Goal: cross-repo conflict detection.
They're complementary — MMR would help retrieve more diverse chunks; the ambiguity checker interprets what that diversity means.

**Q250. If you had 6 more months, what would you build first?**
1. **Webhook ingestion** — real-time index updates on push (most impactful for daily use)
2. **Cross-encoder reranking** — dramatically improves file hit rate (current bottleneck)
3. **Streaming synthesis** — reduce perceived latency from 11s to first-token in 2s
4. **Multi-repo answer diffing** — visual side-by-side code comparison for ambiguity mode
5. **Code graph indexing** — call graph + import graph to enable "what calls this function?" queries
6. **Fine-tuned router** — replace Groq LLM routing with a tiny local classifier (TinyBERT) for sub-100ms routing latency

**Q251–Q300:** (Additional advanced topics covered in the Difficult Interview Questions section below.)

---

# 25. Why This Approach?

## Technology Choices

| Choice | Alternative | Why We Chose This |
|---|---|---|
| **Groq + Llama 3.3 70B** | OpenAI GPT-4, Anthropic Claude | Ultra-fast inference (10-100x vs OpenAI), free tier available, open-source model |
| **FAISS (flat local)** | Pinecone, Weaviate, Qdrant | Zero cloud cost, offline-capable, full control, adequate for personal-scale |
| **Jina Code Embeddings** | OpenAI `text-embedding-ada-002`, Cohere | Code-specific model (trained on code), local (no API cost per embedding), 768-dim vs 1536-dim (half the FAISS memory) |
| **BM25 (hybrid)** | Dense-only, Reranker | Cheap, fast, excellent for exact symbol name matching that dense embeddings miss |
| **LangGraph** | CrewAI, AutoGen, raw Python | Explicit graph topology, built-in fan-out, typed state, LangSmith integration, more control than agents-based frameworks |
| **FastAPI** | Flask, Django REST | Async-ready, Pydantic validation built-in, OpenAPI docs automatic, modern Python with type hints |
| **React + Vite** | Next.js, Vue, Svelte | Simplest SPA setup, no SSR needed (all data fetched from API), Vite is fastest dev server |
| **JSONL for chunks** | SQLite, PostgreSQL | Append-friendly, simple, no ORM needed, human-readable for debugging |
| **tree-sitter** | esprima, acorn, regex | Handles JSX, TSX, decorators, template literals correctly; reliable C implementation |
| **Python `ast`** | `inspect`, `tokenize`, regex | Built-in, reliable, gives exact line numbers, works for all valid Python files |
| **GitPython** | subprocess git commands, pygit2 | High-level Pythonic API, handles edge cases (bare repos, embedded repos), comprehensive commit metadata |

## Why LangGraph instead of CrewAI?
- **CrewAI:** Role-based agents with delegation. Better for autonomous multi-step tasks with agents that collaborate through messages.
- **LangGraph:** Explicit graph topology with typed state. Better for deterministic pipelines with known execution order. CodeAtlas's pipeline is fixed (route → retrieve → check → synthesize → format) — not an autonomous agent reasoning loop.

## Why not use an all-in-one RAG framework like LlamaIndex?
LlamaIndex provides: document loaders, chunkers, vector stores, query engines. CodeAtlas uses all these components but implements them from scratch for:
1. Full control over chunk schema (custom git commit fields)
2. Custom hybrid re-ranking logic
3. Multi-index architecture (3 separate FAISS indexes)
4. In-place deletion and isolated re-indexing
LlamaIndex would abstract these details away, making customization harder.

---

# 26. Tradeoffs

## Advantages
- **Local-first:** All computation (except Groq LLM calls) is on-device. Privacy for proprietary code.
- **Exact citations:** `[repo/file:line]` tied to ground-truth chunk metadata, not hallucinated.
- **Multi-index design:** Code, commits, and docs indexed separately → better relevance per query type.
- **Isolated re-indexing:** Add/remove/update one repo without touching others.
- **No database overhead:** FAISS + pickle is lightweight, no running database process needed.

## Disadvantages
- **Cold start:** First Groq LLM call takes ~2-3s. FAISS index loading on first query takes ~1-2s.
- **Memory footprint:** Jina model (~550MB RAM when loaded), FAISS index (~3KB per chunk) — all kept in process memory.
- **Sequential synthesis:** `synthesize_answer` is a serial bottleneck — ~8-10s per query.
- **No real-time updates:** Index is stale until manual re-ingestion. No webhook integration yet.
- **GPU not used:** Jina inference on CPU — 10-30x slower than GPU inference.
- **Single-language chunkers:** Only Python and JS/TS have AST chunking; other languages fall back to regex or sliding window.
- **Groq API dependency:** LLM functionality offline unavailable.

## Scalability
- **100 users:** Current design works if deployed on a server (uvicorn with uvicorn workers). Need to add auth and session management.
- **10K users:** Needs distributed Jina inference (vLLM or TorchServe sidecar), async job queue for ingestion, PostgreSQL + pgvector instead of FAISS flat. Groq rate limits become a concern (need API key pool or batch routing).
- **1M users:** Full distributed system: Kubernetes, Qdrant/Milvus cluster, Kafka for ingestion events, Redis for session/cache, CDN for static frontend.

---

# 27. Production Improvements

If given 6 more months:

1. **Webhook-triggered incremental indexing** — GitHub webhooks → only re-chunk modified files, O(changed_files) instead of O(total_files)
2. **Cross-encoder reranking** — Replace FAISS+BM25 hybrid with FAISS+CrossEncoder for 15-20% better file hit rate
3. **Streaming synthesis** — FastAPI `StreamingResponse` + Groq streaming API for first-token latency of ~1s instead of 11s full response
4. **Persistent conversation memory** — SQLite or Redis for cross-session conversation threads, not just session-level
5. **Team authentication** — GitHub OAuth, JWT, and team-level access control for shared team codebases
6. **GPU deployment option** — Docker container with CUDA support for Jina inference (10-30x faster indexing)
7. **Call graph indexing** — Parse import graphs and function call chains; enable queries like "what functions call authenticate()?"
8. **Visual code attribution** — VS Code extension version: hover over a function → show who last modified it and related implementations across repos
9. **Automated eval in CI** — GitHub Actions: run `eval/run_eval.py` on every push, fail PR if metrics drop below threshold
10. **Fine-tuned small router** — Replace Groq LLM routing (slow: ~1-2s + network) with a local TinyBERT classifier (fast: ~50ms, no API cost)

---

# 28. Scalability

## 100 Users
- **Current architecture works** with minor changes:
  - Single FastAPI server with `uvicorn --workers 4`
  - Auth: add JWT middleware
  - Rate limit: 10 queries/user/minute (token-bucket)
  - Session management: Redis for conversation history
  - Groq API key: current LLM cost manageable

## 10,000 Users
- **Backend:** Kubernetes deployment, 3+ FastAPI replicas behind load balancer (nginx or Traefik)
- **Vector DB:** Replace FAISS with Qdrant (horizontal scaling, filtering support)
- **Embedding:** vLLM or Python threading sidecar for Jina (multiple replicas)
- **Caching:** Redis layer — cache (query, repo_filter) → (answer, citations) for repeated queries
- **Async ingestion:** Celery + Redis queue for ingestion jobs
- **Database:** PostgreSQL for user management, feedback, indexed repo metadata

## 1,000,000 Users (Hypothetical)
- **Multi-region deployment:** AWS/GCP with regional FAISS/Qdrant clusters
- **LLM:** Self-hosted Llama 3.3 70B on GPU instances (cost >> Groq API at this scale)
- **Sharded vector search:** Partition by repo/team — query only relevant shard
- **CDN:** CloudFront for static React assets
- **Read replicas:** FAISS read-only replicas, single write master for updates
- **Event-driven:** Kafka streams for ingestion events, analytics

---

# 29. Common Bugs & Edge Cases

## Race Conditions
- **Delete during query:** User deletes repo while a query is in-flight reading from that repo's FAISS index. The `@lru_cache` holds the old index in memory — the query completes successfully. The cache is cleared after deletion, so the next query sees the updated index. ✓ Safe.
- **Concurrent `/repos/add` calls:** Two users add repos simultaneously → both `subprocess.run` ingestion calls run in parallel → both write to the same JSONL files → potential JSONL corruption. Fix: file-level locking (`fcntl.flock`) or serialized job queue.

## Memory Leaks
- **Jina model never unloaded:** `Embedder._instance` lives for process lifetime. If you call `/repos/add` 100 times, the same model stays in RAM — no leak. But if you spawn new ingestion processes (via subprocess), each subprocess exits after ingestion and their models are garbage collected. ✓

## API Failures
- **Groq rate limit (429):** `ChatGroq.invoke()` raises a `langchain.exceptions.APIError`. FastAPI catches it as `Exception` → HTTP 500 to client. Fix: add retry with exponential backoff using `tenacity`.
- **Groq network timeout:** Same pattern. Fix: `ChatGroq(timeout=30)` + retry.

## Edge Cases
- **Empty FAISS index:** `n_total = self._index.ntotal; if n_total == 0: return []` — handled. An empty search would crash FAISS otherwise.
- **Python 2 syntax in target repo:** `ast.parse()` raises `SyntaxError` → fallback to sliding window. ✓ Handled.
- **No functions in Python file:** `visitor.chunks == []` → fallback to sliding window. ✓ Handled.
- **Commit with no changed files:** `changed_files = []` → `primary_file = None`. `file_path=None` in chunk. Commit chunk works but contributes nothing to file-hit scoring.
- **Very long function (1000+ lines):** AST captures exact boundaries → one chunk with 1000+ lines. `content[:1500]` in synthesis prompt truncates it. Full content is in FAISS (affects embedding quality for long functions).
- **Unicode in code files:** `file_path.read_text(encoding="utf-8", errors="replace")` — errors='replace' substitutes malformed bytes with '?' instead of crashing.
- **Repo name with spaces:** `repos.json` allows any string as `name`. Spaces in repo names are URL-encoded in endpoint paths (`encodeURIComponent()`), but JSONL filtering uses `.lower()` string comparison — spaces are preserved and compared correctly.

---

# 30. Resume Explanation

**CodeAtlas — Personal Codebase Knowledge Agent** | Python, LangGraph, FastAPI, React, FAISS, Groq LLM

Built a multi-agent Retrieval-Augmented Generation (RAG) system enabling natural language querying over multiple personal GitHub repositories. Implemented AST-aware code chunking (Python `ast` + tree-sitter for JS/TS), hybrid FAISS+BM25 vector retrieval (60/40 dense/sparse fusion), and a LangGraph StateGraph orchestrating parallel cross-index retrieval with cross-repo ambiguity detection. Achieved 89% repository-hit rate and 100% answer quality on a 20-question benchmark suite with grounded `[repo/file:line]` citations. Features a React+Vite SPA with session multi-turn conversation memory and zero-downtime single-repo isolated re-indexing.

---

# 31. HR Round Explanation

**"I built an AI-powered search engine for my own code projects."**

Imagine you've worked on 10 different software projects over 2 years. One day you need to find some code you wrote — authentication, or database setup — but you don't remember which project it's in. You could search through all 10 projects manually, which takes 30 minutes. Or you could just ask CodeAtlas: *"Where have I implemented user authentication?"* — and it finds the exact file, line number, and even shows you the git commit where you originally wrote it, all in under 15 seconds.

It's like Google Search, but for your own private code. You talk to it in plain English, and it gives you specific, verifiable answers — not just "probably in file X" but "definitely in `LearnSphere/src/auth/middleware.py`, line 42, function `verify_token`, written on March 15th."

I built the entire system — the AI backend, the search engine, the website — myself, in Python and JavaScript.

---

# 32. Technical Interview Explanation

"CodeAtlas is a multi-agent RAG pipeline that indexes multiple code repositories into a hybrid vector+keyword search system and exposes natural language querying via a FastAPI REST API and React SPA.

**Ingestion phase:** For each configured repo, I walk the file tree (skipping noise dirs like `node_modules`), parse Python files with the built-in `ast` module to extract function/class boundaries with exact line numbers, parse JS/TS with tree-sitter for the same, extract git commit history via GitPython, and chunk README sections by Markdown headings. All chunks are stored as JSONL.

**Indexing phase:** I run Jina Code Embeddings (`jina-embeddings-v2-base-code`, 768-dim) locally via SentenceTransformers to produce L2-normalized float32 vectors. These go into three FAISS `IndexFlatIP` indexes (code, commits, readme) plus a `BM25Okapi` index for code.

**Query phase:** A LangGraph StateGraph runs 7 nodes. The router node calls Groq Llama 3.3 70B to classify which repos and content types to search. Three retrieval nodes run in parallel via LangGraph's fan-out pattern — code retrieval does FAISS then BM25 hybrid re-ranking (0.6 dense + 0.4 sparse). An ambiguity checker flags cross-repo conflicts. The synthesizer calls Groq with retrieved context for a grounded, cited answer. A citation formatter ground-truths all citations against real chunk metadata.

**Results:** 89% repo-hit rate, 100% answer quality on 20 ground-truth questions, ~11s end-to-end latency."

---

# 33. System Design Round

## High-Level Design

**Functional Requirements:**
- Index multiple code repos (code files, commit history, documentation)
- Accept natural language queries
- Return cited answers with `[repo/file:line]` references
- Support CRUD on indexed repos
- Detect when the same concept exists in multiple repos

**Non-Functional Requirements:**
- Latency: < 15s per query
- Availability: personal tool, not mission-critical
- Scale: 1–50 repos, hundreds to tens of thousands of chunks
- Privacy: code stays local (only queries sent to Groq cloud)

## Components

```
┌──────────┐     ┌──────────┐     ┌──────────────────────────────────────────────┐
│ React SPA│────▶│ FastAPI  │────▶│ LangGraph Pipeline                           │
│(Port 5173)    │(Port 8000)     │ route_query → [retrieve_code, retrieve_commits│
└──────────┘     └──────────┘     │   retrieve_readme] → check_ambiguity →       │
                                  │   synthesize_answer → format_citations       │
                                  └──────────────────────────────────────────────┘
                                              │
                             ┌────────────────┼────────────────┐
                             ▼                ▼                ▼
                      FAISS Indexes      BM25 Index       Groq Cloud API
                    (3 × .faiss files)  (bm25_code.pkl)  (Llama 3.3 70B)
                             ▲
                    Jina Embeddings
                    (Local, CPU)
```

## Low-Level Design

**Chunk Schema (canonical):**
```json
{id, chunk_type, repo, file_path, content, symbol_name, language, start_line, end_line, commit_hash, commit_message, commit_date, changed_files}
```

**FAISS structure:** `IndexFlatIP(768)` + parallel `list[dict]` metadata in pickle. Parallel structure ensures O(1) metadata lookup by FAISS index position.

**Retrieval pipeline:**
```
Query → Jina encode_query() → vector(768dim)
→ FAISS.search(vector, top_k=10, repo_filter)
→ BM25.search(query_tokens, candidate_indices=faiss_results)
→ hybrid_rerank(alpha=0.6) → top_5 chunks
```

## Scalability Tradeoffs

| Decision | Tradeoff |
|---|---|
| FAISS `IndexFlatIP` | 100% recall vs O(N·D) search time |
| Local Jina model | Privacy + no API cost vs slow CPU inference |
| JSONL storage | Simplicity vs no indexing for metadata queries |
| Stateless FastAPI | Horizontal scalability vs shared session state |
| Groq LLM | Fast inference vs cloud dependency |

---

# 34. Deep Code Walkthrough

## `_hybrid_rerank()` — Most Technically Interesting Function

```python
def _hybrid_rerank(query, faiss_results, bm25, top_k=5, alpha=0.6) -> list[dict]:
```

**Purpose:** Combine dense (semantic) and sparse (keyword) retrieval signals.

**Input:**
- `query`: user's question string
- `faiss_results`: `list[(chunk_dict, cosine_score)]` — 10 results from FAISS
- `bm25`: `BM25Store` object
- `top_k=5`: return this many
- `alpha=0.6`: weight for dense signal

**Algorithm:**
1. Build `dense_map: {chunk_id → cosine_score}` from FAISS results
2. Build `chunks_by_id: {chunk_id → chunk_dict}` for O(1) lookup
3. Map chunk IDs to BM25 corpus indices: `id_to_bm25_idx`
4. Call `bm25.search(query, candidate_indices=...)` to score only the subset
5. Normalize both score sets to [0,1]: `max_score → 1.0`
6. `combined = alpha * dense_norm + (1-alpha) * bm25_norm`
7. Sort descending, return top-k chunks

**Why O(K log K) not O(N log N)?** BM25 is called with `candidate_indices` — only the 10 FAISS candidates are scored, not the full corpus of thousands.

**Time:** O(K) normalization + O(K log K) sort where K=10 (constant) → O(1) effectively.

**Edge case:** If `bm25 is None` (index file not found) → return FAISS order directly.

---

## `FaissStore.remove_repo_and_save()` — Most Complex Operation

```python
@classmethod
def remove_repo_and_save(cls, index_path, repo_name) -> int:
```

**Purpose:** In-place deletion of one repo's vectors without re-embedding.

**Algorithm:**
1. Load existing FAISS + metadata
2. `keep_indices = [i for i, chunk in enumerate(chunks) if chunk.get("repo") != repo_name]`
3. Edge case: `if len(keep_indices) == 0` → write empty index
4. `kept_vectors = np.array([store._index.reconstruct(i) for i in keep_indices])` — extract kept raw float32 vectors
5. `new_store = FaissStore(); new_store.add(kept_vectors, kept_chunks); new_store.save(path)`

**Key insight:** `IndexFlatIP.reconstruct(i)` reads the raw float32 vector at position `i` from the internal C array. This is O(1) per vector, no neural computation.

**Why not delete in-place?** FAISS `IndexFlat` doesn't support deletions — it's a fixed contiguous array. Reconstruction + rebuild is the canonical approach.

**Space complexity:** Briefly holds 2× the stored vectors in RAM during rebuild (old + new store).

---

## `check_ambiguity()` — Standout Feature

```python
def check_ambiguity(state: AgentState) -> dict:
```

**Purpose:** Detect cross-repo implementation conflicts.

**Algorithm:**
1. `repo_counts = Counter(c.get("repo") for c in code_chunks)`
2. `repos_present = [r for r in repo_counts if r]`
3. Early exit if `len(repos_present) < AMBIGUITY_MIN_REPOS`
4. Get top-6 chunks: `top_n = code_chunks[:6]`
5. Count unique repos in top_n: `unique_top_repos = set(top_repos)`
6. Early exit if `len(unique_top_repos) < AMBIGUITY_MIN_REPOS`
7. Build `per_repo: {repo: [symbol_names]}` from top_n
8. Format `ambiguity_detail` string

**Why only top-6?** Performance optimization. Checking all chunks would include less-relevant results. Top-6 are the most likely candidates for actual ambiguity.

**Limitation:** Heuristic-based — doesn't actually measure semantic similarity between chunks from different repos.

---

# 35. End-to-End Data Flow

## Tracing "where have I implemented JWT authentication?" from click to render

**Step 1 — User Click:**
```
User types "where have I implemented JWT authentication?" → presses Enter
→ App.jsx handleKeyDown() → handleQuery()
→ setLoading(true), setError(null)
```

**Step 2 — HTTP Request:**
```javascript
axios.post('/query', {
  query: "where have I implemented JWT authentication?",
  repos: ["SketchXPad", "LearnSphere"],  // user selected filter
  conversation_history: []
})
```
Vite proxy → `POST http://localhost:8000/query`

**Step 3 — FastAPI validation:**
```python
QueryRequest.parse_obj(body)  # Pydantic validation
# query: "where have I..." ✓ min_length=3 ✓ max_length=1000
graph = _get_graph()  # lazy singleton
initial_state = AgentState(query="...", routed_repos=["SketchXPad", "LearnSphere"], ...)
```

**Step 4 — LangGraph: route_query**
```
already_filtered_repos = ["SketchXPad", "LearnSphere"] (from state)
→ Skip LLM repo routing
→ Ask LLM: what content types?
→ Groq: {"routed_types": ["code", "readme"]}
→ return {routed_repos: ["SketchXPad", "LearnSphere"], routed_types: ["code", "readme"]}
```

**Step 5 — LangGraph: parallel retrieval (all 3 fire simultaneously)**
```
retrieve_code:
  q_vec = Jina.encode_query("where have I implemented JWT authentication?")  # 768-dim vector
  store = _code_faiss()  # cached FAISS IndexFlatIP with 3000 code chunks
  results = store.search(q_vec, top_k=10, repo_filter=["SketchXPad", "LearnSphere"])
  # FAISS returns: [(jwt_middleware chunk, 0.91), (auth_hook chunk, 0.88), ...]
  bm25 = _code_bm25()
  chunks = _hybrid_rerank(query, faiss_results, bm25, top_k=5)
  # BM25 boosts "jwt" + "middleware" symbol matches
  # Final 5: jwt_middleware.py:8-45, useAuth.jsx:12-67, auth.py:23-89, ...
  return {code_chunks: [chunk1, chunk2, chunk3, chunk4, chunk5]}

retrieve_commits:
  "commits" NOT in routed_types → return {commit_chunks: []}

retrieve_readme:
  q_vec = Jina.encode_query("...")  # same vector
  store = _readme_faiss()
  results = store.search(q_vec, top_k=5, repo_filter=[...])
  return {readme_chunks: [readme_auth_section]}
```

**Step 6 — LangGraph: merge state**
```
AgentState.code_chunks = [] + [chunk1,...,chunk5] = [5 chunks]  # operator.add
AgentState.commit_chunks = [] + [] = []
AgentState.readme_chunks = [] + [readme_section] = [1 chunk]
```

**Step 7 — LangGraph: check_ambiguity**
```
code_chunks from 2 repos: SketchXPad (3 chunks) + LearnSphere (2 chunks)
repos_present = ["SketchXPad", "LearnSphere"] → len=2 ≥ AMBIGUITY_MIN_REPOS=2
top_n = code_chunks[:6] = all 5 code chunks
unique_top_repos = {"SketchXPad", "LearnSphere"} → len=2 ≥ 2
per_repo = {"SketchXPad": ["jwt_middleware", "useAuth"], "LearnSphere": ["authenticate", "JWTTokenObtain"]}
detail = "Multiple repos implement related functionality:\n  • SketchXPad: jwt_middleware, useAuth\n  • LearnSphere: authenticate, JWTTokenObtain\n\nThe answer will compare implementations across repos."
return {ambiguity_flag: True, ambiguity_detail: "..."}
```

**Step 8 — LangGraph: synthesize_answer (AMBIGUITY MODE)**
```python
system = _SYSTEM_AMBIGUITY
# "Compare and contrast. Add sections per repo. Add comparison table. Give recommendation."

context = _format_chunks_for_prompt(code_chunks=[5], commit_chunks=[], readme_chunks=[1])
# "=== CODE CHUNKS ===\n[1] SketchXPad/src/middleware/jwt.js:8-45 | symbol: verifyToken\n```\nconst verifyToken = ...```..."

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.0, max_tokens=2048)
response = llm.invoke([SystemMessage(_SYSTEM_AMBIGUITY), HumanMessage(context)])
answer = "## JWT Authentication Implementation\n\n### SketchXPad\n[SketchXPad/src/middleware/jwt.js:8-45] uses Express middleware...\n### LearnSphere\n[LearnSphere/api/auth.py:23-89] uses Django REST Framework..."
return {final_answer: answer}
```

**Step 9 — LangGraph: format_citations**
```python
# Parse [SketchXPad/src/middleware/jwt.js:8-45] from answer → match against chunk_lookup
citations = [
  {repo: "SketchXPad", file_path: "src/middleware/jwt.js", start_line: 8, ...},
  {repo: "LearnSphere", file_path: "api/auth.py", start_line: 23, ...},
  ... (all 6 chunks added as supporting citations)
]
return {citations: citations}
```

**Step 10 — FastAPI response assembly:**
```python
latency_ms = (perf_counter() - t0) * 1000  # ~9800ms
QueryResponse(answer="...", citations=[...], ambiguity_flag=True, ambiguity_detail="...", latency_ms=9800, ...)
```

**Step 11 — HTTP response → Frontend:**
```javascript
setResult(data)
setLoading(false)
setConversationHistory(prev => [...prev, {query: "...", answer: data.answer}])
setHistory(prev => [{id: Date.now(), query: "...", result: data, saved: false}, ...prev.slice(0, 49)])
```

**Step 12 — React render:**
- `ambiguity_flag=true` → renders yellow `⚠ Ambiguity detected` banner with detail text
- `ReactMarkdown` renders the answer with `## JWT Authentication Implementation` → `<h2>` heading
- `processCitations()` → `keyFiles = [{fname: "jwt.js", count: 3}, {fname: "auth.py", count: 2}]`
- Collapsible "Key Files" section renders with repo color dots
- `CitationPopover` components render numbered superscripts `[1]`, `[2]` in the answer text (click reveals popover with snippet)

---

# 36. Complete Dependency Explanation

| Library | Version | Purpose | Why This One |
|---|---|---|---|
| `langgraph` | ≥0.2.0 | Multi-agent StateGraph orchestration | Fan-out/in parallelism, typed state |
| `langchain` | ≥0.3.0 | LLM abstraction + callback system | LangSmith integration, `SystemMessage/HumanMessage` |
| `langchain-groq` | ≥0.2.0 | Groq API client | `ChatGroq` class, LangChain integration |
| `langchain-community` | ≥0.3.0 | Community integrations | Required by LangGraph dependency tree |
| `langsmith` | ≥0.1.0 | LLM observability tracing | Integrated with LangGraph automatically |
| `faiss-cpu` | ≥1.7.4 | Vector similarity search | Facebook AI, fast C, SOTA for local vector search |
| `sentence-transformers` | ≥3.0.0 | `SentenceTransformer` model loader | Standard wrapper for Jina/BERT models |
| `transformers` | ≥4.41,<4.45 | Hugging Face model architecture | Required by sentence-transformers; pinned to avoid Jina breaking changes |
| `torch` | ≥2.0.0 | Neural inference backend | Required by Jina (custom PyTorch layers) |
| `gitpython` | ≥3.1.40 | Git repository reading | High-level Python API for git operations |
| `tree-sitter` | ≥0.21.0 | C-based syntax parser | JS/TS/JSX/TSX AST extraction |
| `tree-sitter-javascript` | ≥0.21.0 | JavaScript grammar for tree-sitter | Required for `tree_sitter.Language(tsjava.language())` |
| `rank-bm25` | ≥0.2.2 | BM25Okapi implementation | Pure Python, simple API, correct TF-IDF normalization |
| `fastapi` | ≥0.111.0 | Async Python web framework | Pydantic integration, OpenAPI docs, ASGI |
| `uvicorn[standard]` | ≥0.29.0 | ASGI server | Production-grade ASGI, `--reload` for dev |
| `python-dotenv` | ≥1.0.0 | `.env` file loader | Standard `load_dotenv()` pattern |
| `tqdm` | ≥4.66.0 | Progress bars | Visual embedding progress in CLI |
| `rich` | ≥13.0.0 | Beautiful terminal output | Color, tables, panels in CLI tools |
| `typer` | ≥0.12.0 | CLI argument parsing | Type-hint based, fast to implement |
| `pydantic` | ≥2.0.0 | Data validation | FastAPI integration, field constraints |
| `numpy` | (via faiss) | Numerical arrays | Float32 vector operations |

**Frontend dependencies:**
| Package | Purpose |
|---|---|
| `react` `react-dom` | React 18 SPA runtime |
| `vite` | Dev server + bundler (ESM-native, extremely fast) |
| `axios` | HTTP client (better DX than fetch) |
| `react-markdown` | Render LLM Markdown output as HTML |
| `remark-gfm` | GitHub Flavored Markdown tables, strikethrough |
| `@mui/icons-material` | Material Design SVG icon components |
| `@emotion/react` `@emotion/styled` | MUI peer dependencies (CSS-in-JS) |

---

# 37. Difficult Interview Questions (50)

**D1. If FAISS returns the same chunk from two different repo filters, how does deduplication work?**
`seen_ids: set[str]` in `format_citations`. Each chunk has a UUID4 `id`. When the chunk is added the first time: `seen_ids.add(chunk["id"])`. If the same chunk appears again (same uuid), `if cid in seen_ids: continue` skips it.

**D2. The router LLM hallucinates a repo name that doesn't exist. What happens?**
`routed_repos = [r for r in routed_repos if r in available_repos] or available_repos`. The validation step filters out any unknown repo names. If the filtered list is empty, fallback to all repos.

**D3. A Python file with 10,000 lines — how many chunks does it produce?**
Depends on symbol density. If it has 400 function definitions (realistic for a large module): 400 function chunks + class chunks (entire class bodies). If no symbols found: `(10000 / (50-10)) = 250` sliding window chunks. The AST path is more efficient (400 focused chunks vs 250 large windows).

**D4. What is the asymptotic complexity of building the BM25 index?**
`BM25Okapi(corpus)` with N documents, average length L: O(N×L) for tokenization and TF computation + O(V) for IDF computation (V = vocabulary size). Total: O(N×L).

**D5. If a user adds 1000 commits in one push to a 500-commit-capped repo, what happens?**
The ingester calls `git_repo.iter_commits(all=True)` and stops after `max_commits=500`. The `count >= max_commits` check fires. Newest commits (returned first by git log) are indexed; older commits beyond 500 are ignored.

**D6. Explain what would happen if `operator.add` was replaced with `operator.or_` in AgentState.**
`operator.or_` is set union. Applied to lists, it would fail at runtime because `list | list` raises `TypeError` in Python (bitwise OR not defined for lists). Lists require `operator.add` (concatenation). If it were dicts, `operator.or_` (Python 3.9+) would merge dict keys.

**D7. How does the FAISS `reconstruct(i)` ensure the correct vector is returned after partial deletion?**
It doesn't need to — `reconstruct(i)` accesses the contiguous C float array by index. The key is that ALL vectors are reconstructed BEFORE building the new index. The new `IndexFlatIP.add()` call reindexes them at positions 0, 1, 2, ... in the new index, and `kept_chunks` is reordered to match.

**D8. What happens if two repos have files with the same relative path (e.g., both have `src/router.py`)?**
They're stored as separate chunks: `{"repo": "RepoA", "file_path": "src/router.py", ...}` and `{"repo": "RepoB", "file_path": "src/router.py", ...}`. FAISS doesn't care — each is an independent vector. At retrieval time, `repo_filter` correctly separates them. In citation display, the repo name differentiates them: `[RepoA/src/router.py:12]` vs `[RepoB/src/router.py:12]`.

**D9. The Groq API returns a 429 rate limit error during synthesis. What does the user see?**
`llm.invoke(messages)` raises a `langchain.exceptions.APIStatusError`. FastAPI's `try/except Exception` catches it → `HTTP 500 {"detail": "Pipeline error: APIStatusError(429...)"}`. Frontend: `setError("Pipeline error: APIStatusError(429...)")` → red error banner. User-facing message is not graceful.

**D10. How would you make the Groq synthesis call resilient to transient failures?**
Wrap `llm.invoke()` with `tenacity`:
```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception_type(RateLimitError))
def _call_llm(llm, messages): return llm.invoke(messages)
```

**D11. What's the difference between `ast.iter_child_nodes(tree)` and `ast.walk(tree)`?**
`iter_child_nodes`: yields only immediate children.
`ast.walk`: yields all descendants recursively.
In `chunk_python_file`: `for node in ast.iter_child_nodes(tree): visitor.visit(node)` — visits only top-level nodes. The visitor handles recursion within ClassDef. If `ast.walk` was used, nested functions would be visited twice (once by walk, once by visit).

**D12. What happens to the FAISS search results order when `repo_filter` is applied?**
FAISS returns results in inner-product score order (highest first). Post-filtering by `repo_filter` maintains this relative order — results are filtered in order, so the remaining results are still sorted by score. The `if len(results) >= top_k: break` ensures we stop after collecting `top_k` filtered results.

**D13. Explain the memory layout of a Python `list` of `dict` stored in a `@lru_cache`.**
`@lru_cache(maxsize=1)` stores a reference to the returned value in a `functools._lru_cache_wrapper` dictionary keyed by the function arguments. The `FaissStore` object (containing `_index` and `_chunks`) is in heap memory. `lru_cache` holds a strong reference to it, preventing garbage collection. Memory stays allocated until `cache_clear()` or process exit.

**D14. What is the cost of `json.loads(line)` × N_chunks when counting chunks in `_get_repo_chunk_counts()`?**
O(N) where N = total chunks across all JSONL files. For 10K chunks at ~500 bytes each = 5MB of text to parse. At typical CPython JSON parsing speed (~100MB/s), this takes ~50ms. Called on every `GET /repos` request. Optimization: cache the count and invalidate only after add/delete/update operations.

**D15. How does `textwrap.dedent()` handle tabs vs spaces in Python code?**
`textwrap.dedent()` uses common-prefix removal: it finds the longest common leading whitespace prefix across all lines and strips it. If some lines use tabs and others use spaces, Python won't consider them equivalent — `dedent` may fail to find a common prefix and return the text unchanged. Modern Python code is not supposed to mix tabs and spaces (PEP 8 + `SyntaxError` in Python 3 strict mode).

**D16. The frontend sends `conversation_history: []` vs not sending the field at all. What's the difference?**
Pydantic `QueryRequest`: `conversation_history: list[ConversationTurn] | None = None`. If field is absent from JSON: `None`. If field is `[]`: empty list. In `query_endpoint`: `req.conversation_history or []` — both `None` and `[]` evaluate to `[]` via the `or` fallback. Functionally equivalent.

**D17. What is the BM25 IDF score for a symbol that appears in only 1 of 1000 chunks?**
`IDF = log((N-df+0.5)/(df+0.5))` where N=1000, df=1.
`IDF = log((1000-1+0.5)/(1+0.5)) = log(999.5/1.5) = log(666.3) ≈ 6.5`
Very high IDF — this symbol is extremely discriminative. Combined with TF boost (symbol repeated 3×) → very high BM25 score for exact symbol name queries.

**D18. A `git clone --depth 500` gets 500 commits. Is `iter_commits(all=True)` reliably capped?**
`all=True` walks all refs (branches, tags). `count >= max_commits: break` fires after 500 commits regardless of branch. But with a shallow clone, git may not have 500 commits from all refs anyway — some refs may have fewer history entries. The `count` check is a safety ceiling, not relied upon for correctness.

**D19. Why does `_bm25: BM25Okapi | None = None` instead of raising if not initialized?**
Guard in `search()`: `if self._bm25 is None: return []`. Allows calling `BM25Store.load(path)` which uses `cls.__new__(cls)` to create the object without calling `__init__`, then directly sets `_bm25 = data["bm25"]`. Pattern: `__new__ + direct field assignment` for deserialization bypasses `__init__`'s requirement to provide `chunks` argument.

**D20. Explain `cls.__new__(cls)` used in `FaissStore.load()` and `BM25Store.load()`.**
`__new__` creates a new uninitialized instance WITHOUT calling `__init__`. Used in `load()` to avoid the `__init__` requirement (which would require `dim` argument for FaissStore, or `chunks` for BM25Store). After `__new__`, fields are set manually: `store._index = faiss.read_index(...)`, `store.dim = ...`. This is the standard Python deserialization pattern.

**D21. What is the race condition risk between `_write_jsonl` and `_append_jsonl`?**
`_write_jsonl` opens file in `"w"` mode (truncate). If another process is simultaneously reading or writing the file, the truncation creates a window of zero bytes. `_append_jsonl` uses `"a"` mode — safer for concurrent appends but doesn't handle duplicate entries. The `_remove_repo_from_jsonl` + `_append_jsonl` sequence does a full rewrite — read→filter→write — which has a TOCTOU window.

**D22. How is the `RepoStyle` color system resilient to repo renaming?**
`getRepoStyle(name)` uses the djb2 hash of the name string. If a repo is renamed, it gets a new color (hash of the new name). Preset styles (`PRESET_REPO_STYLES`) would still apply if the name matches. There's no persistence of color assignments — they're always computed deterministically from the current name.

**D23. In React, why does `selectedHistoryIds: Set<number>` require creating a new `Set` on each update?**
React's state comparison is by reference equality (`===`). If you mutate the existing Set: `prev.add(id); return prev;` — same Set reference → React thinks state hasn't changed → no re render. `const n = new Set(prev); n.add(id); return n;` → new Set reference → React detects change → triggers re-render.

**D24. The `Embedder.encode_query()` returns shape `(EMBEDDING_DIM,)`. Why is `q_vec = q_vec[np.newaxis, :]` needed in FAISS search?**
`faiss.IndexFlatIP.search()` expects a 2D array of shape `(n_queries, dim)`. A query encoded as `(768,)` is 1D. `query_vec[np.newaxis, :]` reshapes to `(1, 768)` by adding a batch dimension at index 0. `scores[0]` and `indices[0]` then extract the results for the single query.

**D25. What is the maximum safe JSONL file size before write performance degrades significantly?**
Python file I/O: `open(path, "a")`→ `write(line)` is buffered at OS level. Performance stays consistent up to filesystem limits (typically GBs). The real bottleneck is `_remove_repo_from_jsonl` which reads the entire file into RAM. For 100K chunks × 500 bytes = 50MB — fine. For 10M chunks (hypothetical) = 5GB — would cause OOM. Use streaming JSON processing for scale.

**D26. What would happen if `TOP_K_DENSE` was set to 1 instead of 10?**
Only 1 FAISS candidate → BM25 scores only 1 chunk → no re-ranking is possible → top-1 FAISS result is returned. Quality would drop significantly, especially for exact symbol name queries (BM25's strength). The BM25 re-ranking is only meaningful with a candidate pool > final top_k.

**D27. Explain the embedding quality difference between chunking a file as one block vs per-function.**
One large block: the 768-dim vector is an average over all tokens in the file. Similarity to a query is diluted by irrelevant functions. Retrieving "where is the retry logic?" returns the file vector — which also encodes auth, database, logging, etc. False positive risk.
Per-function: each chunk's vector represents only that function's semantics. More precise retrieval, fewer false positives. Trade-off: more vectors to search, higher index memory.

**D28. What is `str(uuid.uuid4())` producing and why is it collision-safe?**
UUID4 is random: 122 bits of randomness + 6 version/variant bits = 128-bit ID. `str(uuid4()) = "550e8400-e29b-41d4-a716-446655440000"`. Collision probability for 1 trillion UUIDs: `P ≈ N²/(2 × 2^122) ≈ (10^12)^2 / (2 × 5.3×10^36) ≈ 10^-13`. Negligible for a personal tool indexing tens of thousands of chunks.

**D29. How does `remark-gfm` differ from standard CommonMark Markdown?**
GFM (GitHub Flavored Markdown) adds: tables (`| col1 | col2 |`), task lists `- [x] done`, strikethrough `~~text~~`, autolinks `https://...`, fenced code blocks with language hints. CodeAtlas answers often include tables (comparison tables in ambiguity mode) and fenced code blocks — both require GFM.

**D30. If you call `graph.invoke()` concurrently from two threads, what happens?**
Each call to `graph.invoke()` creates a new state dict and executes independently. The compiled graph is stateless — it's a function transformer. The LangGraph execution engine runs independent executions in separate call stacks. The risk is with the `@lru_cache` FAISS loaders — they're thread-safe because Python's GIL ensures only one thread runs Python bytecode at a time. The first `.invoke()` call loads the index; subsequent calls return the cached object.

**D31. Why does `ingestion/run_ingestion.py` use `_append_jsonl` instead of `_write_jsonl` when processing multiple repos?**
If `_write_jsonl` was used per repo, each repo would overwrite the previous repo's chunks. `_append_jsonl` adds to the end. But before appending, `_remove_repo_from_jsonl` strips any prior chunks for that repo — prevents duplicates on re-ingestion. Net effect: update-in-place semantics at the JSONL level.

**D32. How does the `ambiguity_detail` string flow from `check_ambiguity` to `synthesize_answer` and into the LLM prompt?**
1. `check_ambiguity` returns `{"ambiguity_detail": "Multiple repos implement..."}`
2. LangGraph merges it into `state`
3. `synthesize_answer`: `ambiguity_detail = state.get("ambiguity_detail", "")`
4. In user message: `f"Note: {ambiguity_detail}"` if `ambiguity_flag` is True
5. LLM sees the detail as context in its user message — "I know there's a conflict, compare them"

**D33. What would you change in `_SYSTEM_AMBIGUITY` to make it explicitly list the repos to compare?**
Inject `routed_repos` into the system prompt:
```python
_SYSTEM_AMBIGUITY = f"""
Your primary job is to COMPARE implementations from: {', '.join(state['routed_repos'])}.
Create one section per repo, then a comparison table, then a recommendation.
"""
```
Currently `_SYSTEM_AMBIGUITY` doesn't know the specific repo names — it relies on the chunk headers in the context.

**D34. When a user bookmarks a history item, what exactly gets stored in localStorage?**
The full history array (max 50 items) is serialized with `JSON.stringify(history)`. Each item includes: `{id, query, timestamp, latency_ms, citationsCount, repos, result: {answer, citations, ambiguity_flag, ...}, saved: true/false}`. The `result` object contains the full server response including all citation objects and the full answer text. localStorage usage per item: ~5–20KB depending on answer length.

**D35. What is the Python `ast` module's handling of type annotations?**
Python 3.10+ `ast.FunctionDef` node includes: `args`, `body`, `decorator_list`, `returns` (return type annotation), `type_comment`. The `_ChunkVisitor` doesn't specially handle annotations — it just captures the full source lines including any `def foo(x: int, y: str) -> bool:` signature. The docstring extractor uses `ast.get_docstring()` which works on any function/class AST node.

**D36. How does the `_HEADING_RE` handle ATX-style vs Setext-style headings?**
`_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)` only matches ATX-style headings: `# Heading`, `## Heading`. Setext headings (text underlined with `====` or `----`) are NOT matched. This is usually fine — most README files use ATX headings in modern Markdown convention.

**D37. In the eval suite, what would happen if `time.sleep(5)` was removed?**
Groq's free-tier limit: ~12k tokens per minute. Llama 3.3 70B synthesis uses ~3-4k tokens per call. At 20 questions in rapid succession: ~4 questions/minute limit exceeded → HTTP 429 errors starting around question 4-5 → `except Exception as e` catches them → rows added with `{"error": "...429..."}` → `answer_ok = False` → inflated failure metrics. Sleep ensures the eval runs in ~100 seconds (20 × 5s) within budget.

**D38. What is `git_repo.iter_commits(all=True)` equivalent to in git CLI?**
`git log --all` — iterates commits from all branches and tags, not just the current checked-out branch. This is important: a developer may have a feature branch with commits not yet merged to main. `all=True` ensures those commits are indexed too.

**D39. If you replace pydantic v2 `Field(...)` with `Field()` (no `...`), what changes?**
`...` (Ellipsis) as default value = required field. `Field()` with no argument = optional with `None` default. Changing `query: str = Field(..., min_length=3)` to `query: str = Field(min_length=3)` would make `query` optional (defaulting to None), which would break type checking and could allow empty query submissions that bypass the API contract.

**D40. What is `numpy.vstack` doing in `encode_documents()`?**
`all_vecs` accumulates one `np.ndarray` per batch, each of shape `(batch_size, 768)`. `np.vstack(all_vecs)` vertically stacks them into a single `(N, 768)` array. `np.concatenate(all_vecs, axis=0)` would be equivalent and slightly faster. `vstack` handles the case where each batch has different size (last batch may be smaller).

**D41. The system embeds code chunks with a header `# file_path\n# symbol: name`. Does this header interfere with the embedding?**
It adds noise to the vector, but strategically useful noise. The header anchors the embedding to a specific file/symbol context. Without the header, "def verify_token(token):" might embed similarly to "async def verify_token(session)" in another file. The header `# src/auth/middleware.py\n# symbol: verify_token` shifts the vector slightly in the direction of "verify_token in auth middleware" — more discriminative.

**D42. How would you implement caching at the query level (memoize entire pipeline for identical queries)?**
```python
import hashlib, functools
@functools.lru_cache(maxsize=128)
def cached_query(query_hash: str, repos_tuple: tuple): ...

def query_endpoint(req):
    key = (req.query, tuple(sorted(req.repos or [])))
    cache_result = query_cache.get(key)
    if cache_result: return cache_result
    result = graph.invoke(...)
    query_cache[key] = result
    return result
```
TTL needed to avoid stale results after repo updates.

**D43. How does `click-outside` detection work in `CitationPopover`?**
```javascript
const handler = (e) => {
  if (ref.current && !ref.current.contains(e.target)) setOpen(false)
}
document.addEventListener('mousedown', handler)
return () => document.removeEventListener('mousedown', handler)
```
`document.addEventListener('mousedown')` captures all clicks. `ref.current.contains(e.target)` checks if the clicked element is inside the popover DOM tree. If not → close. `useEffect` return function removes the listener on cleanup (component unmount or `open` state change).

**D44. Explain the `encode_query` vs `encode_documents` distinction in Jina v2.**
Jina v2 code model uses symmetric retrieval — same encoder for queries and documents. No special query prefix is needed. `encode_query()` calls `model.encode([query], ...)` — wraps query in a list for batch API. `encode_documents()` calls `model.encode(batch, ...)` — batch of document strings. Functionally identical. The separation is for clarity and to enable future asymmetric retrieval models.

**D45. What would you do differently about the `feedback` endpoint if you wanted to use it for fine-tuning?**
Current: stores only `(query, answer_snippet[:200], rating)`. For fine-tuning:
1. Store full answer (not just 200 chars)
2. Store retrieved chunks (what context the LLM had)
3. For thumbs-down: store user's corrected answer if provided
4. For DPO (Direct Preference Optimization): store pairs of (preferred, rejected) answers
5. Tag with user ID for personalized models

**D46. How does the `@lru_cache` interact with the lazy `Embedder._instance` singleton?**
They serve different purposes. `@lru_cache` on FAISS loaders: per-function cache keyed by call arguments (no arguments here → one global cached result). `Embedder._instance`: class-level singleton, explicitly checked with `if cls._instance is None: cls._instance = cls()`. Both are cached forever until `cache_clear()` (FAISS) or process restart (Embedder).

**D47. What would happen if `EMBEDDING_DIM` in config.py was changed to 512 but the Jina model still outputs 768?**
1. `FaissStore(dim=512)` creates `faiss.IndexFlatIP(512)` — expects 512-dim vectors
2. `Embedder.encode_documents()` returns `(N, 768)` arrays
3. `store.add(vectors, chunks)` → `faiss.IndexFlatIP.add()` with 768-dim vectors into a 512-dim index → `faiss.FaissException: expected d=512 dimensions`
4. Crash during `build_indexes.py`. `EMBEDDING_DIM` must match the actual model output dimension.

**D48. How does the `parent_class` field enable hierarchical code navigation?**
`extra={"parent_class": "MyClass"}` stored in each method sub-chunk. If a future UI feature wanted to show "this method's class context", it could read `chunk.get("parent_class")`. In synthesis, the chunk header includes `# class: MyClass` which helps the LLM understand the method belongs to a class. In citation display, `symbol_name = "MyClass.process"` shows the full qualified name.

**D49. If a Python class has 200 methods, how many chunks does python_chunker produce?**
1 class chunk (whole class body) + 200 method sub-chunks = 201 chunks. Each chunk gets a UUID. For a 200-method class with each method ~20 lines: 1 chunk of ~4000 lines + 200 chunks of ~20 lines each. Memory: 201 dicts in RAM until written to JSONL. The class-level chunk will have ~4000 lines of content — the 1500-char cap in synthesis truncates it.

**D50. What is the system's behavior when `repos.json` is empty and someone queries?**
```python
if not configured_repos:
    raise HTTPException(
        status_code=400,
        detail="No repositories are configured. Please add and index at least one repository from the Repositories page before querying."
    )
```
Explicit 400 error with a user-actionable message. Frontend catches it: `setError("No repositories are configured...")` → red banner. No LangGraph execution happens. This is a guard — not an oversight.

---

# 38. Explain Like I Built It

## Feature: AST-Aware Python Chunking

**What I built:** Instead of splitting Python files every N lines (which cuts code mid-function), I used Python's built-in `ast` module to parse the actual syntax tree. Each function and class becomes its own chunk with precise line boundaries.

**Why I built it:** Early tests with sliding-window chunking were terrible. A query for "retry logic" would return chunks that were 60% the function and 40% another function below it — confusing to read and embeds a mixed semantic signal.

**Problems I faced:** Classes with many small methods were being emitted as one large chunk, making it hard to retrieve individual methods. I had to implement two-level chunking: emit the whole class AND each method separately.

**How I solved it:** `_inside_class` flag in the visitor. When visiting a ClassDef, I emit the whole class, then set `_inside_class = node.name`, visit all descendant methods (emitting them with the parent class in the symbol name as `ClassName.method_name`), then reset the flag.

**Lessons learned:** AST line numbers are 1-indexed; Python list slicing is 0-indexed. I debugged a subtle off-by-one: `lines[start - 1 : end]` is correct. `lines[start : end]` would skip line 1 of every function.

**Future improvements:** Track function call relationships (call graph) and include "called_by: [funcA, funcB]" in chunk metadata. This would enable queries like "what calls my authenticate() function?"

---

## Feature: Hybrid BM25 + FAISS Retrieval

**What I built:** Dense vector similarity (FAISS) retrieves semantically similar code. BM25 keyword search re-ranks the FAISS candidates based on exact symbol name matches. Final score = 0.6 × dense + 0.4 × BM25.

**Why I built it:** Early version was pure FAISS. Query "where is useDrawingSocket?" would rank a chunk about "drawing_hook" (semantically similar) above the actual `useDrawingSocket` function because embeddings are fuzzy. BM25 fixed this — when the query exactly mentions a function name, BM25 scores that function extremely high.

**Problems I faced:** BM25 scoring the entire 3000-chunk corpus per query was slow. Also, CamelCase function names like `useDrawingSocket` weren't being split into meaningful tokens by standard tokenizers.

**How I solved it:** Custom `_tokenize()` that splits on CamelCase boundaries (`([a-z])([A-Z])` regex) and then on `_` (snakeCase). Also implemented `candidate_indices` — BM25 only scores the 10 FAISS candidates, not all 3000 chunks.

**Lessons learned:** Symbol upweighting (3× repetition) is a hackish but effective trick. A more principled approach would be a custom BM25 field weight or a dedicated symbol inverted index.

**Future improvements:** Replace BM25 with a cross-encoder fine-tuned on code (query, code_chunk) pairs.

---

## Feature: Cross-Repo Ambiguity Detection

**What I built:** When retrieved code chunks come from multiple repos for the same query, the system detects this as potential ambiguity and switches to compare-and-contrast synthesis mode.

**Why I built it:** Without this, the system would silently pick the highest-scoring chunk and explain only that implementation. The user wouldn't know they had JWT auth implemented differently in two repos — which is exactly the information they need.

**Problems I faced:** Distinguishing "true ambiguity" (conflicting implementations) from "broad multi-repo queries" (asking about error handling which exists in all repos). A query like "how do I handle errors?" would always trigger ambiguity — that's noise.

**How I solved it:** Two-level check: (1) multiple repos in retrieved chunks, AND (2) multiple repos in the TOP-6 chunks. Top-6 being from multiple repos is stronger signal than any random chunk from a different repo being retrieved. However: this is still a heuristic. The eval suite distinguishes `is_ambiguity_test=True` (genuine conflicts) from multi-repo queries.

**Lessons learned:** The eval ambiguity detection rate of 66% (2/3) shows the heuristic is imperfect. A better approach: compare embedding similarity between top-1 chunks from different repos — if similarity > 0.85, they're likely the same concept implemented differently.

**Future improvements:** Compute pairwise semantic similarity between top chunks from different repos. Use a dedicated "ambiguity classifier" fine-tuned on (chunk_pair, is_ambiguous) examples.

---

## Feature: Isolated Single-Repo Update

**What I built:** `POST /repos/{name}/update` strips only the target repo's data from all indexes, re-ingests just that repo, and appends new vectors — other repos completely untouched.

**Why I built it:** Naive implementation would re-embed ALL repos when one changes. With 3 repos and 3000 total chunks at batch_size=8 on CPU, a full rebuild takes ~5 minutes. Single-repo update for a 500-chunk repo takes ~30 seconds.

**Problems I faced:** FAISS doesn't support deletions by metadata. You can't say "remove all vectors where repo==MyRepo." I had to reconstruct the entire index from kept vectors.

**How I solved it:** `FaissStore.remove_repo_and_save()` uses `IndexFlatIP.reconstruct(i)` — reads raw float32 vectors at specific positions from the C array without re-running neural inference. Build a new `IndexFlatIP` from only the kept vectors, overwrite the file.

**Lessons learned:** The same pattern applies to BM25 — it's pure Python, so rebuilding is fast (just re-tokenization, no GPU/CPU-intensive inference).

**Future improvements:** Webhook integration — instead of manual "Update" button, GitHub webhooks trigger automatic per-file incremental updates.

---

# 39. Whiteboard Explanation (5 Minutes)

Draw this:

```
1. OFFLINE (run once)
―――――――――――――――――――――――――――
repos.json  →  walker  →  chunkers  →  JSONL files
                                           ↓
                                      Jina Embeddings
                                           ↓
                                    FAISS + BM25 indexes

2. ONLINE (every query)
―――――――――――――――――――――――――――
User Query
    ↓
Router (Groq LLM) → which repos? which types?
    ↓        ↓         ↓
  code    commits    readme  ← parallel FAISS searches
    ↓        ↓         ↓
         MERGE
            ↓
    Ambiguity check → multiple repos? → compare mode
            ↓
    Synthesize (Groq LLM) → grounded answer + [repo/file:line]
            ↓
         Response
```

**Talk track (60 seconds):**
"Offline, I index code, git history, and docs into three separate FAISS vector stores. At query time, a LangGraph pipeline runs 7 nodes: the router uses Groq LLM to decide which repos and content types to search; three retrieval nodes run in parallel (fan-out); we detect if the same thing is implemented in multiple repos (ambiguity); then Groq generates a grounded answer with exact file citations. The whole thing runs in about 11 seconds."

---

# 40. Final Cheat Sheet

## Tech Stack at a Glance
```
Backend:  Python 3.10+ | FastAPI | LangGraph | Pydantic
LLM:      Groq Cloud | Llama 3.3 70B | temperature=0.0
Embed:    jinaai/jina-embeddings-v2-base-code | 768-dim | LOCAL CPU
Vector:   FAISS IndexFlatIP | 3 indexes | + pickle metadata
Sparse:   BM25Okapi (rank-bm25) | camelCase tokenizer | symbol 3×
Parse:    Python `ast` | tree-sitter (JS/TS) | GitPython | regex fallback
Frontend: React 18 | Vite | axios | react-markdown | MUI icons
Storage:  JSONL (chunks) | FAISS binary | pickle | JSON (repos.json)
Eval:     20 questions | 5 metrics | Typer CLI
```

## Critical Numbers
| Number | Meaning |
|---|---|
| 768 | Jina embedding dimension |
| 10 | `TOP_K_DENSE` — FAISS candidates |
| 5 | `TOP_K_FINAL` — after BM25 re-rank |
| 0.6 / 0.4 | Dense / BM25 hybrid weight |
| 2 | `AMBIGUITY_MIN_REPOS` threshold |
| 500 | Max commits per repo |
| 2048 | Max LLM output tokens |
| 1500 | Code chunk content cap (chars) in prompt |
| 89% | Repo hit rate (benchmark) |
| 100% | Answer quality (benchmark) |
| ~11s | Avg end-to-end latency |

## API Quick Reference
```
POST /query           → {query, repos?, conversation_history?} → {answer, citations, ambiguity_flag, latency_ms}
GET  /health          → {status, indexes_loaded, repos_configured}
GET  /repos           → {repos, repos_detail, chunk_counts}
POST /repos/add       → {name, url} → ingest+index → ok
DELETE /repos/{name}  → strip+patch → ok
POST /repos/{name}/update → strip+re-ingest+patch → ok
POST /feedback        → {query, answer_snippet, rating, routed_repos} → ok
```

## Database (No Traditional DB!)
```
data/chunks/
  code_chunks.jsonl      ← one JSON per function/class/window
  commit_chunks.jsonl    ← one JSON per commit
  readme_chunks.jsonl    ← one JSON per heading section

data/indexes/
  code.faiss             ← IndexFlatIP binary
  code.faiss.meta        ← pickle(list[dict])  ← PARALLEL to FAISS
  commits.faiss + .meta
  readme.faiss + .meta
  bm25_code.pkl          ← pickle({chunks, bm25: BM25Okapi})
```

## LangGraph Pipeline
```
START → route_query
  ┌────────────────────────────────┐
  ↓            ↓                  ↓
retrieve_code  retrieve_commits  retrieve_readme
  ↓            ↓                  ↓
  └────────────→ check_ambiguity ←┘
                      ↓
               synthesize_answer
                      ↓
               format_citations → END
```
**Key:** Annotated[list, operator.add] enables concurrent-write merging at join point.

## Top 10 Interview Points to Remember
1. **Three separate indexes** — code/commits/readme have different semantics
2. **BM25 re-ranks FAISS candidates** — not a full corpus scan (candidate_indices)
3. **Symbol upweighted 3×** in BM25 corpus for exact function name boosting
4. **IndexFlatIP + L2-norm = cosine similarity** — no approximation = 100% recall
5. **Annotated[list, operator.add]** — how LangGraph merges parallel retrieval
6. **Fan-out → Fan-in** — three retrievers run simultaneously, joined by ambiguity check
7. **In-place deletion** — reconstruct() extracts raw vectors; no re-embedding for delete/update
8. **Temperature=0.0** — deterministic LLM output for classification (routing) and generation
9. **Two-pass citation** — parse LLM text + include ALL retrieved chunks (anti-hallucination)
10. **conversation_history session-only** — never persisted, last 3 turns only (token budget)

## One-Liner Explanations for Every File
| File | One-liner |
|---|---|
| `config.py` | Single source of truth — all paths, model names, thresholds |
| `agents/state.py` | Typed schema for the data that flows through LangGraph |
| `agents/graph.py` | Assembles and compiles the 7-node StateGraph |
| `agents/router.py` | Groq LLM classifies query → (repos, content_types) |
| `agents/retrieval_nodes.py` | Three parallel FAISS+BM25 search functions |
| `agents/ambiguity_checker.py` | Detects cross-repo conflicts in top code results |
| `agents/synthesizer.py` | Groq LLM generates cited Markdown answer |
| `agents/citation_formatter.py` | Parses + verifies citations against real chunk metadata |
| `api/main.py` | FastAPI: 7 REST endpoints, repo management, feedback |
| `api/schemas.py` | Pydantic models for request/response validation |
| `ingestion/repo_walker.py` | Filesystem traversal with noise directory pruning |
| `ingestion/python_chunker.py` | `ast.parse()` → function/class chunks with line numbers |
| `ingestion/js_chunker.py` | tree-sitter/regex → JS/TS chunks |
| `ingestion/commit_ingester.py` | GitPython → 500 commit history chunks per repo |
| `ingestion/readme_ingester.py` | `## heading` splits → Markdown section chunks |
| `ingestion/run_ingestion.py` | Typer CLI entry: walk → chunk → write JSONL |
| `indexing/embedder.py` | Jina code embedding singleton (768-dim local model) |
| `indexing/faiss_store.py` | IndexFlatIP + pickle metadata: build/search/save/delete |
| `indexing/bm25_store.py` | BM25Okapi: camelCase tokenizer + symbol upweighting |
| `indexing/build_indexes.py` | Reads JSONL → embed → build FAISS+BM25 → save |
| `frontend/src/App.jsx` | 1572-line SPA: all state, all views, all API calls |
| `eval/run_eval.py` | 5-metric evaluation harness: 20 ground-truth questions |
| `eval/test_questions.py` | 20 labeled questions: expected_repo, expected_file |

