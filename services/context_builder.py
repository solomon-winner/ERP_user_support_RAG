"""
Context Builder — assembles the full context for the LLM prompt.

Gathers information from:
  1. Route Registry (current page + fields)
  2. Embedding Store (relevant documentation chunks)
  3. Process Graph (current workflow steps)
  4. Conversation history

And formats it all into a structured prompt for the LLM.
"""
from typing import List, Optional, Dict, Any
from app.models.schemas import (
    RouteInfo, ProcessGraph, DocumentChunk, ChatMessage, GuideStep
)
from app.knowledge.route_registry import route_registry
from app.knowledge.process_graph import process_graph_store
from app.knowledge.embedding_store import embedding_store
from app.config import settings


def build_context(
    query: str,
    current_route: str = "",
    user_role: str = "",
    conversation_history: List[ChatMessage] = None,
) -> Dict[str, Any]:
    """
    Build the full context for an LLM prompt.
    
    Returns a dict with:
        - route_info: current route details
        - related_routes: routes linked from the current one
        - process: any process the user is currently in
        - doc_chunks: semantically relevant documentation
        - conversation: recent conversation history
    """
    context: Dict[str, Any] = {
        "route_info": None,
        "related_routes": [],
        "process": None,
        "doc_chunks": [],
        "conversation": conversation_history or [],
    }

    # 1. Current route info
    if current_route:
        route = route_registry.get_route(current_route)
        if route:
            context["route_info"] = route

            # Related routes (next steps + prerequisites)
            next_routes = route_registry.get_next_steps(current_route)
            prereq_routes = route_registry.get_prerequisites(current_route)
            context["related_routes"] = [
                {"path": r.path, "title": r.title, "method": r.method}
                for r in next_routes + prereq_routes
            ]

    # 2. Process graph (find which process the user is in)
    if current_route:
        processes = process_graph_store.get_processes_for_route(current_route)
        if processes:
            # Use the first matching process
            process = processes[0]
            remaining = process_graph_store.get_remaining_steps(
                process.process_name, current_route
            )
            context["process"] = {
                "process_name": process.process_name,
                "title": process.title,
                "description": process.description,
                "total_steps": process.total_steps,
                "remaining_steps": len(remaining),
                "steps": [
                    {
                        "order": s.order,
                        "route": s.route,
                        "title": s.title,
                        "description": s.description,
                    }
                    for s in process.steps
                ],
            }

    # 3. Semantic search for relevant docs (placeholder — requires embeddings)
    # In production, this would generate a query embedding and search pgvector.
    # For now, we do text search as a fallback.
    context["doc_chunks"] = []  # Will be populated by LLM service with actual embedding search

    return context


def build_prompt(
    query: str,
    context: Dict[str, Any],
    conversation_history: List[ChatMessage] = None,
) -> str:
    """
    Assemble the full user prompt from context.
    This is the text that goes into the LLM's user message.
    """
    parts = []

    # Current page context
    if context.get("route_info"):
        route = context["route_info"]
        parts.append(f"CURRENT PAGE: {route.title} ({route.path})")
        parts.append(f"Module: {route.module}")
        if route.description:
            parts.append(f"Description: {route.description}")
        if route.fields:
            parts.append("FIELDS ON THIS PAGE:")
            for field in route.fields:
                desc = f"  - {field.name} ({field.type}): {field.description or field.label or 'No description'}"
                if field.required:
                    desc += " [REQUIRED]"
                if field.enum_values:
                    desc += f" Options: {', '.join(field.enum_values)}"
                parts.append(desc)
        parts.append("")

    # Related routes
    if context.get("related_routes"):
        parts.append("RELATED PAGES (next steps / prerequisites):")
        for r in context["related_routes"]:
            parts.append(f"  - {r['title']} ({r['path']}) [{r['method']}]")
        parts.append("")

    # Process context
    if context.get("process"):
        proc = context["process"]
        parts.append(f"CURRENT WORKFLOW: {proc['title']} ({proc['process_name']})")
        parts.append(f"Total steps: {proc['total_steps']}, Remaining: {proc['remaining_steps']}")
        parts.append("WORKFLOW STEPS:")
        for step in proc["steps"]:
            parts.append(f"  {step['order']}. {step['title']} → {step['route']}")
            if step['description']:
                parts.append(f"     {step['description']}")
        parts.append("")

    # Documentation context
    if context.get("doc_chunks"):
        parts.append("RELEVANT DOCUMENTATION:")
        for chunk in context["doc_chunks"]:
            if isinstance(chunk, DocumentChunk):
                parts.append(f"  [From: {chunk.source_file}, Section: {chunk.section_heading}]")
                parts.append(f"  {chunk.content[:500]}")
            elif isinstance(chunk, dict):
                parts.append(f"  [From: {chunk.get('source_file', 'Unknown')}]")
                parts.append(f"  {chunk.get('content', '')[:500]}")
        parts.append("")

    # Conversation history
    if conversation_history and len(conversation_history) > 0:
        parts.append("PREVIOUS CONVERSATION:")
        for msg in conversation_history[-5:]:  # Last 5 messages
            role = msg.role.upper()
            parts.append(f"  {role}: {msg.content[:200]}")
        parts.append("")

    # User query
    parts.append(f"USER QUESTION: {query}")

    return "\n".join(parts)


SYSTEM_PROMPT = """You are an AI-powered ERP Guide Assistant embedded within an ERP system. Your job is to help users understand how to use the ERP by providing clear, step-by-step guidance.

RULES:
1. When the user asks about a process or workflow, respond with an ordered list of steps.
2. Each step MUST include: title, description, target_route (the ERP page URL), and target_element (CSS selector to highlight).
3. When describing form fields, always include: field name, type, what it's for, and whether it's required.
4. NEVER fabricate routes or fields that aren't mentioned in the context provided.
5. Keep responses concise but complete. Use simple, direct language.
6. If the user is asking about a specific page, focus on that page's functionality.
7. If you're unsure about something, say so rather than guessing.

OUTPUT FORMAT — When providing a step-by-step guide, use this JSON structure:
{
  "answer": "Brief conversational answer to the question",
  "steps": [
    {
      "order": 1,
      "title": "Navigate to Page X",
      "description": "Click on Menu > Submenu to reach the X page",
      "target_route": "/module/page",
      "target_element": "#element-selector",
      "action": "click|fill|select|navigate",
      "fields": [
        {
          "name": "field_name",
          "type": "string",
          "description": "What this field does",
          "required": true
        }
      ],
      "tip": "Optional helpful tip"
    }
  ],
  "related_routes": ["/other/relevant/routes"],
  "suggestions": ["Follow-up question 1", "Follow-up question 2"]
}

When just answering a quick question (not a process), you can skip the steps array and just provide the answer as plain text.
"""
