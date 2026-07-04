# CodeAtlas — Personal Codebase Knowledge Agent

A multi-agent Retrieval-Augmented Generation (RAG) system built with **LangGraph**, **Groq Llama 3.3 70B**, **FAISS**, and **Jina Code Embeddings**. It indexes custom repositories, git commit histories, and documentation, answering queries like *"where have I implemented WebSocket real-time features before?"* with exact file, line, and commit citations.

---

## System Architecture

```
                              ┌─────────────────────┐
                              │   Query (CLI/API)   │
                              └──────────┬──────────┘
                                         │
                              ┌──────────▼──────────┐
                              │   Router Agent      │
                              │ (Groq Llama 3.3 70B │
                              │  — repo + type cls) │
                              └──────────┬──────────┘
                                         │
             ┌───────────────────────────┼───────────────────────────┐
             ▼                           ▼                           ▼
     ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
     │ Code Retriever│           │CommitRetriever│           │Doc / README   │
     │ (FAISS + BM25 │           │ (FAISS dense) │           │ Retriever     │
     │  Hybrid)      │           │               │           │ (FAISS dense) │
     └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
             │                           │                           │
             └───────────────────┬───────┴───────────────────────────┘
                                 ▼
                     ┌───────────────────────┐
                     │   Ambiguity Checker   │
                     │ (Flags cross-repo     │
                     │  conflicting impls)   │
                     └───────────┬───────────┘
                                 ▼
                     ┌───────────────────────┐
                     │    Synthesis Agent    │
                     │ (Grounded explanation │
                     │  via Groq Llama 3.3)  │
                     └───────────┬───────────┘
                                 ▼
                     ┌───────────────────────┐
                     │  Citation Formatter   │
                     │  (file:line & commit  │
                     │   verification)       │
                     └───────────────────────┘
```

---

## Tech Stack

### **AI & Multi-Agent Engine**
- **LangGraph**: Stateful multi-agent orchestration for intent routing, parallel retrieval, ambiguity detection, and grounded answer synthesis.
- **Groq (Llama 3.3 70B)**: Ultra-fast LLM inference engine powering natural language routing, cross-repo synthesis, and reasoning.

### **Embeddings & Vector Search**
- **Jina Code Embeddings (`jina-embeddings-v2-base-code`)**: 768-dimensional dense code embedding model supporting 4096+ token context windows.
- **FAISS (Facebook AI Similarity Search)**: Vector similarity indexing for code snippet, commit log, and Markdown documentation retrieval.
- **BM25 (Rank-BM25)**: Sparse keyword ranker for symbol-exact function and class name matching. Fused via linear interpolation (α=0.6 dense, 0.4 sparse).

### **Ingestion & Parsing**
- **Tree-sitter & AST**: Syntax-aware AST parsing for Python, JavaScript, and TypeScript to preserve exact function boundaries and line numbers.
- **GitPython**: Git history analysis engine extracting commit trees, author metadata, diff statistics, and commit messages. Each commit chunk surfaces the primary changed file as `file_path` metadata for accurate citation lookup.

### **Backend & API Layer**
- **FastAPI**: Modern Python web framework exposing REST endpoints for RAG execution, query history management, and single-repo re-indexing.
- **Pydantic**: Type validation and schema definitions for request and response models.

### **Frontend & UI**
- **React 18 + Vite**: High-density single-page web app with custom CSS variables.
- **Material-UI (MUI) Icons**: Icon set for navigation rail, repo colour dots, and inline history controls.
- **React Markdown**: Markdown engine with code block syntax highlighting and inline citation popovers.

---

## Key Features & Technical Differentiators

