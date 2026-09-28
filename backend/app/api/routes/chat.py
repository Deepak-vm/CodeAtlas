"""
backend/app/api/routes/chat.py

Chat endpoints — thin routes that delegate to ChatService.

Routes:
  POST /api/v1/query         — run the full RAG pipeline
  GET  /api/v1/history       — fetch query history
  POST /api/v1/history/{id}/save — toggle saved bookmark
  DELETE /api/v1/history/{id}    — delete one history item
  POST /api/v1/history/bulk-delete — bulk delete history items
  POST /api/v1/feedback          — record thumbs rating
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Body

from backend.app.core.exceptions import (
    KnowledgeAgentError,
    NoReposConfiguredError,
    AgentError,
)
from backend.app.core.logging import get_logger
from backend.app.schemas.chat import (
    QueryRequest,
    QueryResponse,
    FeedbackRequest,
)
from backend.app.services.chat_service import chat_service
from backend.app.database.repositories.history import history_repository
from backend.app.database.repositories.feedback import feedback_repository

logger = get_logger(__name__)
router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(req: QueryRequest) -> QueryResponse:
    """Run the full multi-agent RAG pipeline and save result to Supabase."""
    try:
        return chat_service.chat(req)
    except NoReposConfiguredError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except AgentError as e:
        raise HTTPException(status_code=500, detail=e.message)
    except KnowledgeAgentError as e:
        raise HTTPException(status_code=e.http_status, detail=e.message)
    except Exception as e:
        logger.exception("unexpected_error_in_query")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/history")
async def get_history(limit: int = 100) -> dict:
    """Fetch shared query history from Supabase (newest first)."""
    try:
        items = history_repository.get_recent(limit=limit)
        return {"history": items, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {e}")


@router.post("/history/{history_id}/save")
async def toggle_save_history(history_id: int, body: dict = Body(default={})) -> dict:
    """Toggle the 'saved' bookmark flag on a history item."""
    saved = body.get("saved", True)
    try:
        history_repository.toggle_saved(history_id, saved)
        return {"status": "ok", "id": history_id, "saved": saved}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update history item: {e}")


@router.delete("/history/{history_id}")
async def delete_history_item(history_id: int) -> dict:
    """Delete a single history entry."""
    try:
        history_repository.delete(history_id)
        return {"status": "ok", "deleted": history_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete history item: {e}")


@router.post("/history/bulk-delete")
async def bulk_delete_history(body: dict = Body(...)) -> dict:
    """Bulk delete history items by list of IDs."""
    ids = body.get("ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    try:
        history_repository.bulk_delete(ids)
        return {"status": "ok", "deleted_count": len(ids)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk delete: {e}")


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest) -> dict:
    """Record a thumbs-up or thumbs-down rating → Supabase feedback table."""
    try:
        feedback_repository.save(
            query=req.query,
            answer_snippet=req.answer_snippet,
            rating=req.rating,
            routed_repos=req.routed_repos,
        )
    except Exception as e:
        logger.warning("feedback_save_failed", extra={"error": str(e)})

    logger.info("feedback_recorded", extra={"rating": req.rating})
    return {"status": "ok", "recorded": req.rating}
