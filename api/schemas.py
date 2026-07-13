"""
api/schemas.py

Pydantic models for the FastAPI request/response contract.
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
    conversation_history: list[ConversationTurn] | None = Field(None, description="Prior turns for multi-turn follow-up")


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


class HealthResponse(BaseModel):
    status: str
    indexes_loaded: dict[str, bool]
    repos_configured: list[str]


class AddRepoRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Repository name")
    url: str = Field(..., min_length=1, description="GitHub repository URL or local folder path")


class FeedbackRequest(BaseModel):
    query: str
    answer_snippet: str = Field(..., description="First 200 chars of the answer for identification")
    rating: Literal["up", "down"]
    routed_repos: list[str] = Field(default_factory=list)

