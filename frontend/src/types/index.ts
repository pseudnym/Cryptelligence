export type Confidence = 'LOW' | 'MEDIUM' | 'HIGH';
export interface Entity { id: string; entity_type: string; chain: string | null; label: string; value: string }
export interface PublicSource {
  publisher: string; source_kind: string; excerpt: string; published_at: string | null;
  retrieved_document: boolean; exact_match: boolean; query_identifier: string;
  narrow_statement: string; limitations: string[]; corroboration: 'YES' | 'NO' | 'UNKNOWN';
  derivative: boolean; independence_reason: string; reliability_reason: string;
  identifiers: { kind: string; value: string }[]; cited_sources: string[];
}
export interface Evidence {
  source: PublicSource | null;
  id: string; evidence_type: string; title: string; description: string; source_type: string;
  source_url: string | null; source_identifier: string; raw_data: Record<string, unknown>;
  collected_at: string; reliability: Confidence; directness: string; reproducible: boolean; linked_entity_ids: string[];
}
export interface Claim {
  generated_by: string; rationale: string; limitations: string; entity_ids: string[];
  id: string; fact_basis: 'blockchain' | 'public_source'; reasoning_category: "FACT" | "INFERENCE" | "UNKNOWN"; statement: string; claim_type: string; status: string; confidence: Confidence;
  supporting_evidence_ids: string[]; contradicting_evidence_ids: string[]; required_for_hypothesis_ids: string[];
}
export interface Hypothesis {
  generated_by: string; limitations: string;
  support_assessment: "INSUFFICIENT" | "LOW" | "MODERATE" | "STRONG";
  id: string; title: string; description: string; confidence: Confidence;
  supporting_claim_ids: string[]; contradicting_claim_ids: string[]; missing_claim_ids: string[];
}
export interface Action {
  execution_mode: "AUTO" | "ANALYST_APPROVAL" | "MANUAL"; generated_by: string; claim_ids: string[]; hypotheses_distinguished: string[];
  action_type: string;
  id: string; title: string; description: string; rationale: string; status: string; total_score: number;
  hypothesis_discrimination_score: number; expected_evidence_quality_score: number;
  ease_score: number; source_reliability_score: number;
}
export interface GraphData {
  nodes: { data: { id: string; label: string; kind: string; value: string; chain?: string } }[];
  edges: { data: { id: string; source: string; target: string; label: string; kind?: string } }[];
}
export interface CollectionSummary {
  entity_id: string; provider: string; provider_transaction_count: number | null; examined: number;
  event_count: number; window_transaction_count: number; inbound_count: number; outbound_count: number;
  token_count: number; internal_count: number; failed_or_unknown_count: number;
  first_observed: string | null; most_recent: string | null; direction: string; scope: string;
  truncated: boolean; warnings: string[]; significant_ids: string[];
  top_counterparties: { entity_id: string; event_count: number }[];
  largest_inbound: { transaction_id: string; asset: string; amount: string }[];
  largest_outbound: { transaction_id: string; asset: string; amount: string }[];
  contract_interactions: string[]; unusual_high_value_ids: string[];
}
export interface Workspace {
  relationships: {id: string; source_entity_id: string; target_entity_id: string; statement: string; evidence_ids: string[]; reasoning_category: "INFERENCE"}[];
  reasoning_mode: "deterministic" | "gemini"; auto_steps: number; max_auto_steps: number; automation_paused: boolean; assessment_claim_ids: string[];
  reasoning_usage: { task: string; model: string; totalTokenCount?: number }[];
  collections: Record<string, CollectionSummary>;
  version: number; active_action_id: string | null; error: string | null;
  plan: { id: string; objective: string; status: string; steps: { id: string; title: string; description: string; reason: string; tool_or_adapter: string; status: string; produced_evidence_ids: string[] }[] } | null;
  events: { id: string; timestamp: string; event_type: string; title: string; description: string; related_evidence_ids: string[] }[];
  important_unknown: { evidence_that_could_resolve_it: string; question: string; why_it_matters: string; related_hypothesis_ids: string[]; claims_needed: string[]; potential_resolution_actions: string[] } | null;
  revisions: { number: number; reason: string; evidence_added: string[]; claims_changed: { id: string; before: Claim | null; after: Claim }[]; explanation_support_changed: { id: string; before: Hypothesis | null; after: Hypothesis }[]; unknowns_resolved: string[]; unknowns_introduced: string[]; still_unknown: string[]; next_action_before: string | null; next_action_after: string | null }[];
  fixture: boolean; fixture_notice: string; revision: number; changes: string[];
  investigation: { id: string; seed_entity: string; objective: string; created_at: string; status: string; summary: string; seed_entities: string[] };
  entities: Entity[]; transactions: { id: string; chain: string; tx_hash: string; sender: string; receiver: string; amount: string; asset: string; timestamp: string; metadata: { status?: string; record_kind?: string } }[];
  claims: Claim[]; evidence: Evidence[]; hypotheses: Hypothesis[]; actions: Action[]; graph: GraphData;
  analysis: {
    ranked_actions: Action[];
    fragility: {
      method: string; critical_gap: { claim_id: string; statement: string; reason: string } | null;
      dependency_weights: Record<string, number>;
      hypotheses: { hypothesis_id: string; label: string; single_source_claims: number; external_attribution_claims: number; critical_dependencies: string[] }[];
    };
  };
}
