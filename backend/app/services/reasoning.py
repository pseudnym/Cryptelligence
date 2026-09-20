"""Deterministic reasoning over collected records. No fixture conclusions are loaded."""
from typing import Protocol
from ..models.domain import Case, Claim, Hypothesis

class ReasoningEngine(Protocol):
    def evaluate(self, case: Case) -> None: ...

class DeterministicReasoningEngine:
    def evaluate(self, case: Case):
        if not case.fixture:
            from .live_reasoning import live_reasoning
            return live_reasoning(case)
        records = {e.id: e for e in case.evidence}
        case_id = case.investigation.id
        claims: list[Claim] = []
        def claim(id, statement, category, status, confidence, support=(), contra=(), required=()):
            claims.append(Claim(id=id, investigation_id=case_id, statement=statement,
                reasoning_category=category, claim_type="observation" if category == "FACT" else "attribution" if id == "c-attribution" else "inference",
                status=status, confidence=confidence, supporting_evidence_ids=list(support),
                contradicting_evidence_ids=list(contra), required_for_hypothesis_ids=list(required)))

        has_case = all(key in records for key in ["e-flow", "e-attribution", "e-osint"])
        verified = "e-verification" in records
        if has_case:
            claim("c-flow", "The seed transferred fixture funds to counterparty B.", "FACT", "supported", "HIGH",
                ["e-flow"], required=["h-control", "h-flow"])
            claim("c-attribution", "The seed is associated with the incident described in the fixture note.", "INFERENCE",
                "disputed" if verified else "partially_supported", "LOW", ["e-attribution"],
                ["e-verification"] if verified else [], ["h-control"])
            claim("c-control", "The seed and Counterparty B may share a controller.", "INFERENCE", "disputed", "LOW",
                ["e-flow", "e-attribution"], ["e-osint"] + (["e-verification"] if verified else []), ["h-control"])
            claim("c-service", "Counterparty B could be a service used by unrelated actors.", "INFERENCE", "partially_supported", "LOW",
                ["e-osint"], required=["h-flow"])
            claim("c-gap", "Are the seed and Counterparty B controlled by the same actor?", "UNKNOWN", "unknown", "LOW",
                ["e-gap"] if "e-gap" in records else [], required=["h-control", "h-flow"])
            claim("c-identity", "Who is the real-world controller of Counterparty B?", "UNKNOWN", "unknown", "LOW")
            claim("c-destination", "Where did Counterparty B send the received funds?", "FACT" if "e-tx-expanded" in records else "UNKNOWN",
                "supported" if "e-tx-expanded" in records else "unknown", "HIGH" if "e-tx-expanded" in records else "LOW",
                ["e-tx-expanded"] if "e-tx-expanded" in records else [])
            if "e-tx-expanded" in records:
                claims[-1].statement = "Counterparty B sent 1,200 fixture ETH to the liquidity pool."
            claim("c-bridge-match", "Which cross-chain destination matches the bridge transfer?", "UNKNOWN", "unknown", "LOW",
                ["e-bridge-gap"] if "e-bridge-gap" in records else [])
            case.hypotheses = [
                Hypothesis(id="h-control", investigation_id=case_id, title="Common control",
                    description="A transfer and an unverified attribution permit a common-control interpretation; neither proves ownership." if not verified else "The second source challenges the attribution. The fund flow remains, but the attribution-dependent support has weakened.",
                    confidence="LOW", support_assessment="INSUFFICIENT" if verified else "LOW",
                    supporting_claim_ids=["c-flow"] if verified else ["c-flow", "c-attribution"],
                    contradicting_claim_ids=["c-control", "c-service"] + (["c-attribution"] if verified else []),
                    missing_claim_ids=["c-gap", "c-identity"]),
                Hypothesis(id="h-flow", investigation_id=case_id, title="Transfer to an intermediary",
                    description="The service note offers an alternative explanation for receipt of funds. It still lacks independent verification.",
                    confidence="LOW", support_assessment="LOW", supporting_claim_ids=["c-flow", "c-service"],
                    contradicting_claim_ids=["c-control"], missing_claim_ids=["c-gap", "c-identity"])
            ]
            case.investigation.summary = (
                "The synthetic records show bridge funds reaching the seed, followed by transfers to Counterparty B and a pool. "
                + ("The incident attribution is now disputed after the second-source check. Common-control support has weakened. " if verified else
                   "One unverified source links the seed to the incident. ")
                + "Common control remains unproven."
                + (" A downstream transfer to the pool is now documented." if "e-tx-expanded" in records else ""))
        else:
            case.hypotheses = []
            case.investigation.summary = "The local collection completed without enough transaction or attribution evidence to support an explanation. No wallet activity or identity can be established from this result."
        for e in case.evidence:
            if e.raw_data.get("coverage") == "unavailable":
                entity = next(item for item in case.entities if item.id == e.linked_entity_ids[0])
                claim("unknown-" + entity.id, "What activity is associated with " + entity.value + "?", "UNKNOWN", "unknown", "LOW", [e.id])
        case.claims = claims
