"""
backend/app/api/dependencies.py

FastAPI dependency injection helpers.

Usage in routes:
    from backend.app.api.dependencies import require_configured_repos

    @router.post("/query")
    async def query(req: QueryRequest, _=Depends(require_configured_repos)):
        ...
"""

from __future__ import annotations

from fastapi import HTTPException

from backend.app.database.repositories.repos import repo_repository


async def require_configured_repos() -> None:
    """
    FastAPI dependency: raise 400 if no repositories have been configured.
    Used by the /query endpoint to give a clear error before hitting the graph.
    """
    try:
        repos = repo_repository.get_all()
    except Exception:
        repos = []

    if not repos:
        raise HTTPException(
            status_code=400,
            detail=(
                "No repositories are configured. "
                "Please add and index at least one repository from the Repositories page."
            ),
        )
