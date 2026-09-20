"""Validated case state. IDs are local references, never identity attribution."""
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, computed_field, model_validator

from .osint import PublicSource
from .workflow import InvestigationPlan, InvestigationEvent, MostImportantUnknown, CaseRevision

Confidence = Literal["LOW", "MEDIUM", "HIGH"]

class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Entity(Model):
    id: str
    entity_type: Literal["wallet", "transaction", "contract", "protocol", "bridge", "person", "organization", "public_identifier"]
    chain: str | None = None
    label: str
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class Investigation(Model):
    id: str
    seed_entity: str
    objective: str
    created_at: AwareDatetime
    status: Literal["CREATED", "PLANNING", "COLLECTING", "ANALYZING", "AWAITING_ACTION", "EXECUTING_ACTION", "REANALYZING", "COMPLETE", "ERROR"] = "CREATED"
    seed_entities: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def legacy_status(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            data["status"] = {"ready": "AWAITING_ACTION", "investigating": "AWAITING_ACTION", "complete": "COMPLETE"}.get(data.get("status"), data.get("status", "CREATED"))
            data.setdefault("seed_entities", [data["seed_entity"]])
        return data
    summary: str

class TransactionEvent(Model):
    id: str
    chain: str
    tx_hash: str
    timestamp: AwareDatetime
    sender: str
    receiver: str
    asset: str
    amount: Decimal = Field(ge=0, allow_inf_nan=False)
    protocol: str | None = None
    block_number: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

class Evidence(Model):
    source: PublicSource | None = None
    id: str
    investigation_id: str
    evidence_type: Literal["blockchain_observation", "osint", "external_attribution", "model_inference", "analyst_input"]
    title: str
    description: str
    source_type: str
    source_url: str | None = None
    source_identifier: str
    raw_data: dict[str, Any]
    collected_at: AwareDatetime
    reliability: Confidence
    directness: Literal["direct", "indirect"]
    reproducible: bool
    linked_entity_ids: list[str]

class Claim(Model):
    generated_by: str = "deterministic"
    rationale: str = ""
    limitations: str = ""
    entity_ids: list[str] = Field(default_factory=list)
    fact_basis: Literal["blockchain", "public_source"] = "blockchain"
    id: str
    investigation_id: str
    statement: str
    claim_type: Literal["observation", "source_observation", "attribution", "inference"]
    status: Literal["supported", "partially_supported", "disputed", "unsupported", "unknown"]
    confidence: Confidence
    reasoning_category: Literal["FACT", "INFERENCE", "UNKNOWN"] = "INFERENCE"
    supporting_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def category_for_legacy(cls, data):
        if isinstance(data, dict) and "reasoning_category" not in data:
            data = dict(data)
            data["reasoning_category"] = "UNKNOWN" if data.get("status") == "unknown" else "FACT" if data.get("claim_type") == "observation" else "INFERENCE"
        return data

    @model_validator(mode="after")
    def provenance_required(self):
        if self.reasoning_category != "UNKNOWN" and not self.supporting_evidence_ids:
            raise ValueError("Facts and inferences require supporting evidence")
        if self.reasoning_category == "FACT" and (self.claim_type not in {"observation", "source_observation"} or self.status != "supported"):
            raise ValueError("A fact must be an established observation")
        return self
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    required_for_hypothesis_ids: list[str] = Field(default_factory=list)

class Hypothesis(Model):
    limitations: str = ""
    generated_by: str = "deterministic"
    support_assessment: Literal["INSUFFICIENT", "LOW", "MODERATE", "STRONG"] = "LOW"
    id: str
    investigation_id: str
    title: str
    description: str
    confidence: Confidence
    supporting_claim_ids: list[str]
    contradicting_claim_ids: list[str]
    missing_claim_ids: list[str]

class InvestigativeAction(Model):
    execution_mode: Literal["AUTO", "ANALYST_APPROVAL", "MANUAL"] = "AUTO"
    generated_by: str = "deterministic"
    claim_ids: list[str] = Field(default_factory=list)
    hypotheses_distinguished: list[str] = Field(default_factory=list)
    id: str
    investigation_id: str
    title: str
    description: str
    action_type: str
    target_entity_id: str
    hypothesis_discrimination_score: float = Field(ge=0, le=10, allow_inf_nan=False)
    expected_evidence_quality_score: float = Field(ge=0, le=10, allow_inf_nan=False)
    ease_score: float = Field(ge=0, le=10, allow_inf_nan=False)
    source_reliability_score: float = Field(ge=0, le=10, allow_inf_nan=False)
    rationale: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"

    @computed_field
    @property
    def total_score(self) -> float:
        return round(.40 * self.hypothesis_discrimination_score
                     + .25 * self.expected_evidence_quality_score
                     + .20 * self.ease_score + .15 * self.source_reliability_score, 2)

class CrossChainRelationship(Model):
    id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: Literal["possible_cross_chain_transition"] = "possible_cross_chain_transition"
    reasoning_category: Literal["INFERENCE"] = "INFERENCE"
    statement: str
    evidence_ids: list[str] = Field(min_length=1)

class Case(Model):
    relationships: list[CrossChainRelationship] = Field(default_factory=list)
    reasoning_mode: Literal["deterministic", "gemini"] = "deterministic"
    auto_steps: int = 0
    max_auto_steps: int = 5
    automation_paused: bool = False
    reasoning_usage: list[dict[str, Any]] = Field(default_factory=list)
    assessment_claim_ids: list[str] = Field(default_factory=list)
    source_assessments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    collections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    graph_limit: int = Field(default=40, ge=1, le=100)
    fixture: bool = True
    fixture_notice: str
    investigation: Investigation
    entities: list[Entity]
    transactions: list[TransactionEvent]
    evidence: list[Evidence]
    claims: list[Claim]
    hypotheses: list[Hypothesis]
    actions: list[InvestigativeAction]
    revision: int = 1
    changes: list[str] = Field(default_factory=list)
    plan: InvestigationPlan | None = None
    events: list[InvestigationEvent] = Field(default_factory=list)
    important_unknown: MostImportantUnknown | None = None
    revisions: list[CaseRevision] = Field(default_factory=list)
    version: int = 0
    active_action_id: str | None = None
    error: str | None = None
    resume_state: str | None = None
    analyzed_fingerprint: str | None = None

    @model_validator(mode="after")
    def references(self):
        groups = [self.entities, self.transactions, self.evidence, self.claims, self.hypotheses, self.actions]
        for group in groups:
            if len({item.id for item in group}) != len(group):
                raise ValueError("Duplicate IDs")
        entities, evidence, claims, hypotheses = (set(x.id for x in group) for group in
            [self.entities, self.evidence, self.claims, self.hypotheses])
        if entities & {t.id for t in self.transactions}:
            raise ValueError("Graph node IDs must be unique")
        def require(ids, known):
            if not set(ids) <= known:
                raise ValueError("Dangling case reference")
        require([self.investigation.seed_entity] + self.investigation.seed_entities, entities)
        if len(set(self.investigation.seed_entities)) != len(self.investigation.seed_entities):
            raise ValueError("Duplicate seed references")
        for tx in self.transactions:
            require([tx.sender, tx.receiver], entities)
        for e in self.evidence:
            require(e.linked_entity_ids, entities)
        for c in self.claims:
            require(c.supporting_evidence_ids + c.contradicting_evidence_ids, evidence)
            require(c.required_for_hypothesis_ids, hypotheses)
            require(c.entity_ids, entities)
        for h in self.hypotheses:
            require(h.supporting_claim_ids + h.contradicting_claim_ids + h.missing_claim_ids, claims)
        if len({r.id for r in self.relationships}) != len(self.relationships):
            raise ValueError("Duplicate relationship")
        for relation in self.relationships:
            require([relation.source_entity_id, relation.target_entity_id], entities)
            require(relation.evidence_ids, evidence)
            source = next(e for e in self.entities if e.id == relation.source_entity_id)
            target = next(e for e in self.entities if e.id == relation.target_entity_id)
            if source.chain not in {"ethereum", "solana"} or target.chain not in {"ethereum", "solana"} or source.chain == target.chain:
                raise ValueError("Cross-chain relationship requires different supported chains")
        for a in self.actions:
            require([a.target_entity_id], entities)
        actions = {a.id for a in self.actions}
        if self.active_action_id:
            require([self.active_action_id], actions)
        for c in self.claims:
            if c.reasoning_category == "FACT":
                records = [e for e in self.evidence if e.id in c.supporting_evidence_ids]
                if c.fact_basis == "public_source":
                    if c.claim_type != "source_observation" or not any(e.source and e.source.retrieved_document and e.source.exact_match and e.source.narrow_statement == c.statement for e in records):
                        raise ValueError("Public-source facts must be narrow statements grounded in retrieved documents")
                elif not any(e.directness == "direct" and e.evidence_type == "blockchain_observation" for e in records):
                    raise ValueError("Blockchain facts need direct blockchain observations")
        if self.plan:
            if self.plan.investigation_id != self.investigation.id:
                raise ValueError("Cross-investigation plan")
            if len({step.id for step in self.plan.steps}) != len(self.plan.steps):
                raise ValueError("Duplicate plan step")
            for step in self.plan.steps:
                require(step.produced_evidence_ids, evidence)
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("Duplicate event ID")
        for event in self.events:
            if event.investigation_id != self.investigation.id:
                raise ValueError("Cross-investigation event")
            require(event.related_entity_ids, entities)
            require(event.related_evidence_ids, evidence)
        if self.important_unknown:
            require(self.important_unknown.related_hypothesis_ids, hypotheses)
            require(self.important_unknown.claims_needed, claims)
            require(self.important_unknown.potential_resolution_actions, actions)
        if len({r.number for r in self.revisions}) != len(self.revisions):
            raise ValueError("Duplicate revision")
        for revision in self.revisions:
            require(revision.evidence_added, evidence)
        for item in self.evidence + self.claims + self.hypotheses + self.actions:
            if item.investigation_id != self.investigation.id:
                raise ValueError("Cross-investigation reference")
        return self
