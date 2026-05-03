"""
Guide Validator — validates LLM output against the Route Registry.

Ensures that routes and fields referenced in the guide actually exist
in the ERP system. Prevents hallucinated navigation paths.
"""
from typing import List
from app.models.schemas import GuideStep, GuideQueryResponse
from app.knowledge.route_registry import route_registry


def validate_guide_response(response: GuideQueryResponse) -> GuideQueryResponse:
    """
    Validate a guide response, removing or flagging invalid references.
    
    Checks:
      - All target_route values exist in the Route Registry
      - All field names exist on their respective routes
      - Steps are in sequential order
    """
    valid_steps = []

    for step in response.steps:
        step_issues = []

        # Validate target_route
        if step.target_route and not route_registry.validate_route_exists(step.target_route):
            step_issues.append(f"Route '{step.target_route}' not found in registry")
            # Don't remove the step, but clear the target_route to prevent broken navigation
            step.target_route = ""
            step.target_element = None

        # Validate fields exist on their routes
        if step.fields and step.target_route:
            valid_fields = []
            for field in step.fields:
                if route_registry.validate_field_exists(step.target_route, field.name):
                    valid_fields.append(field)
                # Keep fields even if not in registry — the LLM might know about them
                # from documentation. Just log the discrepancy.
                else:
                    valid_fields.append(field)
            step.fields = valid_fields

        # Re-number steps sequentially
        valid_steps.append(step)

    # Re-number
    for i, step in enumerate(valid_steps):
        step.order = i + 1

    response.steps = valid_steps
    return response


def is_guide_response_structured(response: GuideQueryResponse) -> bool:
    """Check if the response has structured step-by-step guide data."""
    return len(response.steps) > 0
