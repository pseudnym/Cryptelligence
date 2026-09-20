"""Allowlisted requests and backend-owned scope, permission and scoring policy."""
import hashlib
import re
from ..models.domain import Entity, InvestigativeAction
from .tools import ToolResult
from .chains import solana_address, solana_signature

CAPABILITIES = {
    "inspect_ethereum_address": ("inspect_address", "Inspect a bounded Ethereum transfer window", "blockchain_observation"),
    "expand_ethereum_wallet": ("expand_counterparty", "Inspect a known counterparty", "blockchain_observation"),
    "trace_inbound": ("trace_inbound", "Read incoming Ethereum transfers", "blockchain_observation"),
    "trace_outbound": ("trace_outbound", "Read outgoing Ethereum transfers", "blockchain_observation"),
    "inspect_transaction": ("inspect_transaction", "Inspect a transaction already present in the case", "blockchain_observation"),
    "search_wallet_osint": ("search_exact_wallet_address", "Search public sources for an existing wallet", "osint"),
    "verify_attribution": ("verify_external_attribution", "Seek another public attribution source; no automatic verification", "osint"),
    "search_entity_osint": ("search_public_identifier", "Search an existing public entity identifier", "osint"),
    "find_corroboration": ("find_independent_corroboration", "Seek independent public reporting", "osint"),
    "get_case_evidence": ("get_case_evidence", "Refresh bounded normalized case evidence in reasoning context", "case_state"),
    "get_case_entities": ("get_case_entities", "Refresh known case entities", "case_state"),
    "get_claims": ("get_claims", "Refresh current claims, including unknowns", "case_state"),
    "get_competing_explanations": ("get_competing_explanations", "Refresh previous explanations", "case_state"),
    "manual_review": ("manual_review", "Analyst-only review; cannot execute automatically", "analyst_input"),
}
from .solana_tool import CAPABILITIES as SOLANA_CAPABILITIES
CAPABILITIES.update({cap: (cap, "Read bounded Solana observations: " + cap, "blockchain_observation") for cap in SOLANA_CAPABILITIES})
READS = {key for key, value in CAPABILITIES.items() if value[2] == "case_state"}

def definitions():
    return [dict(name=name, description=description, expected_evidence_type=kind,
        parameters={"type": "object", "properties": {"target_id": {"type": "string", "description": "Existing case entity or transaction ID; for case reads use a seed ID"}},
                    "required": ["target_id"], "additionalProperties": False})
        for name, (_, description, kind) in CAPABILITIES.items()]

def validate_request(case, request):
    if request.capability not in CAPABILITIES:
        raise ValueError("Unsupported tool name")
    target = next((e for e in case.entities if e.id == request.target_id), None)
    if request.capability in {"inspect_transaction", "inspect_solana_transaction"}:
        expected_chain = "solana" if request.capability == "inspect_solana_transaction" else "ethereum"
        tx = next((t for t in case.transactions if t.id == request.target_id), None)
        if tx:
            if tx.chain != expected_chain: raise ValueError("Transaction chain does not match capability")
            return Entity(id="gemini-tx-" + tx.tx_hash, entity_type="transaction", chain=tx.chain, label=tx.tx_hash, value=tx.tx_hash)
        if expected_chain == "solana":
            if not target or target.chain != "solana": raise ValueError("Unknown Solana transaction")
            solana_signature(target.value)
            return target
        if not target or not re.fullmatch(r"0x[a-fA-F0-9]{64}", target.value):
            raise ValueError("Transaction must already exist in case")
    elif not target:
        raise ValueError("Invalid entity reference")
    if CAPABILITIES[request.capability][2] == "blockchain_observation" and request.capability not in {"inspect_transaction", "inspect_solana_transaction"}:
        if request.capability in SOLANA_CAPABILITIES:
            if target.chain != "solana" or target.entity_type not in {"wallet", "contract"}: raise ValueError("Solana capability requires a Solana address")
            solana_address(target.value)
            return target
        if target.entity_type not in {"wallet", "contract"} or not re.fullmatch(r"0x[a-fA-F0-9]{40}", target.value):
            raise ValueError("Ethereum request requires a known address")
    if request.capability == "search_wallet_osint" and target.entity_type not in {"wallet", "contract"}:
        raise ValueError("Wallet search requires a wallet or contract")
    return target

def make_action(case, request, title, reason, claim_ids=(), hypothesis_ids=()):
    target = validate_request(case, request)
    if not any(e.id == target.id for e in case.entities):
        case.entities.append(target)
    capability, _, kind = CAPABILITIES[request.capability]
    mode = "MANUAL" if request.capability == "manual_review" else "ANALYST_APPROVAL" if target.metadata.get("candidate") else "AUTO"
    # Components are computed here, never accepted from Gemini. Distinct relevant
    # explanation/claim dependencies increase discriminatory usefulness, not certainty.
    discrimination = min(9, 4 + 2 * len(set(hypothesis_ids)) + min(1, len(set(claim_ids))))
    quality, ease, reliability = (9, 7, 8) if kind == "blockchain_observation" else (6, 8, 6) if kind == "osint" else (2, 10, 5) if kind == "case_state" else (5, 2, 5)
    return InvestigativeAction(id="gemini-action-" + hashlib.sha256((capability + ":" + target.id).encode()).hexdigest()[:24],
        investigation_id=case.investigation.id, title=title, description=CAPABILITIES[request.capability][1],
        action_type=capability, target_entity_id=target.id, rationale=reason, execution_mode=mode, generated_by="gemini",
        claim_ids=list(claim_ids), hypotheses_distinguished=list(hypothesis_ids),
        hypothesis_discrimination_score=discrimination, expected_evidence_quality_score=quality,
        ease_score=ease, source_reliability_score=reliability)

class CaseReadTool:
    name = "CaseReadTool"
    capability = tuple(READS)
    def can_handle(self, action): return action in self.capability
    def execute(self, context, action):
        if action not in READS: raise ValueError("Unsupported local read")
        # Next reasoning request reconstructs the bounded structured context from
        # persisted state. Reading it never creates synthetic evidence.
        return ToolResult()