1. **AST-Aware & Tree-Sitter Chunking** — Extracts exact function, class, and method definitions with preserved line numbers rather than arbitrary token cuts. Falls back gracefully to regex declaration parsing for JS/TS if needed.
2. **Code-Specific Embedding Model** — Powered by `jinaai/jina-embeddings-v2-base-code` (768-dim, 4096+ token context), specifically trained for semantic code search across 30+ programming languages.
3. **Hybrid Dense + Sparse Retrieval** — Combines dense vector similarity (FAISS) with BM25 keyword matching over symbol and function names to guarantee high recall for exact code symbols.
4. **Cross-Repo Ambiguity Detection** — Automatically flags when the same concept is implemented differently across multiple repositories, switching the synthesis agent to compare-and-contrast mode.
5. **Multi-Content Indexing** — Indexes code files, complete git commit history (author, date, changed files, message), and Markdown documentation in dedicated FAISS vector spaces.
6. **Strict Citation Verification** — Cross-references every generated claim against ground-truth chunk metadata to eliminate hallucinated line numbers or non-existent file paths.
7. **Session Multi-Turn Context** — Remembers conversation turns within an active session, providing context-aware follow-up answers with visual turn indicators.
8. **Query History Management** — Local history interface with search, preview, bookmarking, and bulk operations (select all, save, delete).
9. **Noise-Filtered Indexing** — `eval/`, `migrations/`, `node_modules/`, and similar infrastructure directories are pruned from the code index at walk time. A `SKIP_FILENAMES` allowlist further excludes root-level debug and check scripts committed to target repos, preventing retrieval pollution.
10. **Isolated Single-Repo Updates** — Individual update controls on repository cards that pull remote updates and re-embed a single repository without rebuilding the entire vector store.

---

## Repository Structure

```
Knowledge-Base-Agent/
├── .env                          # API Keys (GROQ_API_KEY, LANGCHAIN_API_KEY)
├── config.py                     # Central configuration & tunable parameters
├── repos.json                    # Repository list (GitHub URLs or local paths)
├── requirements.txt              # Project dependencies
│
├── ingestion/                    # Code & Git Ingestion
│   ├── repo_walker.py            # Recursive directory walker & noise filtering
│   ├── python_chunker.py         # AST module chunker for Python
│   ├── js_chunker.py             # tree-sitter & regex fallback for JS/TS
│   ├── commit_ingester.py        # GitPython log & commit document ingester
│   ├── readme_ingester.py        # Section-based Markdown chunker
│   └── run_ingestion.py          # Ingestion CLI runner
│
├── indexing/                     # Embeddings & Vector Store
│   ├── embedder.py               # Jina Code Embeddings wrapper
│   ├── faiss_store.py            # FAISS Inner Product index & metadata store
│   ├── bm25_store.py             # BM25 symbol ranker
│   └── build_indexes.py          # Vector store index builder CLI
│
├── agents/                       # LangGraph Multi-Agent Engine
│   ├── state.py                  # LangGraph AgentState TypedDict
│   ├── router.py                 # Groq Llama 3.3 router node
│   ├── retrieval_nodes.py        # Parallel code, commit, and doc retrievers
│   ├── ambiguity_checker.py      # Cross-repo conflict detector
│   ├── synthesizer.py            # Grounded answer generation node
│   ├── citation_formatter.py     # Ground-truth citation parser
│   └── graph.py                  # StateGraph compiler & standalone CLI
│
├── api/                          # REST API Layer
│   ├── main.py                   # FastAPI application with CORS
│   └── schemas.py                # Pydantic request/response schemas
│
├── frontend/                     # React UI
│   ├── package.json              # React + Vite + MUI setup
│   ├── vite.config.js            # API proxy configuration
│   └── src/
│       ├── App.jsx               # Dashboard UI with citation drawer
│       └── index.css             # Custom design system
│
└── eval/                         # Benchmark & Evaluation Harness
    ├── test_questions.py         # 20 ground-truth labelled evaluation questions
    └── run_eval.py               # Deterministic evaluation runner
```

---

## Quick Start Guide

### 1. Requirements & Setup

```bash
# Clone the repository
git clone https://github.com/Deepak-vm/Knowledge-Base-Agent.git
cd Knowledge-Base-Agent

# Create & activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment & Repositories

Create a `.env` file in the root directory:
```env
GROQ_API_KEY=gsk_your_groq_api_key
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_your_langsmith_key
LANGCHAIN_PROJECT=Knowledge-Base-Agent
```

Create `repos.json` specifying local paths or GitHub URLs to index:
```json
[
  {
    "name": "my-backend",
    "path": "/path/to/your/backend"
  },
  {
    "name": "my-rag-agent",
    "url": "https://github.com/username/my-rag-agent"
  }
]
```

> **Note:** Repositories specified by URL are cloned automatically into `repos/` on first ingestion.

### 3. Ingestion & Indexing Workflow

```bash
# Step 1: Ingest code, commits, and docs for all repos in repos.json
python -m ingestion.run_ingestion

