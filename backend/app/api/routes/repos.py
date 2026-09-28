"""
backend/app/api/routes/repos.py

Repository management endpoints — thin routes that delegate to RepoService.

Routes:
  GET    /api/v1/repos              — list configured repos
  POST   /api/v1/repos/add          — add + ingest + index a new repo
  DELETE /api/v1/repos/{name}       — delete repo + remove from indexes
  POST   /api/v1/repos/{name}/update — re-index a repo
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.core.exceptions import (
    KnowledgeAgentError,
    RepoDuplicateError,
    RepositoryNotFoundError,
    IngestionError,
)
from backend.app.core.logging import get_logger
from backend.app.schemas.repo import AddRepoRequest
from backend.app.services.repo_service import repo_service

logger = get_logger(__name__)
router = APIRouter()


@router.get("/repos")
async def list_repos() -> dict:
    """Return configured repos with chunk counts from Supabase."""
    try:
        return repo_service.list_repos()
    except KnowledgeAgentError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load repos: {e}")


@router.post("/repos/add")
async def add_repo(req: AddRepoRequest) -> dict:
    """Add a new repository to Supabase and trigger ingestion + indexing."""
    try:
        return repo_service.add_repo(req.name, req.url)
    except RepoDuplicateError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except IngestionError as e:
        raise HTTPException(status_code=500, detail=e.message)
    except KnowledgeAgentError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add repo: {e}")


@router.delete("/repos/{repo_name}")
async def delete_repo(repo_name: str) -> dict:
    """Delete a repository from Supabase and remove from indexes."""
    try:
        return repo_service.delete_repo(repo_name)
    except RepositoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except KnowledgeAgentError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete repo: {e}")


@router.post("/repos/{repo_name}/update")
async def update_repo(repo_name: str) -> dict:
    """Re-index a single repository in-place and update Supabase timestamp."""
    try:
        return repo_service.update_repo(repo_name)
    except RepositoryNotFoundError as e:
        raise HTTPException(status_code=404, detail=e.message)
    except IngestionError as e:
        raise HTTPException(status_code=500, detail=e.message)
    except KnowledgeAgentError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update repo: {e}")
