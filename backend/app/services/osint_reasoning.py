"""Executable public search actions and narrow deterministic source reasoning."""
from ..models.domain import Claim, InvestigativeAction
from .chains import address_key
from .osint_extraction import candidate_entity, digest, assess_independence
from .osint_tool import CAPABILITIES

def public_action(case, target_id=None, query=None, capability="search_exact_wallet_address"):
    if capability not in CAPABILITIES:
        raise ValueError("Unsupported public search capability")
    if query:
        target = candidate_entity({"kind": "public_identifier", "value": query.strip()})
        existing = next((e for e in case.entities if address_key(e.value) == address_key(target.value)), None)
        if existing: target = existing
        else: case.entities.append(target)
    else:
        target = next((e for e in case.entities if e.id == target_id), None)
        if target is None:
            transaction = next((t for t in case.transactions if t.id == target_id), None)
            if transaction is None: raise KeyError("Search target not found")
            target = candidate_entity({"kind": "transaction_hash", "value": transaction.tx_hash})
            existing = next((e for e in case.entities if e.id == target.id), None)
            if existing: target = existing
            else: case.entities.append(target)
            capability = "search_transaction_hash"
    verification = capability in {"verify_external_attribution", "find_independent_corroboration"}
    return InvestigativeAction(id="osint-action-" + digest(capability + ":" + target.id),
        investigation_id=case.investigation.id, title=("Find independent public references to " if verification else "Search public sources for ") + target.label,
        description="Search public documents; preserve source statements without establishing identity.",
        action_type=capability, target_entity_id=target.id,
        hypothesis_discrimination_score=9 if verification else 6,
        expected_evidence_quality_score=8 if verification else 6, ease_score=8, source_reliability_score=7 if verification else 6,
        rationale="Check original reporting and source dependence. Public allegations are not proof of wallet ownership.")

def public_actions(case):
    existing = {a.id: a for a in case.actions}
    targets = list(case.investigation.seed_entities)
    targets += [e.id for e in case.entities if e.metadata.get("candidate")][:3]
    sources = [e for e in case.evidence if e.source]
    for target in dict.fromkeys(targets):
        for capability in ["search_exact_wallet_address"] + (["find_independent_corroboration"] if sources else []):
            item = public_action(case, target, capability=capability)
            if item.id not in existing:
                case.actions.append(item)
                existing[item.id] = item

def source_reasoning(case):
    case.source_assessments = assess_independence(case.evidence)
    sources = [e for e in case.evidence if e.source]
    for evidence in sources:
        source = evidence.source
        assessment = case.source_assessments[evidence.id]
        source.corroboration = assessment["corroboration"]
        source.derivative = assessment["derivative"]
        source.independence_reason = assessment["reason"]
        direct = source.retrieved_document and source.exact_match
        case.claims.append(Claim(id="source-claim-" + evidence.id, investigation_id=case.investigation.id,
            statement=source.narrow_statement, claim_type="source_observation" if direct else "inference",
            fact_basis="public_source", reasoning_category="FACT" if direct else "INFERENCE",
            status="supported" if direct else "partially_supported", confidence="MEDIUM" if direct else "LOW",
            supporting_evidence_ids=[evidence.id]))
    if sources:
        case.claims.append(Claim(id="source-independent", investigation_id=case.investigation.id,
            statement="Do independent original sources corroborate the reported association?",
            claim_type="inference", reasoning_category="UNKNOWN", status="unknown", confidence="LOW",
            supporting_evidence_ids=[e.id for e in sources]))
        case.investigation.summary += f" {len(sources)} public-source records were collected. These establish source mentions only; allegations and candidate identity links remain unverified."
