"""
Knowledge Base Service — unified query interface for all KB components.

This is the main service that the API routes call. It orchestrates
lookups across the Route Registry, Process Graph, and Embedding Store.
"""
from typing import List, Optional
from app.models.schemas import (
    RouteInfo, FieldDescription, ProcessGraph, ProcessStep,
    FieldQueryResponse, ProcessQueryResponse, Suggestion, SuggestionType,
)
from app.knowledge.route_registry import route_registry
from app.knowledge.process_graph import process_graph_store
from app.config import settings


class KnowledgeBaseService:
    """Unified interface for querying the Knowledge Base."""

    def get_route_fields(
        self, route_path: str, user_role: str = ""
    ) -> Optional[FieldQueryResponse]:
        """Get field descriptions for a specific route."""
        route = route_registry.get_route(route_path)
        if not route:
            return None

        # Filter by permissions if user_role is provided
        fields = route.fields
        if user_role and route.permissions:
            # Simple check: if user doesn't have the required permission, 
            # still return fields but mark them
            pass

        return FieldQueryResponse(
            route=route.path,
            title=route.title,
            fields=fields,
        )

    def get_process(
        self, process_name: str, current_step: Optional[int] = None
    ) -> Optional[ProcessQueryResponse]:
        """Get a process definition, optionally starting from a specific step."""
        process = process_graph_store.get_process(process_name)
        if not process:
            return None

        steps = process.steps
        if current_step is not None:
            # Return from current step onwards
            steps = [s for s in steps if s.order >= current_step]

        return ProcessQueryResponse(
            process_name=process.process_name,
            title=process.title,
            description=process.description,
            steps=steps,
            total_steps=process.total_steps,
        )

    def get_suggestions(
        self, current_route: str, user_role: str = ""
    ) -> List[Suggestion]:
        """Generate proactive suggestions based on the current route."""
        suggestions = []

        # 1. Suggest related processes
        processes = process_graph_store.get_processes_for_route(current_route)
        for process in processes[:3]:
            suggestions.append(Suggestion(
                type=SuggestionType.process,
                title=f"Start: {process.title}",
                description=process.description or f"Follow the {process.title} workflow ({process.total_steps} steps)",
                confidence=0.9,
            ))

        # 2. Suggest next steps
        next_routes = route_registry.get_next_steps(current_route)
        for route in next_routes[:2]:
            suggestions.append(Suggestion(
                type=SuggestionType.tip,
                title=f"Next: {route.title}",
                description=f"Navigate to {route.path} — {route.description}" if route.description else f"Go to {route.path}",
                confidence=0.7,
            ))

        # 3. Suggest field help
        route = route_registry.get_route(current_route)
        if route and route.fields:
            required_fields = [f for f in route.fields if f.required]
            if required_fields:
                suggestions.append(Suggestion(
                    type=SuggestionType.field,
                    title=f"Required fields on this page",
                    description=f"This page has {len(required_fields)} required field(s): {', '.join(f.name for f in required_fields[:5])}",
                    confidence=0.8,
                ))

        return suggestions

    def initialize(self) -> None:
        """Load all KB components."""
        route_registry.load()
        process_graph_store.load()
        print("[KnowledgeBase] All components loaded")


# Singleton instance
kb_service = KnowledgeBaseService()
