"""
Pydantic schemas for request/response models.
These define the API contract between the frontend and the backend.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum


# ═══════════════════════════════════════════
#  Shared / Nested Models
# ═══════════════════════════════════════════

class FieldDescription(BaseModel):
    """Describes a single form field on an ERP page."""
    name: str = Field(..., description="Field name / key in the form")
    type: str = Field("string", description="Data type: string, number, date, enum, boolean, etc.")
    label: Optional[str] = Field(None, description="Human-readable label shown on the form")
    description: str = Field("", description="What this field is for, in plain language")
    required: bool = Field(False, description="Whether the field is mandatory")
    validation: Optional[str] = Field(None, description="Validation rule, e.g. 'min:0, max:999999'")
    example: Optional[str] = Field(None, description="Example value for the field")
    enum_values: Optional[List[str]] = Field(None, description="Allowed values if type is enum")


class RouteInfo(BaseModel):
    """Describes a single ERP route / page."""
    path: str = Field(..., description="Route path, e.g. /payroll/employee/list")
    method: str = Field("GET", description="HTTP method: GET, POST, PUT, DELETE")
    module: str = Field("", description="ERP module this route belongs to, e.g. Payroll")
    title: str = Field("", description="Human-readable page title")
    description: str = Field("", description="What this page/endpoint does")
    fields: List[FieldDescription] = Field(default_factory=list, description="Form fields on this page")
    permissions: List[str] = Field(default_factory=list, description="Required permissions to access")
    next_steps: List[str] = Field(default_factory=list, description="Route paths for next logical steps")
    prerequisites: List[str] = Field(default_factory=list, description="Route paths that must be visited first")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")


class ProcessStep(BaseModel):
    """A single step within a business process workflow."""
    order: int = Field(..., description="Step number in the sequence (1-based)")
    route: str = Field(..., description="ERP route path for this step")
    title: str = Field(..., description="Short title for the step, e.g. 'Select Pay Period'")
    description: str = Field("", description="Detailed description of what to do in this step")
    target_element: Optional[str] = Field(None, description="CSS selector for the element to highlight, e.g. #pay-period-dropdown")
    action: Optional[str] = Field(None, description="Action to take: click, fill, select, navigate")
    fields: List[FieldDescription] = Field(default_factory=list, description="Fields involved in this step")
    next_step_condition: Optional[str] = Field(None, description="Condition for branching, e.g. 'If approval required → /payroll/approval'")


class ProcessGraph(BaseModel):
    """A complete business process with ordered steps."""
    process_name: str = Field(..., description="Unique process identifier, e.g. 'payroll_run'")
    title: str = Field(..., description="Human-readable process name, e.g. 'Run Payroll'")
    description: str = Field("", description="What this process accomplishes")
    module: str = Field("", description="ERP module this process belongs to")
    steps: List[ProcessStep] = Field(default_factory=list, description="Ordered steps in the process")
    total_steps: int = Field(0, description="Total number of steps")


# ═══════════════════════════════════════════
#  Guide Step (LLM Output Model)
# ═══════════════════════════════════════════

class GuideStep(BaseModel):
    """A single step in the guide returned to the frontend."""
    order: int = Field(..., description="Step number (1-based)")
    title: str = Field(..., description="Short instruction, e.g. 'Navigate to Payroll Period Selection'")
    description: str = Field("", description="Detailed explanation of what to do and why")
    target_route: str = Field("", description="ERP route path for this step")
    target_element: Optional[str] = Field(None, description="CSS selector to highlight on the page")
    action: Optional[str] = Field(None, description="click, fill, select, navigate")
    fields: List[FieldDescription] = Field(default_factory=list, description="Fields to fill in this step")
    tip: Optional[str] = Field(None, description="Optional tip or warning")


# ═══════════════════════════════════════════
#  API Request Models
# ═══════════════════════════════════════════

class ChatMessage(BaseModel):
    """A single message in the conversation history."""
    role: str = Field(..., description="user or assistant")
    content: str = Field(..., description="Message text")


class GuideQueryRequest(BaseModel):
    """Request body for POST /api/guide/query"""
    query: str = Field(..., description="User's natural-language question", min_length=1)
    current_route: str = Field("", description="Current ERP page route, e.g. /payroll/employee/list")
    user_role: str = Field("", description="User's role for permission-aware guidance")
    conversation_history: List[ChatMessage] = Field(default_factory=list, description="Previous messages in this conversation")


class FieldQueryRequest(BaseModel):
    """Request body for POST /api/guide/fields"""
    route: str = Field(..., description="ERP route path to get field descriptions for")
    user_role: str = Field("", description="User's role for permission filtering")


class ProcessQueryRequest(BaseModel):
    """Request body for POST /api/guide/process"""
    process_name: str = Field(..., description="Process identifier, e.g. 'payroll_run'")
    current_step: Optional[int] = Field(None, description="Current step number (1-based) for context")


class SuggestRequest(BaseModel):
    """Request body for POST /api/guide/suggest"""
    current_route: str = Field(..., description="Current ERP page route")
    user_role: str = Field("", description="User's role for permission filtering")


# ═══════════════════════════════════════════
#  API Response Models
# ═══════════════════════════════════════════

class GuideQueryResponse(BaseModel):
    """Response for POST /api/guide/query"""
    answer: str = Field(..., description="Conversational answer to the user's question")
    steps: List[GuideStep] = Field(default_factory=list, description="Ordered step-by-step guide")
    related_routes: List[str] = Field(default_factory=list, description="Other routes mentioned in the answer")
    suggestions: List[str] = Field(default_factory=list, description="Follow-up questions the user might ask")


class FieldQueryResponse(BaseModel):
    """Response for POST /api/guide/fields"""
    route: str
    title: str = ""
    fields: List[FieldDescription] = Field(default_factory=list)


class ProcessQueryResponse(BaseModel):
    """Response for POST /api/guide/process"""
    process_name: str
    title: str = ""
    description: str = ""
    steps: List[ProcessStep] = Field(default_factory=list)
    total_steps: int = 0


class SuggestionType(str, Enum):
    process = "process"
    field = "field"
    tip = "tip"


class Suggestion(BaseModel):
    """A proactive suggestion for the user."""
    type: SuggestionType
    title: str
    description: str
    confidence: float = Field(0.5, ge=0.0, le=1.0)


class SuggestResponse(BaseModel):
    """Response for POST /api/guide/suggest"""
    suggestions: List[Suggestion] = Field(default_factory=list)


# ═══════════════════════════════════════════
#  WebSocket Message Models
# ═══════════════════════════════════════════

class WSClientMessage(BaseModel):
    """Message from client over WebSocket."""
    type: str = Field(..., description="query, navigate, field_click, feedback")
    payload: Dict[str, Any] = Field(default_factory=dict)


class WSServerMessage(BaseModel):
    """Message from server over WebSocket."""
    type: str = Field(..., description="answer_chunk, step, highlight, done, error")
    payload: Dict[str, Any] = Field(default_factory=dict)


# ═══════════════════════════════════════════
#  Ingestion Models
# ═══════════════════════════════════════════

class DocumentChunk(BaseModel):
    """A chunk of documentation stored in the vector DB."""
    id: Optional[int] = None
    content: str
    source_file: str
    section_heading: str = ""
    page_number: int = 0
    embedding: Optional[List[float]] = None


class IngestionResult(BaseModel):
    """Result of an ingestion run."""
    source: str
    items_processed: int
    items_stored: int
    errors: List[str] = Field(default_factory=list)
