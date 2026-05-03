"""
WebSocket endpoint — streaming guide responses for real-time UX.

Provides:
  - ws://host/ws/guide/stream
  - Client sends: {"type": "query", "payload": {"query": "...", "currentRoute": "..."}}
  - Server streams: {"type": "answer_chunk", "payload": {"text": "..."}}
  - Then: {"type": "step", "payload": {"order": 1, "title": "...", ...}}
  - Finally: {"type": "done", "payload": {}}
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.models.schemas import WSClientMessage, WSServerMessage, ChatMessage
from app.services.llm_service import llm_service
from app.services.knowledge_base import kb_service
from app.services.guide_validator import validate_guide_response
from app.services.cache_service import cache_service


router = APIRouter()


@router.websocket("/ws/guide/stream")
async def websocket_guide_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming guide responses.
    
    Protocol:
    1. Client sends: {"type": "query", "payload": {"query": "...", "currentRoute": "/payroll/..."}}
    2. Server streams answer chunks: {"type": "answer_chunk", "payload": {"text": "..."}}
    3. Server sends steps: {"type": "step", "payload": {"order": 1, "title": "...", ...}}
    4. Server sends: {"type": "done", "payload": {}}
    """
    await websocket.accept()
    
    # Initialize KB on first connection
    kb_service.initialize()
    await cache_service.initialize()

    try:
        while True:
            # Receive message from client
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                msg = WSClientMessage(**data)
            except (json.JSONDecodeError, Exception) as e:
                await websocket.send_json(WSServerMessage(
                    type="error",
                    payload={"message": f"Invalid message format: {str(e)}"},
                ).model_dump())
                continue

            if msg.type == "query":
                await _handle_query(websocket, msg.payload)
            elif msg.type == "field_click":
                await _handle_field_click(websocket, msg.payload)
            elif msg.type == "navigate":
                await _handle_navigate(websocket, msg.payload)
            elif msg.type == "feedback":
                # Log feedback for analytics
                print(f"[WS] Feedback: {msg.payload}")
            else:
                await websocket.send_json(WSServerMessage(
                    type="error",
                    payload={"message": f"Unknown message type: {msg.type}"},
                ).model_dump())

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")


async def _handle_query(websocket: WebSocket, payload: dict):
    """Handle a query message — get guide response and stream it back."""
    query = payload.get("query", "")
    current_route = payload.get("currentRoute", "")
    user_role = payload.get("userRole", "")

    if not query:
        await websocket.send_json(WSServerMessage(
            type="error", payload={"message": "Query is required"}
        ).model_dump())
        return

    # Get full guide response (non-streaming for now — will add streaming later)
    response = await llm_service.guide_query(
        query=query,
        current_route=current_route,
        user_role=user_role,
    )
    response = validate_guide_response(response)

    # Stream the answer in chunks
    answer = response.answer
    chunk_size = 50  # characters per chunk
    for i in range(0, len(answer), chunk_size):
        chunk = answer[i:i + chunk_size]
        await websocket.send_json(WSServerMessage(
            type="answer_chunk",
            payload={"text": chunk},
        ).model_dump())

    # Send each step
    for step in response.steps:
        await websocket.send_json(WSServerMessage(
            type="step",
            payload=step.model_dump(),
        ).model_dump())

    # Send highlight instructions
    if response.steps:
        first_step = response.steps[0]
        if first_step.target_element:
            await websocket.send_json(WSServerMessage(
                type="highlight",
                payload={
                    "selector": first_step.target_element,
                    "step": first_step.order,
                },
            ).model_dump())

    # Done
    await websocket.send_json(WSServerMessage(
        type="done",
        payload={
            "related_routes": response.related_routes,
            "suggestions": response.suggestions,
        },
    ).model_dump())


async def _handle_field_click(websocket: WebSocket, payload: dict):
    """Handle a field click — return field description."""
    route = payload.get("route", "")
    field_name = payload.get("fieldName", "")

    from app.knowledge.route_registry import route_registry
    field = route_registry.get_field(route, field_name)

    if field:
        await websocket.send_json(WSServerMessage(
            type="field_description",
            payload=field.model_dump(),
        ).model_dump())
    else:
        await websocket.send_json(WSServerMessage(
            type="field_description",
            payload={"name": field_name, "description": "No description available."},
        ).model_dump())


async def _handle_navigate(websocket: WebSocket, payload: dict):
    """Handle a navigate event — send suggestions for the new page."""
    current_route = payload.get("currentRoute", "")

    suggestions = kb_service.get_suggestions(current_route)
    await websocket.send_json(WSServerMessage(
        type="suggestions",
        payload={"suggestions": [s.model_dump() for s in suggestions]},
    ).model_dump())
