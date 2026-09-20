from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class PlanStep(WorkflowModel):
    investigative_question: str = ""
    expected_evidence_type: str = ""
    target_entity_id: str | None = None
    action_id: str | None = None
    id: str
    title: str
    description: str
    tool_or_adapter: str
    capability: str
    reason: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    produced_evidence_ids: list[str] = Field(default_factory=list)

class InvestigationPlan(WorkflowModel):
    id: str
    investigation_id: str
    objective: str
    steps: list[PlanStep]
    created_at: AwareDatetime
    status: Literal["active", "completed", "failed"] = "active"

class InvestigationEvent(WorkflowModel):
    id: str
    investigation_id: str
    timestamp: AwareDatetime
    event_type: str
    title: str
    description: str
    related_entity_ids: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class MostImportantUnknown(WorkflowModel):
    evidence_that_could_resolve_it: str = ""
    question: str
    why_it_matters: str
    related_hypothesis_ids: list[str]
    claims_needed: list[str]
    potential_resolution_actions: list[str]

class CaseRevision(WorkflowModel):
    number: int
    timestamp: AwareDatetime
    reason: str
    evidence_added: list[str]
    claims_changed: list[dict[str, Any]]
    explanation_support_changed: list[dict[str, Any]]
    unknowns_resolved: list[str]
    unknowns_introduced: list[str]
    still_unknown: list[str]
    next_action_before: str | None
    next_action_after: str | None
    fragility_before: dict[str, Any] | None
    fragility_after: dict[str, Any]
    snapshot: dict[str, Any]

class AdvanceRequest(WorkflowModel):
    expected_version: int = Field(ge=0)
