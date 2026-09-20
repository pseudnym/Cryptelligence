from ..models.domain import Case, InvestigativeAction
from ..models.workflow import MostImportantUnknown

class ActionEngine:
    def public_action(self, case, target_id, query, capability):
        from .osint_reasoning import public_action
        return public_action(case, target_id, query, capability)

    def pivot_action(self, case, target, direction):
        from .live_reasoning import pivot_action
        return pivot_action(case, target, direction)

    def generate(self, case: Case):
        if not case.fixture:
            from .live_reasoning import live_actions
            return live_actions(case)
        existing = {a.id: a for a in case.actions}
        records = {e.id for e in case.evidence}
        if not case.hypotheses:
            case.actions = []
            return
        definitions = [
            ("a-verify", "Verify attribution with an independent source", "verify_attribution", "seed", [9, 8, 8, 7],
             "Check whether a second source supports the attribution used by the common-control explanation."),
            ("a-expand", "Follow Counterparty B’s next transfer", "expand_hop", "counterparty", [7, 8, 8, 9],
             "Document the next destination without interpreting a transfer as proof of common ownership."),
            ("a-bridge", "Check the bridge destination", "inspect_bridge", "bridge", [6, 7, 6, 8],
             "Check for a matching destination record and make the limits of cross-chain coverage explicit.")
        ]
        actions = []
        for id, title, capability, target, scores, reason in definitions:
            if id == "a-expand" and "e-verification" in records:
                reason = "The source check weakened attribution. Following B's next transfer now addresses the unresolved destination question."
            actions.append(InvestigativeAction(id=id, investigation_id=case.investigation.id,
                title=title, description="Runs a deterministic local collection tool; no live source is contacted.",
                action_type=capability, target_entity_id=target,
                hypothesis_discrimination_score=scores[0], expected_evidence_quality_score=scores[1],
                ease_score=scores[2], source_reliability_score=scores[3], rationale=reason,
                status=existing[id].status if id in existing else "pending"))
        case.actions = actions

    def important_unknown(self, case: Case):
        unknowns = [c for c in case.claims if c.reasoning_category == "UNKNOWN"]
        if not unknowns:
            case.important_unknown = None
            return
        claim = sorted(unknowns, key=lambda c: (-len(c.required_for_hypothesis_ids), c.id))[0]
        case.important_unknown = MostImportantUnknown(question=claim.statement,
            why_it_matters="Resolving this would distinguish common control from an intermediary relationship." if claim.id == "c-gap" else
                "The available records do not establish this part of the investigation question.",
            related_hypothesis_ids=claim.required_for_hypothesis_ids, claims_needed=[claim.id],
            potential_resolution_actions=[a.id for a in case.actions if a.status == "pending"])
