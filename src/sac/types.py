"""
SaC SDK Type Definitions

All data contracts as Pydantic models, ported from the TypeScript product.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ─── Enums ──────────────────────────────────────────────────────────


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class GrowthType(str, Enum):
    EXTEND_CURRENT = "extend_current"
    NEW_PAGE = "new_page"


class IntentType(str, Enum):
    ACTION = "action"
    EXPLORE = "explore"
    REFINE = "refine"
    ENHANCE = "enhance"


class EventType(str, Enum):
    MESSAGE = "message"
    GENERATION = "generation"
    GROWTH = "growth"
    ERROR = "error"


class EventStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


# ─── Core Models ────────────────────────────────────────────────────


class SearchQuery(BaseModel):
    query: str
    purpose: str


class SearchSource(BaseModel):
    title: str
    url: str
    content: str


class SearchResult(BaseModel):
    query: str
    answer: str | None = None
    sources: list[SearchSource] = Field(default_factory=list)
    images: list[str] | None = None


class IntentSuggestion(BaseModel):
    label: str
    prompt: str
    type: IntentType = IntentType.ACTION


class StageSnapshot(BaseModel):
    name: str
    status: StageStatus = StageStatus.PENDING
    duration: float | None = None


class GrowthDecision(BaseModel):
    growth_type: GrowthType = GrowthType.EXTEND_CURRENT
    reason: str = ""


class ModelOption(BaseModel):
    id: str
    name: str
    provider: str


# ─── App ────────────────────────────────────────────────────────────


class App(BaseModel):
    """The core output of SaC — a versioned, generated UI artifact."""

    code: str
    version: int = 1
    intent: str = ""
    parent_version: int | None = None
    search_queries: list[SearchQuery] = Field(default_factory=list)
    search_results: list[SearchResult] = Field(default_factory=list)
    suggestions: list[IntentSuggestion] = Field(default_factory=list)
    growth_decision: GrowthDecision | None = None
    stages: list[StageSnapshot] = Field(default_factory=list)
    model: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ─── Conversation ──────────────────────────────────────────────────


class ConversationSettings(BaseModel):
    custom_instructions: str = ""
    use_design_system: bool = True
    enable_web_search: bool = True
    intent_rules: str = ""
    growth_rules: str = ""


class ConversationData(BaseModel):
    """Conversation metadata (stored in the store)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model: str = ""
    settings: ConversationSettings = Field(default_factory=ConversationSettings)
    latest_code: str | None = None
    latest_intent: str | None = None
    event_count: int = 0


# ─── Conversation Events (discriminated union) ─────────────────────


class BaseEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MessageEvent(BaseEvent):
    type: Literal["message"] = "message"
    role: Literal["user", "assistant"]
    content: str


class GenerationEvent(BaseEvent):
    type: Literal["generation"] = "generation"
    intent: str
    model: str = ""
    status: EventStatus = EventStatus.PENDING
    code: str | None = None
    stages: list[StageSnapshot] | None = None
    search_queries: list[SearchQuery] | None = None
    search_results: list[SearchResult] | None = None
    intent_suggestions: list[IntentSuggestion] | None = None
    error: str | None = None


class GrowthEvent(BaseEvent):
    type: Literal["growth"] = "growth"
    intent: str
    model: str = ""
    status: EventStatus = EventStatus.PENDING
    code: str | None = None
    stages: list[StageSnapshot] | None = None
    search_queries: list[SearchQuery] | None = None
    search_results: list[SearchResult] | None = None
    intent_suggestions: list[IntentSuggestion] | None = None
    error: str | None = None


class ErrorEvent(BaseEvent):
    type: Literal["error"] = "error"
    message: str
    context: str | None = None


ConversationEvent = MessageEvent | GenerationEvent | GrowthEvent | ErrorEvent


# ─── Pipeline Events (streaming) ──────────────────────────────────