# Step 2: Generate embeddings & build FAISS + BM25 indexes
python -m indexing.build_indexes
```

To re-ingest a single repo without touching others:
```bash
python -m ingestion.run_ingestion --only-repo my-rag-agent
```

To start fresh and wipe existing chunk files before ingesting:
```bash
python -m ingestion.run_ingestion --fresh
```

### 4. Running the Agent

#### Option A: Command Line Interface (CLI)
```bash
python -m agents.graph "where have I implemented WebSocket real-time features?"
```

#### Option B: FastAPI Backend + React Web Interface
```bash
# Terminal 1: Start FastAPI server (Port 8000)
uvicorn api.main:app --reload --port 8000

# Terminal 2: Start React Frontend (Port 5173)
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Evaluation & Benchmarking

The evaluation suite runs 20 ground-truth labelled queries through the full LangGraph pipeline and measures performance against exact repo and file targets.

```bash
# Run all 20 questions
python -m eval.run_eval

# Pin to a specific repo set for reproducible runs (recommended)
python -m eval.run_eval --repos "LearnSphere,SketchXPad,MultiSource-RAG-Agent"

# Run a subset of questions by ID
python -m eval.run_eval --questions 1,2,5

# Save results to JSON for further analysis
python -m eval.run_eval --output results.json

# Print retrieved file paths and answer snippets
python -m eval.run_eval --verbose
```

### Measured Metrics

| Metric | What It Tests |
|---|---|
| **Repo hit rate** | Expected repository name found in retrieved chunks or citations |
| **File hit rate** | Expected file substring found in retrieved chunks or citations (commit chunks also checked via `changed_files`) |
| **Answer quality** | Non-empty, grounded response; negative/hallucination tests checked for correct refusal |
| **Ambiguity detection** | Ambiguity flag raised correctly for genuine conflicting-implementation cross-repo queries (distinct from broad multi-repo queries) |
| **Avg latency** | End-to-end pipeline time per query |

### Scoring Design

- **Negative tests** (`expected_repo == "NONE"`, e.g. the Kubernetes deployment query) are excluded from repo-hit and file-hit denominators entirely — they only count toward answer quality (did the system correctly refuse?).
- **Ambiguity detection** is scored only for questions tagged `is_ambiguity_test = True` — genuine conflicting-implementation cases (e.g. JWT auth implemented differently across repos). Broad multi-repo README queries are not counted.
- A **file-hit miss table** is printed at the end of every run showing retrieved filenames vs. expected, enabling quick triage of ranking failures vs. coverage gaps.

### Current Benchmark Results (20-question suite)

| Metric | Score |
|---|---|
| Repo hit rate | 89% (17/19) |
| File hit rate | 57% (11/19) — *being actively improved* |
| Answer quality | 100% (20/20) |
| Ambiguity detection | 66% (2/3) |
| Avg latency | ~11 s |

> File-hit misses were traced to eval/debug scripts committed inside target repos competing with implementation files in retrieval. Fixed by excluding `eval/` directories and root-level check scripts from the code index via `SKIP_DIRS` and `SKIP_FILENAMES` in `config.py`.

---

## Known Limitations

- Tree-sitter chunking is scoped to a small set of languages; other file types fall back to regex-based declaration parsing, which is less precise at handling nested structures.
- Conversation memory is session-only and does not persist across page refreshes.
- Evaluation set contains 20 questions benchmarked against 3 target repositories — results demonstrate the architecture, not large-scale production performance.
- Incremental re-indexing on commit push (webhook-triggered) is designed but not yet implemented; current updates require a manual per-repo re-ingestion step.
- Groq's free-tier token-per-minute cap (12k TPM) limits continuous eval throughput; the eval runner adds a 5-second inter-query pause to avoid 429 errors.