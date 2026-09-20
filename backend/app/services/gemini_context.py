"""Bounded, explicit provenance context; no raw provider payloads or configuration."""
import json
from .chains import transfer_statement

def fact_catalog(case, records):
    transactions = {t.id: t for t in case.transactions}
    facts = {}
    for e in records:
        tx = transactions.get(e.raw_data.get("transaction_id"))
        if e.evidence_type == "blockchain_observation" and e.directness == "direct" and tx and tx.metadata.get("status") == "success":
            statement = transfer_statement(tx)
            facts[e.id] = dict(statement=statement, fact_basis="blockchain", supporting_evidence_ids=[e.id])
        elif e.source and e.source.retrieved_document and e.source.exact_match:
            facts[e.id] = dict(statement=e.source.narrow_statement, fact_basis="public_source", supporting_evidence_ids=[e.id])
    return facts

def context_for(case):
    # Prioritize public sources and new/significant chain observations. State the
    # omissions explicitly so a bounded window is never presented as exhaustive.
    sources = [e for e in case.evidence if e.evidence_type in {"osint", "external_attribution"}][-20:]
    other = [e for e in case.evidence if e.id not in {s.id for s in sources}]
    significant = {id for summary in case.collections.values() for id in summary.get("significant_ids", [])}
    receipts = [e for e in other if e.evidence_type == "analyst_input"][-10:]
    notable = [e for e in other if e.raw_data.get("transaction_id") in significant][:30]
    recent = other[-20:]
    selected = list({e.id: e for e in receipts + notable + recent + other[-60:]}.values())[:60]
    records = sources + selected
    linked = set(case.investigation.seed_entities)
    for e in records: linked.update(e.linked_entity_ids)
    essential = set(case.investigation.seed_entities)
    for e in records:
        if e.evidence_type == "blockchain_observation": essential.update(e.linked_entity_ids)
    entities = ([e for e in case.entities if e.id in essential]
                + [e for e in case.entities if e.id in linked and e.id not in essential]
                + [e for e in case.entities if e.id not in linked])[:240]
    included_entity_ids = {e.id for e in entities}
    evidence = []
    for e in records:
        item = dict(id=e.id, evidence_type=e.evidence_type,
            linked_entity_ids=[id for id in e.linked_entity_ids if id in included_entity_ids],
            linked_entities_omitted=sum(id not in included_entity_ids for id in e.linked_entity_ids),
            provenance=dict(source_type=e.source_type, source_url=e.source_url, collected_at=e.collected_at.isoformat(),
                reliability=e.reliability, directness=e.directness, reproducible=e.reproducible))
        if e.evidence_type == "blockchain_observation":
            tx = next((t for t in case.transactions if t.id == e.raw_data.get("transaction_id")), None)
            if tx:
                item["transaction"] = {k:v for k,v in tx.model_dump(mode="json").items() if k != "metadata"}
                item["execution_status"] = tx.metadata.get("status", "unknown")
            elif e.source_type == "solana_rpc" and "program_ids" in e.raw_data:
                item["execution"] = {k:e.raw_data.get(k) for k in ("chain", "signature", "slot", "timestamp", "version", "status", "cluster", "commitment", "fee_lamports", "normalization_limits")}
                item["execution"]["program_ids"] = e.raw_data["program_ids"][:100]
                item["execution"]["balance_deltas"] = e.raw_data.get("balance_deltas", [])[:100]

        else:
            item["untrusted_source_content"] = dict(instructions_allowed=False,
                title=e.title[:300], excerpt=(e.source.excerpt if e.source else e.description)[:1200])
            if e.source:
                item["source_assessment"] = dict(exact_match=e.source.exact_match, retrieved_document=e.source.retrieved_document,
                    corroboration=e.source.corroboration, independence_reason=e.source.independence_reason,
                    limitations=e.source.limitations)
        evidence.append(item)
    result = dict(objective=case.investigation.objective, seed_ids=case.investigation.seed_entities,
        entities=[dict(id=e.id, type=e.entity_type, chain=e.chain, value=e.value[:200], label=e.label[:150]) for e in entities],
        possible_cross_chain_relationships=[r.model_dump(mode="json") for r in case.relationships][:20],
        evidence=evidence, allowed_facts=fact_catalog(case, records),
        current_claims=[c.model_dump(mode="json") for c in case.claims][-40:],
        previous_explanations=[h.model_dump(mode="json") for h in case.hypotheses][:8],
        unresolved_questions=[c.statement for c in case.claims if c.reasoning_category == "UNKNOWN"][:20],
        completed_actions=[dict(capability=a.action_type, target_id=a.target_entity_id) for a in case.actions if a.status == "completed"][-50:],
        limits=dict(evidence_included=len(records), evidence_total=len(case.evidence), entities_included=len(entities),
                    entities_total=len(case.entities), auto_steps=case.auto_steps, max_auto_steps=case.max_auto_steps))
    if len(json.dumps(result)) > 240000:
        raise ValueError("Structured case context exceeds its configured boundary")
    return result
