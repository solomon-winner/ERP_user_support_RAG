"""
LLM Service — calls OpenAI API and parses structured responses.

Handles:
  - System prompt management
  - Context → prompt assembly
  - Structured JSON output parsing
  - Fallback for non-JSON responses
  - Mock mode for testing without API credits
"""
import json
from typing import List, Optional, Dict, Any
from openai import OpenAI

from app.models.schemas import (
    GuideStep, GuideQueryResponse, FieldDescription, ChatMessage
)
from app.services.context_builder import build_context, build_prompt, SYSTEM_PROMPT
from app.knowledge.embedding_store import embedding_store
from app.knowledge.route_registry import route_registry
from app.knowledge.process_graph import process_graph_store
from app.config import settings


class LLMService:
    """Service for interacting with the LLM (OpenAI)."""

    def __init__(self):
        self._client: Optional[OpenAI] = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    @property
    def _is_mock_mode(self) -> bool:
        """Check if mock mode is enabled (no real API calls)."""
        return settings.LLM_MOCK_MODE

    async def guide_query(
        self,
        query: str,
        current_route: str = "",
        user_role: str = "",
        conversation_history: List[ChatMessage] = None,
    ) -> GuideQueryResponse:
        """
        Main method: given a user query, build context, call LLM, return structured guide.
        In mock mode, generates realistic responses from the knowledge base without API calls.
        """
        # 1. Build context from knowledge base
        context = build_context(query, current_route, user_role, conversation_history)

        # 2. Semantic search for relevant docs (if embeddings available)
        if not self._is_mock_mode:
            try:
                doc_chunks = await self._semantic_search(query)
                context["doc_chunks"] = doc_chunks
            except Exception as e:
                print(f"[LLMService] Semantic search failed: {e}")
                context["doc_chunks"] = []

        # 3. Call LLM or use mock
        if self._is_mock_mode:
            print("[LLMService] Using MOCK mode — generating response from knowledge base")
            return self._mock_guide_query(query, context, current_route)

        # 4. Build the user prompt
        user_prompt = build_prompt(query, context, conversation_history)

        # 5. Call the real LLM
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )

            content = response.choices[0].message.content.strip()

        except Exception as e:
            print(f"[LLMService] OpenAI API error: {e}")
            return GuideQueryResponse(
                answer=f"I'm sorry, I encountered an error processing your request. Please try again.",
                steps=[],
                related_routes=[],
                suggestions=[],
            )

        # 6. Parse the response
        return self._parse_response(content, context)

    # ═══════════════════════════════════════════
    #  Mock Mode — no API calls needed
    # ═══════════════════════════════════════════

    def _mock_guide_query(
        self,
        query: str,
        context: Dict[str, Any],
        current_route: str = "",
    ) -> GuideQueryResponse:
        """
        Generate a realistic guide response from the knowledge base
        without calling the LLM. Useful for testing and development.
        """
        query_lower = query.lower()
        steps: List[GuideStep] = []
        related_routes: List[str] = []
        suggestions: List[str] = []
        answer = ""

        # ── Try to match a process workflow ──
        matched_process = None
        all_processes = process_graph_store.get_all_processes()
        for proc in all_processes:
            proc_keywords = (
                proc.title.lower() + " " +
                proc.process_name.lower() + " " +
                proc.description.lower() + " " +
                proc.module.lower()
            )
            # Check if the query matches this process
            query_words = query_lower.split()
            match_count = sum(1 for w in query_words if w in proc_keywords)
            if match_count >= 1:
                matched_process = proc
                break

        if matched_process:
            # Build step-by-step guide from the process
            answer = (
                f"To {matched_process.title.lower()}, follow these {matched_process.total_steps} steps. "
                f"This workflow is part of the {matched_process.module} module. "
                f"{matched_process.description}"
            )

            for step in matched_process.steps:
                route_info = route_registry.get_route(step.route)
                step_title = route_info.title if route_info else step.title
                step_fields = step.fields if step.fields else (route_info.fields if route_info else [])

                steps.append(GuideStep(
                    order=step.order,
                    title=step.title,
                    description=step.description,
                    target_route=step.route,
                    target_element=step.target_element,
                    action=step.action,
                    fields=step_fields,
                    tip=step.next_step_condition if step.next_step_condition else None,
                ))

                # Collect related routes
                if step.route not in related_routes:
                    related_routes.append(step.route)

            # Suggestions
            suggestions = [
                f"What are the required fields on {matched_process.steps[0].route}?",
                f"What happens after {matched_process.steps[-1].title}?",
            ]
            if len(matched_process.steps) > 3:
                suggestions.append(f"Skip to step 3 of {matched_process.title}")

        # ── Try to match a route/page ──
        elif current_route:
            route = route_registry.get_route(current_route)
            if route:
                answer = (
                    f"You are currently on the **{route.title}** page ({route.path}) "
                    f"in the {route.module} module. "
                    f"{route.description}"
                )

                if route.fields:
                    field_names = ", ".join(f.name for f in route.fields)
                    answer += f" This page has fields: {field_names}."

                # Build a single-step guide for this page
                steps.append(GuideStep(
                    order=1,
                    title=f"Complete {route.title}",
                    description=route.description,
                    target_route=route.path,
                    target_element=f"#{route.path.split('/')[-1]}-form",
                    action="fill",
                    fields=route.fields,
                    tip="Fill in all required fields and submit." if any(f.required for f in route.fields) else None,
                ))

                # Next steps
                next_routes = route_registry.get_next_steps(current_route)
                for nr in next_routes:
                    related_routes.append(nr.path)
                    suggestions.append(f"How do I use {nr.title}?")

                if route.fields:
                    required = [f for f in route.fields if f.required]
                    if required:
                        suggestions.append(f"What are the required fields on this page?")

        # ── General search across routes ──
        else:
            search_results = route_registry.search_routes(query_lower, limit=5)
            if search_results:
                answer = f"I found {len(search_results)} page(s) related to your question:\n\n"
                for r in search_results:
                    answer += f"• **{r.title}** ({r.path}) — {r.description}\n"
                    related_routes.append(r.path)

                # Build steps for the top result
                top = search_results[0]
                steps.append(GuideStep(
                    order=1,
                    title=f"Navigate to {top.title}",
                    description=f"Go to {top.path} to access {top.title}. {top.description}",
                    target_route=top.path,
                    target_element=None,
                    action="navigate",
                    fields=top.fields,
                ))
                suggestions.append(f"What fields are on {top.title}?")
            else:
                answer = (
                    "I couldn't find a specific match for your question in the ERP system. "
                    "Try asking about a specific module like Payroll or Finance, "
                    "or ask about a process like 'How do I run payroll?' or 'How do I create an invoice?'."
                )

        return GuideQueryResponse(
            answer=answer,
            steps=steps,
            related_routes=related_routes,
            suggestions=suggestions,
        )

    # ═══════════════════════════════════════════
    #  Real LLM methods
    # ═══════════════════════════════════════════

    async def _semantic_search(self, query: str) -> List[Dict]:
        """Generate query embedding and search for relevant docs."""
        client = self._get_client()

        # Generate query embedding
        embedding_response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=query,
            dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        )
        query_embedding = embedding_response.data[0].embedding

        # Search vector store
        await embedding_store.initialize()
        chunks = await embedding_store.search(
            query_embedding,
            top_k=settings.SEMANTIC_SEARCH_TOP_K,
        )

        return [
            {
                "source_file": c.source_file,
                "section_heading": c.section_heading,
                "content": c.content,
            }
            for c in chunks
        ]

    def _parse_response(
        self, content: str, context: Dict[str, Any]
    ) -> GuideQueryResponse:
        """
        Parse the LLM response into a structured GuideQueryResponse.
        Handles both JSON and plain-text responses.
        """
        # Try to parse as JSON
        json_content = content
        if "```json" in content:
            json_content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_content = content.split("```")[1].split("```")[0]

        try:
            parsed = json.loads(json_content)
            return GuideQueryResponse(
                answer=parsed.get("answer", ""),
                steps=[GuideStep(**s) for s in parsed.get("steps", [])],
                related_routes=parsed.get("related_routes", []),
                suggestions=parsed.get("suggestions", []),
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            # Fallback: treat the entire response as the answer
            return GuideQueryResponse(
                answer=content,
                steps=[],
                related_routes=[],
                suggestions=[],
            )


# Singleton instance
llm_service = LLMService()
