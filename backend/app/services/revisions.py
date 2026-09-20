from datetime import datetime, timezone
from ..models.domain import Case
from ..models.workflow import CaseRevision
from .scoring import fragility, ranked_actions

def snapshot(case: Case):
    ranked = ranked_actions(case)
    return {
        "evidence": [e.id for e in case.evidence],
        "claims": {c.id: c.model_dump(mode="json") for c in case.claims},
        "hypotheses": {h.id: h.model_dump(mode="json") for h in case.hypotheses},
        "unknowns": {c.id: c.statement for c in case.claims if c.reasoning_category == "UNKNOWN"},
        "next_action": ranked[0].id if ranked else None,
        "fragility": fragility(case),
    }

def record_revision(case: Case, reason: str):
    before = case.revisions[-1].snapshot if case.revisions else {}
    after = snapshot(case)
    def changed(key):
        previous = before.get(key, {})
        return [{"id": id, "before": previous.get(id), "after": value}
                for id, value in after[key].items() if previous.get(id) != value]
    previous_unknowns = before.get("unknowns", {})
    current_unknowns = after["unknowns"]
    case.revision = case.revisions[-1].number + 1 if case.revisions else 1
    revision = CaseRevision(number=case.revision, timestamp=datetime.now(timezone.utc), reason=reason,
        evidence_added=[id for id in after["evidence"] if id not in before.get("evidence", [])],
        claims_changed=changed("claims"), explanation_support_changed=changed("hypotheses"),
        unknowns_resolved=[previous_unknowns[id] for id in previous_unknowns if id not in current_unknowns],
        unknowns_introduced=[current_unknowns[id] for id in current_unknowns if id not in previous_unknowns],
        still_unknown=list(current_unknowns.values()), next_action_before=before.get("next_action"),
        next_action_after=after["next_action"], fragility_before=before.get("fragility"),
        fragility_after=after["fragility"], snapshot=after)
    case.revisions.append(revision)
    case.changes = [f"{len(revision.evidence_added)} new evidence record(s)."]
    if before:
        for change in revision.claims_changed:
            if change["before"] and change["before"]["status"] != change["after"]["status"]:
                case.changes.append(change["after"]["statement"] + ": " + change["before"]["status"] + " → " + change["after"]["status"])
        for change in revision.explanation_support_changed:
            if change["before"] and change["before"]["support_assessment"] != change["after"]["support_assessment"]:
                case.changes.append(change["after"]["title"] + " support: " + change["before"]["support_assessment"] + " → " + change["after"]["support_assessment"])
    if revision.next_action_after:
        case.changes.append("Next step: " + next(a.title for a in case.actions if a.id == revision.next_action_after))
