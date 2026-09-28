"""
backend/app/schemas/repo.py

Pydantic request/response models for the repository management endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AddRepoRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Repository name")
    url: str = Field(..., min_length=1, description="GitHub repository URL or local folder path")


class HealthResponse(BaseModel):
    status: str
    indexes_loaded: dict[str, bool]
    repos_configured: list[str]
