"""Strict model proposals; no source/evidence creation or model-owned scores."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(min_length=1, max_length=1600)]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=240)]
Capability = Literal["inspect_solana_address", "get_solana_transactions", "inspect_solana_transaction", "identify_solana_counterparties", "identify_program_interactions", "trace_solana_inbound", "trace_solana_outbound", "expand_solana_address","inspect_ethereum_address", "expand_ethereum_wallet", "trace_inbound", "trace_outbound",
    "inspect_transaction", "search_wallet_osint", "verify_attribution", "search_entity_osint", "find_corroboration",
    "get_case_evidence", "get_case_entities", "get_claims", "get_competing_explanations", "manual_review"]

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class ToolRequest(Strict):
    capability: Capability
    target_id: Ref

class ProposedStep(Strict):
    title: Text
    investigative_question: Text
    reason: Text
    request: ToolRequest
    expected_evidence_type: Literal["blockchain_observation", "osint", "case_state", "analyst_input"]

class PlanOutput(Strict):
    steps: list[ProposedStep] = Field(min_length=1, max_length=8)

class ProposedClaim(Strict):
    id: Ref
    statement: Text
    category: Literal["FACT", "INFERENCE", "UNKNOWN"]
    status: Literal["supported", "partially_supported", "disputed", "unsupported", "unknown"]
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    fact_id: Ref | None
    supporting_evidence_ids: list[Ref] = Field(max_length=20)
    contradicting_evidence_ids: list[Ref] = Field(max_length=20)
    entity_ids: list[Ref] = Field(max_length=20)
    rationale: Text
    limitations: Text

class ProposedHypothesis(Strict):
    id: Ref
    title: Text
    description: Text
    supporting_claim_ids: list[Ref] = Field(max_length=30)
    contradicting_claim_ids: list[Ref] = Field(max_length=30)
    unresolved_claim_ids: list[Ref] = Field(max_length=30)
    limitations: Text

class ProposedAction(Strict):
    title: Text
    request: ToolRequest
    why_it_matters: Text
    hypotheses_distinguished: list[Ref] = Field(max_length=8)
    claim_ids: list[Ref] = Field(max_length=30)

class ProposedUnknown(Strict):
    claim_id: Ref
    why_it_matters: Text
    hypotheses_affected: list[Ref] = Field(max_length=8)
    evidence_that_could_resolve_it: Text

class AssessmentOutput(Strict):
    claims: list[ProposedClaim] = Field(min_length=1, max_length=40)
    hypotheses: list[ProposedHypothesis] = Field(max_length=8)
    important_unknown: ProposedUnknown
    candidate_actions: list[ProposedAction] = Field(max_length=10)
    summary_claim_ids: list[Ref] = Field(min_length=1, max_length=8)