class PipelineStageEvent(BaseModel):
    type: Literal["stage"] = "stage"
    name: str
    status: StageStatus


class PipelineChunkEvent(BaseModel):
    type: Literal["chunk"] = "chunk"
    data: str


class PipelineCompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    app: App


class PipelineErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    error: str


PipelineEvent = PipelineStageEvent | PipelineChunkEvent | PipelineCompleteEvent | PipelineErrorEvent


# ─── Judge / Evaluation Types ─────────────────────────────────────


class L0Violation(BaseModel):
    type: str
    severity: str
    evidence: str
    reason: str


class L0Values(BaseModel):
    passed: bool = Field(alias="pass")
    violations: list[L0Violation] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class L1Credibility(BaseModel):
    passed: bool = Field(alias="pass")
    total_claims: int = 0
    sourced_claims: int = 0
    source_rate: float = 0.0
    unsourced_claims: list[str] = Field(default_factory=list)
    vague_attributions: list[str] = Field(default_factory=list)
    fake_personas: list[str] = Field(default_factory=list)
    vague_numbers: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class L2Narrative(BaseModel):
    passed: bool = Field(alias="pass")
    has_thesis: bool = False
    thesis: str | None = None
    has_closure: bool = False
    structure_type: str = "flat"
    issues: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class L3Interaction(BaseModel):
    element: str
    type: str
    purpose: str


class L3Action(BaseModel):
    passed: bool = Field(alias="pass")
    interactions: list[L3Interaction] = Field(default_factory=list)
    action_count: int = 0
    info_count: int = 0
    has_clear_next_step: bool = False
    issues: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class L4Coherence(BaseModel):
    passed: bool = Field(alias="pass")
    content_theme: str = ""
    visual_tone: str = ""
    tone_match: bool = False
    hierarchy_clear: bool = False
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class L5SpecificityElements(BaseModel):
    has_numbers: bool = False
    has_source: bool = False
    has_value_proposition: bool = False


class L5Card(BaseModel):
    passed: bool = Field(alias="pass")
    title: str = ""
    is_hook: bool = False
    hook_analysis: str = ""
    has_specificity: bool = False
    specificity_elements: L5SpecificityElements = Field(default_factory=L5SpecificityElements)
    visual_info_value: str = "low"
    suggested_title: str = ""
    issues: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PriorityFix(BaseModel):
    level: str
    issue: str
    fix_type: str
    fix_instruction: str


class JudgeSummary(BaseModel):
    overall_pass: bool = False
    passed_levels: list[str] = Field(default_factory=list)
    failed_levels: list[str] = Field(default_factory=list)
    recommendation: str = "regenerate"
    priority_fixes: list[PriorityFix] = Field(default_factory=list)


class JudgeEvalResult(BaseModel):
    L0_values: L0Values
    L1_credibility: L1Credibility
    L2_narrative: L2Narrative
    L3_action: L3Action
    L4_coherence: L4Coherence
    L5_card: L5Card
    summary: JudgeSummary


# ─── UI Verifier Types ────────────────────────────────────────────


class UIVerifierIssue(BaseModel):
    selector: str
    count: int = 1
    fixing: str | None = None
    description: str = ""


class UIVerifierButtons(BaseModel):
    passed: bool = Field(alias="pass")
    total: int = 0
    effective: int = 0
    issues: list[UIVerifierIssue] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UIVerifierContrast(BaseModel):
    passed: bool = Field(alias="pass")
    issues: list[UIVerifierIssue] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class UIVerifierSummary(BaseModel):
    overall_pass: bool = False
    recommendation: Literal["pass", "fix_buttons", "fix_contrast", "fix_both"] = "pass"


class UIVerifierResult(BaseModel):
    buttons: UIVerifierButtons
    contrast: UIVerifierContrast
    summary: UIVerifierSummary


# ─── LLM Message ──────────────────────────────────────────────────


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
