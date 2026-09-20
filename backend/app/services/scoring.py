from ..models.domain import Case

def ranked_actions(case: Case):
    return sorted((a for a in case.actions if a.status == "pending"), key=lambda a: (-a.total_score, a.id))

def fragility(case: Case):
    evidence = {e.id: e for e in case.evidence}
    claims = {c.id: c for c in case.claims}
    dependencies = {c.id: sum(c.id in h.supporting_claim_ids for h in case.hypotheses) for c in case.claims}
    results = []
    for h in case.hypotheses:
        support = [claims[cid] for cid in h.supporting_claim_ids]
        single = sum(len({evidence[e].source_identifier for e in c.supporting_evidence_ids}) <= 1 for c in support)
        external = sum(any(evidence[e].evidence_type == "external_attribution" for e in c.supporting_evidence_ids) for c in support)
        weak = [c.id for c in support if c.status != "supported" or c.confidence == "LOW" or len({evidence[e].source_identifier for e in c.supporting_evidence_ids}) <= 1]
        label = "FRAGILE" if not support or external or any(c.status != "supported" for c in support) else ("MODERATELY FRAGILE" if weak else "STABLE")
        results.append(dict(hypothesis_id=h.id, label=label, single_source_claims=single,
                            external_attribution_claims=external, critical_dependencies=weak))
    gaps = sorted((c for c in case.claims if c.status in {"unknown", "unsupported", "partially_supported", "disputed"}),
                  key=lambda c: (-len(c.required_for_hypothesis_ids), -dependencies[c.id], c.id))
    return dict(hypotheses=results, dependency_weights=dependencies,
                critical_gap=({"claim_id": gaps[0].id, "statement": gaps[0].statement,
                               "reason": "Unresolved claim required by the most hypotheses."} if gaps else None),
                method="Categorical heuristic, not statistical certainty. Single-source support uses distinct source identifiers; independence is not verified.")

def analysis(case: Case):
    return {"fragility": fragility(case), "ranked_actions": [a.model_dump(mode="json") for a in ranked_actions(case)]}
