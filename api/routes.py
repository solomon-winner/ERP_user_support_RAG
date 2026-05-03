"""
API Routes — the 4 core REST endpoints for the Guide Assistant.

POST /api/guide/query    — Ask a question, get a step-by-step guide
POST /api/guide/fields   — Get field descriptions for a route
POST /api/guide/process  — Get a business process workflow
POST /api/guide/suggest  — Get proactive suggestions for current page
"""
from fastapi import APIRouter, HTTPException, Depends

from app.models.schemas import (
    GuideQueryRequest, GuideQueryResponse,
    FieldQueryRequest, FieldQueryResponse,
    ProcessQueryRequest, ProcessQueryResponse,
    SuggestRequest, SuggestResponse,
)
from app.services.llm_service import llm_service
from app.services.knowledge_base import kb_service
from app.services.guide_validator import validate_guide_response
from app.services.cache_service import cache_service
from app.config import settings


router = APIRouter()


# ─── Startup initialization ───
_initialized = False


async def ensure_initialized():
    """Load KB data and cache on first request."""
    global _initialized
    if not _initialized:
        kb_service.initialize()
        await cache_service.initialize()
        _initialized = True


# ═══════════════════════════════════════════
#  POST /api/guide/query
# ═══════════════════════════════════════════

@router.post("/query", response_model=GuideQueryResponse)
async def guide_query(request: GuideQueryRequest):
    """
    Ask a natural-language question about the ERP system.
    Returns a conversational answer + step-by-step guide + field descriptions.
    """
    await ensure_initialized()

    # Check cache
    cache_key = f"guide:{request.current_route}:{request.query[:100]}"
    cached = await cache_service.get_json(cache_key)
    if cached:
        return GuideQueryResponse(**cached)

    # Call LLM service
    response = await llm_service.guide_query(
        query=request.query,
        current_route=request.current_route,
        user_role=request.user_role,
        conversation_history=request.conversation_history,
    )

    # Validate (remove hallucinated routes)
    response = validate_guide_response(response)

    # Cache the result
    await cache_service.set_json(cache_key, response.model_dump())

    return response


# ═══════════════════════════════════════════
#  POST /api/guide/fields
# ═══════════════════════════════════════════

@router.post("/fields", response_model=FieldQueryResponse)
async def guide_fields(request: FieldQueryRequest):
    """
    Get field descriptions for a specific ERP route/page.
    Returns all fields with their types, descriptions, and validation rules.
    """
    await ensure_initialized()

    result = kb_service.get_route_fields(request.route, request.user_role)
    if not result:
        raise HTTPException(status_code=404, detail=f"Route not found: {request.route}")

    return result


# ═══════════════════════════════════════════
#  POST /api/guide/process
# ═══════════════════════════════════════════

@router.post("/process", response_model=ProcessQueryResponse)
async def guide_process(request: ProcessQueryRequest):
    """
    Get a business process workflow with ordered steps.
    Optionally start from a specific step number.
    """
    await ensure_initialized()

    result = kb_service.get_process(request.process_name, request.current_step)
    if not result:
        raise HTTPException(status_code=404, detail=f"Process not found: {request.process_name}")

    return result


# ═══════════════════════════════════════════
#  POST /api/guide/suggest
# ═══════════════════════════════════════════

@router.post("/suggest", response_model=SuggestResponse)
async def guide_suggest(request: SuggestRequest):
    """
    Get proactive suggestions based on the current ERP page.
    Returns process walkthroughs, next steps, and field tips.
    """
    await ensure_initialized()

    suggestions = kb_service.get_suggestions(request.current_route, request.user_role)
    return SuggestResponse(suggestions=suggestions)
