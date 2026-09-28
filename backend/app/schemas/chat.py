"""
backend/app/schemas/chat.py

Pydantic request/response models for the chat endpoints.

These are the API contract — they must remain stable across refactors.
The existing api/schemas.py models are preserved here verbatim, then
api/schemas.py is updated to re-export from this location for backward
compatibility with any external code that imports from the old path.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    query: str
    answer: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="Question about your codebase")
    repos: list[str] | None = Field(None, description="Optional: restrict search to specific repo names")
    conversation_history: list[ConversationTurn] | None = Field(
        None, description="Prior turns for multi-turn follow-up"
    )


class Citation(BaseModel):
    repo: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    symbol_name: str | None
    commit_hash: str | None
    language: str | None
    snippet: str
    chunk_type: str   # code | commit | readme


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    ambiguity_flag: bool
    ambiguity_detail: str
    latency_ms: float
    routed_repos: list[str]
    routed_types: list[str]


class FeedbackRequest(BaseModel):
    query: str
    answer_snippet: str = Field(..., description="First 200 chars of the answer for identification")
    rating: Literal["up", "down"]
    routed_repos: list[str] = Field(default_factory=list)
