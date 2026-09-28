"""
backend/app/api/routes/health.py

Health and diagnostic endpoints.

Routes:
  GET /api/v1/health       — index status + repos configured
  GET /api/v1/debug/disk   — disk usage diagnostics (Render persistent disk)
"""

from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.schemas.repo import HealthResponse
from backend.app.services.repo_service import repo_service

logger = get_logger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Check index files and repo configuration."""
    try:
        data = repo_service.get_health()
    except Exception as e:
        logger.warning("health_check_failed", extra={"error": str(e)})
        raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

    return HealthResponse(
        status="ok",
        indexes_loaded=data["index_status"],
        repos_configured=data["repo_names"],
    )


@router.get("/debug/disk")
async def debug_disk() -> dict:
    """Diagnostic: report disk usage. Helps verify Render persistent disk mount."""
    data_dir = settings.data_dir
    indexes_dir = settings.indexes_dir
    chunks_dir = settings.chunks_dir

    def dir_info(path) -> dict:
        if not path.exists():
            return {"exists": False}
        files = [f.name for f in path.iterdir()] if path.is_dir() else []
        return {"exists": True, "files": sorted(files)}

    disk = shutil.disk_usage(str(data_dir)) if data_dir.exists() else None

    return {
        "data_dir":    {"path": str(data_dir),    **dir_info(data_dir)},
        "indexes_dir": {"path": str(indexes_dir), **dir_info(indexes_dir)},
        "chunks_dir":  {"path": str(chunks_dir),  **dir_info(chunks_dir)},
        "disk_usage":  {
            "total_gb": round(disk.total / 1e9, 2),
            "used_gb":  round(disk.used  / 1e9, 2),
            "free_gb":  round(disk.free  / 1e9, 2),
        } if disk else "data_dir not found",
        "index_files": {
            "code_faiss":   settings.code_faiss_path.exists(),
            "commit_faiss": settings.commit_faiss_path.exists(),
            "readme_faiss": settings.readme_faiss_path.exists(),
            "bm25_code":    settings.bm25_code_path.exists(),
        },
    }
