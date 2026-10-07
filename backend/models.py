from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IncidentStatus(str, Enum):
    new = "new"
    investigating = "investigating"
    action_required = "action_required"
    verifying = "verifying"
    resolved = "resolved"


class WorkflowStage(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"


class Classification(BaseModel):
    domain: str
    secondary: str | None = None
    severity: str = "P3"
    complexity: str = "MEDIUM"
    source: str = "rules"
    confidence: float | None = None


class Evidence(BaseModel):
    id: str
    source: str
    summary: str
    status: str = "reported"  # reported | confirmed | failed | unavailable
    data: dict[str, Any] | None = None


class Hypothesis(BaseModel):
    id: str
    name: str
    confidence: float | None = None
    rationale: str = ""


class RaftMatch(BaseModel):
    id: str
    title: str
    summary: str = ""
    score: float | None = None
    verification: str = "unknown"
    retrieval: str = "external"


class AgentAction(BaseModel):
    id: str
    label: str
    tool: str | None = None
    requires_approval: bool = False
    status: str = "proposed"


class ClaimReference(BaseModel):
    eventId: int
    relation: str  # reported | observed | failed_check | historical_match | follow_up_check | operator_verification


class TraceClaim(BaseModel):
    id: str
    text: str
    verification: str = "unverified"  # unverified | operator_verified
    references: list[ClaimReference] = Field(default_factory=list)
    createdAt: str


class IncidentState(BaseModel):
    id: str
    origin: str = "live"  # live | example
    seedKey: str | None = None
    examplePhase: str | None = None  # seeded | investigating | awaiting_review | reviewed
    exampleReference: dict[str, str] | None = None
    firstDiagnosis: str | None = None
    firstActions: list[str] = Field(default_factory=list)
    status: IncidentStatus = IncidentStatus.new
    workflowStage: WorkflowStage | None = None
    severity: str = "P3"
    symptoms: list[str] = Field(default_factory=list)
    confirmedFacts: list[Evidence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    rejectedHypotheses: list[Hypothesis] = Field(default_factory=list)
    raftMatches: list[RaftMatch] = Field(default_factory=list)
    actions: list[AgentAction] = Field(default_factory=list)
    currentStep: str = "observe"
    classification: Classification | None = None
    diagnosis: str = ""
    immediateActions: list[str] = Field(default_factory=list)
    reasoningTrace: list[dict[str, str]] = Field(default_factory=list)
    recommendedAction: str = ""
    providerStatus: dict[str, str] = Field(default_factory=dict)
    resolution: dict[str, str] | None = None
    traceId: str = ""
    claims: list[TraceClaim] = Field(default_factory=list)


class DiagnoseRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    attachments: list[str] = Field(default_factory=list)


class DiagnoseResponse(BaseModel):
    incident_id: str
    classification: Classification


class ToolExecuteRequest(BaseModel):
    incident_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class StatusUpdateRequest(BaseModel):
    status: IncidentStatus
    root_cause: str | None = Field(default=None, max_length=1000)
    successful_action: str | None = Field(default=None, max_length=2000)
    note: str | None = Field(default=None, max_length=2000)


class WorkflowUpdateRequest(BaseModel):
    stage: WorkflowStage


class ExampleReviewRequest(BaseModel):
    root_cause: str = Field(min_length=1, max_length=1000)
    successful_action: str = Field(min_length=1, max_length=2000)
    note: str = Field(default="", max_length=2000)
    review_source: str = Field(default="operator", pattern="^(operator|reference_batch)$")
