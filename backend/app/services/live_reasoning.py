"""Deterministic live reasoning: no identity or incident assumptions."""
from decimal import Decimal
from datetime import datetime, timezone
from ..models.domain import Claim, Hypothesis, InvestigativeAction
from ..models.workflow import InvestigationPlan, PlanStep

def live_plan(case):
    order = [("get_transactions", "Inspect Ethereum transactions"),
             ("get_internal_transactions", "Inspect internal value transfers"),
             ("get_token_transfers", "Inspect token transfers")]
    if "token" in case.investigation.objective.lower():
        order = [order[2], *order[:2]]
    chains = {e.chain for e in case.entities if e.id in case.investigation.seed_entities}
    if "ethereum" not in chains: order = []
    if "solana" in chains: order.append(("get_solana_transactions", "Inspect Solana transactions"))
    return InvestigationPlan(id="plan-" + case.investigation.id, investigation_id=case.investigation.id,
        objective=case.investigation.objective, created_at=datetime.now(timezone.utc),
        steps=[PlanStep(id="step-" + capability, title=title, description="Collect a bounded provider window and retain provenance.",
            tool_or_adapter="SolanaInvestigationTool" if "solana" in capability else "EthereumInvestigationTool", capability=capability,
            reason="Establish observable sources, destinations and coverage for: " + case.investigation.objective)
            for capability, title in order])

def live_reasoning(case):
    claims = []
    evidence = {e.raw_data.get("transaction_id"): e.id for e in case.evidence if e.evidence_type == "blockchain_observation"}
    selected = set(id for s in case.collections.values() for id in s["significant_ids"])
    transactions = [t for t in case.transactions if t.id in selected and t.metadata.get("status") == "success"][-case.graph_limit:]
    for tx in transactions:
        verb = "recorded a contract call to" if tx.amount == 0 else "transferred " + str(tx.amount) + " " + tx.asset + " to"
        claims.append(Claim(id="fact-" + tx.id, investigation_id=case.investigation.id,
            statement=tx.sender[4:] + " " + verb + " " + tx.receiver[4:] + ".",
            claim_type="observation", reasoning_category="FACT", status="supported", confidence="HIGH",
            supporting_evidence_ids=[evidence[tx.id]]))
    def unknown(id, text, required=()):
        claims.append(Claim(id=id, investigation_id=case.investigation.id, statement=text,
            claim_type="inference", reasoning_category="UNKNOWN", status="unknown", confidence="LOW",
            required_for_hypothesis_ids=list(required)))
    unknown("live-identity", "Who controls the observed addresses? Blockchain flows alone do not establish identity.")
    unknown("live-coverage", "What activity lies outside the collected pages and supported transfer types?")
    case.hypotheses = []
    seeds = set(case.investigation.seed_entities)
    inbound = [t for t in transactions if t.receiver in seeds and t.sender not in seeds and t.amount > 0]
    outbound = [t for t in transactions if t.sender in seeds and t.receiver not in seeds and t.amount > 0]
    pairs = [(i,o) for i in inbound for o in outbound if i.chain == o.chain]
    if pairs:
        unknown("live-purpose", "Are the observed receipts and payments economically related?", ["live-routing", "live-independent"])
        support = ["fact-" + t.id for t in pairs[0]]
        for id, title, description in [
            ("live-routing", "Related receipts and onward payments", "The collected window includes receipts and outbound payments. An onward-flow explanation is possible, but timing, asset conversion and economic linkage are not established."),
            ("live-independent", "Independent receipts and payments", "The same records are also consistent with unrelated activity. No flow alone proves common control or links particular received units to a later payment.")]:
            case.hypotheses.append(Hypothesis(id=id, investigation_id=case.investigation.id, title=title,
                description=description, confidence="LOW", support_assessment="LOW", supporting_claim_ids=support,
                contradicting_claim_ids=[], missing_claim_ids=["live-purpose", "live-identity", "live-coverage"]))
    for summary in case.collections.values():
        if summary["direction"] != "all":
            continue
        for row in summary["top_counterparties"][:3]:
            id = row["entity_id"]
            if not any(s["entity_id"] == id and s["direction"] == "outbound" for s in case.collections.values()):
                if not any(c.id == "destination-" + id for c in claims):
                    unknown("destination-" + id, "What outbound activity is recorded for " + id[4:] + "?")
    if len({e.chain for e in case.entities if e.id in seeds}) > 1:
        unknown("cross-chain-gap", "Which, if any, cross-chain transitions are supported by bridge or independently sourced evidence?")
    case.claims = claims
    successful = sum(t.metadata.get("status") == "success" for t in case.transactions)
    limited = any(s["truncated"] or s["warnings"] for s in case.collections.values())
    case.investigation.summary = (
        f"Collected {len(case.transactions)} normalized blockchain events across {len(case.collections)} collection windows; "
        f"{successful} report successful execution. "
        + ("Collection is partial or limited. " if limited else "Counts describe the collected windows. ")
        + ("Receipts and outbound activity permit competing flow explanations. " if case.hypotheses else "Insufficient evidence for competing flow explanations. ")
        + "Ownership, identity and economic links remain unproven.")
    from .osint_reasoning import source_reasoning
    source_reasoning(case)

def pivot_action(case, target, direction):
    capability = {"inbound": "trace_inbound", "outbound": "trace_outbound", "inspect": "expand_counterparty"}[direction]
    if target.chain == "solana":
        capability = {"inbound":"trace_solana_inbound","outbound":"trace_solana_outbound","inspect":"expand_solana_address"}[direction]
    title = {"inbound": "Inspect source of funds for ", "outbound": "Trace outbound activity from ", "inspect": "Inspect counterparties of "}[direction] + target.label
    return InvestigativeAction(id="action-" + capability + "-" + target.id, investigation_id=case.investigation.id,
        title=title, description="Fetch a bounded live blockchain window into this investigation.",
        action_type=capability, target_entity_id=target.id, hypothesis_discrimination_score=7,
        expected_evidence_quality_score=9, ease_score=7, source_reliability_score=8,
        rationale="Collect the next observable relationships and test the current coverage gap. Transfers cannot establish shared ownership.")

def live_actions(case):
    existing = {a.id: a for a in case.actions}
    completed = [a for a in case.actions if a.status in {"completed", "running", "failed"}]
    entities = {e.id: e for e in case.entities}
    ordered = []
    # Prioritize large native outbound branches, then other significant counterparties.
    for summary in reversed(list(case.collections.values())):
        rows = sorted(summary["largest_outbound"], key=lambda r: (r["asset"] != "ETH", -Decimal(r["amount"]) if r["asset"] == "ETH" else 0))
        for row in rows:
            tx = next(t for t in case.transactions if t.id == row["transaction_id"])
            if tx.receiver not in case.investigation.seed_entities:
                ordered.append(tx.receiver)
    for summary in case.collections.values():
        ordered.extend(c["entity_id"] for c in summary["top_counterparties"])
    ordered.extend(case.investigation.seed_entities)
    candidates = []
    for id in dict.fromkeys(ordered):
        if id not in entities or entities[id].entity_type not in {"wallet", "contract"} or entities[id].chain not in {"ethereum", "solana"}:
            continue
        for direction in ("outbound", "inbound", "inspect"):
            candidate = pivot_action(case, entities[id], direction)
            if candidate.id not in existing or existing[candidate.id].status == "pending":
                candidate.hypothesis_discrimination_score = max(5, 8 - len(candidates) * .1)
                candidates.append(candidate)
        if len(candidates) >= 9:
            break
    case.actions = completed + candidates[:9]
    from .osint_reasoning import public_actions
    public_actions(case)
