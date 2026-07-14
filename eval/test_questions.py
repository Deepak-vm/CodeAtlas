"""
eval/test_questions.py

20 ground-truth labeled evaluation questions for CodeAtlas.

Each question has:
  - query            : the natural language question
  - expected_repo    : which repo(s) should appear in retrieved chunks ("NONE" for negative tests)
  - expected_file    : substring that should appear in the retrieved file paths (None for negative tests)
  - expected_type    : primary content type (code / commits / readme)
  - is_ambiguity_test: True ONLY for genuine conflicting-implementation cross-repo cases.
                       Broad multi-repo queries (e.g. "what does this project do?") are NOT
                       ambiguity tests — they're legitimately answered from many repos.
  - notes            : evaluation purpose and expected behavior

NOTE on "NONE" repo questions (negative / hallucination tests):
  These are excluded from repo_hit and file_hit denominators entirely.
  They are only scored via answer_ok (did the system correctly decline?).
"""

from __future__ import annotations

EVAL_QUESTIONS: list[dict] = [
    # ── Code retrieval ─────────────────────────────────────────────────────
    {
        "id": 1,
        "query": "where have I implemented WebSocket real-time features?",
        "expected_repo": "SketchXPad",
        "expected_file": "useDrawingSocket",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Surfaces DrawingCanvas / useDrawingSocket in SketchXPad",
    },
    {
        "id": 2,
        "query": "show me my retry and backoff logic",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tools",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Tests symbol-name BM25 boost — tools.py or router in MultiSource-RAG-Agent",
    },
    {
        "id": 3,
        "query": "how does my RAG router agent work?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "router",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Retrieves router.py from MultiSource-RAG-Agent",
    },
    {
        "id": 4,
        "query": "where do I configure FAISS vector search?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tools",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Vector index setup in tools.py / config.py",
    },
    {
        "id": 5,
        "query": "show me my async task queue implementation",
        "expected_repo": ["SketchXPad", "MultiSource-RAG-Agent"],
        "expected_file": "DrawingCanvas",
        "expected_type": "code",
        "is_ambiguity_test": True,
        "notes": "TRUE ambiguity — async patterns exist in both repos with different implementations",
    },
    {
        "id": 6,
        "query": "where do I handle authentication and JWT tokens?",
        "expected_repo": ["SketchXPad", "LearnSphere"],
        "expected_file": "middleware",
        "expected_type": "code",
        "is_ambiguity_test": True,
        "notes": "TRUE ambiguity — JWT auth implemented differently in both SketchXPad and LearnSphere",
    },
    {
        "id": 7,
        "query": "how do I scrape web pages in my crawler?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tools",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Web scraping utilities in tools.py",
    },
    {
        "id": 8,
        "query": "where do I parse HTML or use BeautifulSoup?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tools",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "BeautifulSoup HTML parsing in tools.py",
    },
    {
        "id": 9,
        "query": "show me how I call the OpenAI or Groq API",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "router",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Groq client initialization and completions in router.py",
    },
    {
        "id": 10,
        "query": "where is my database model definition?",
        "expected_repo": "SketchXPad",
        "expected_file": "types",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Prisma schema & database types in packages/common/src/types.ts",
    },
    # ── Commit / history ─────────────────────────────────────────────────
    {
        "id": 11,
        "query": "when did I add streaming support and why?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "router",
        "expected_type": "commits",
        "is_ambiguity_test": False,
        "notes": "Commit-message retrieval — finds router streaming commits",
    },
    {
        "id": 12,
        "query": "what was the most recent change to the router?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "router",
        "expected_type": "commits",
        "is_ambiguity_test": False,
        "notes": "Recency + file-name combo on router.py commits",
    },
    {
        "id": 13,
        "query": "who refactored the embedding pipeline and what changed?",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tools",
        "expected_type": "commits",
        "is_ambiguity_test": False,
        "notes": "Author and commit log retrieval for embedding refactoring",
    },
    # ── README / docs ─────────────────────────────────────────────────────
    {
        "id": 14,
        "query": "what does this project do overall?",
        "expected_repo": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"],
        "expected_file": "README",
        "expected_type": "readme",
        "is_ambiguity_test": False,
        "notes": "Broad README overview — legitimately multi-repo, NOT true ambiguity (no conflicting implementations)",
    },
    {
        "id": 15,
        "query": "how do I run this project locally?",
        "expected_repo": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"],
        "expected_file": "README",
        "expected_type": "readme",
        "is_ambiguity_test": False,
        "notes": "Broad installation query — legitimately multi-repo, NOT true ambiguity",
    },
    # ── Broad cross-repo (multi-repo but NOT true ambiguity) ───────────────
    {
        "id": 16,
        "query": "how do I handle errors and exceptions across my projects?",
        "expected_repo": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"],
        "expected_file": "middleware",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Broad error-handling query spanning all repos — multi-repo but NOT conflicting-implementation ambiguity",
    },
    # ── True ambiguity (same concept, different impls across repos) ────────
    {
        "id": 17,
        "query": "where do I use environment variables and config loading?",
        "expected_repo": ["LearnSphere", "SketchXPad", "MultiSource-RAG-Agent"],
        "expected_file": "config",
        "expected_type": "code",
        "is_ambiguity_test": True,
        "notes": "TRUE ambiguity — dotenv / config loading implemented differently across all 3 repos",
    },
    # ── Negative / Hallucination tests ─────────────────────────────────────
    {
        "id": 18,
        # Rewritten from a meta-instruction to a genuine out-of-domain user question.
        # Kubernetes is not referenced in any indexed repo (LearnSphere, SketchXPad,
        # MultiSource-RAG-Agent), so the system should decline or say not found.
        # Scored ONLY via answer_ok; excluded from repo_hit and file_hit denominators.
        "query": "how do I connect this project to a Kubernetes cluster for deployment?",
        "expected_repo": "NONE",
        "expected_file": None,
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Negative / hallucination test — Kubernetes not in any indexed repo; system must not hallucinate. "
                 "Excluded from repo_hit/file_hit denominators, scored only by answer_ok.",
    },
    {
        "id": 19,
        "query": "find my logging setup",
        "expected_repo": "MultiSource-RAG-Agent",
        "expected_file": "tracking",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Short query — logging / tracking setup in tracking.py",
    },
    {
        "id": 20,
        "query": "how do I paginate API responses?",
        "expected_repo": "LearnSphere",
        "expected_file": "payHistory",
        "expected_type": "code",
        "is_ambiguity_test": False,
        "notes": "Pagination logic in LearnSphere frontend/components",
    },
]
