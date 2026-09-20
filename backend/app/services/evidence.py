from datetime import datetime, timezone
import hashlib
import json
from ..models.domain import Case, Evidence, TransactionEvent
from .tools import ToolResult, Observation
from .chains import address_key

def transaction_evidence(tx: TransactionEvent, investigation_id: str) -> Evidence:
    return Evidence(id="e-" + tx.id, investigation_id=investigation_id,
        evidence_type="blockchain_observation", title="Fixture transfer: " + tx.asset,
        description="Deterministic observation of synthetic fixture data, not a verified on-chain transaction.",
        source_type="mock_chain", source_identifier=tx.tx_hash, source_url=None,
        raw_data={"fixture": True, "transaction": tx.model_dump(mode="json")},
        collected_at=datetime.now(timezone.utc), reliability="HIGH", directness="direct",
        reproducible=True, linked_entity_ids=[tx.sender, tx.receiver])

def normalize(observation: Observation, investigation_id: str) -> Evidence:
    return Evidence(**vars(observation), investigation_id=investigation_id, collected_at=datetime.now(timezone.utc))

def evidence_fingerprint(case: Case):
    records = sorted((e.model_dump(mode="json") for e in case.evidence), key=lambda e: e["id"])
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()

class EvidenceService:
    def merge(self, case: Case, result: ToolResult) -> list[str]:
        # Validate all output on a draft before publishing any data to the caller.
        draft = case.model_copy(deep=True)
        for entity in result.entities:
            existing = next((e for e in draft.entities if e.id == entity.id), None)
            if existing is None:
                draft.entities.append(entity)
            elif address_key(existing.value) != address_key(entity.value):
                raise ValueError("Conflicting entity identifier")
            elif entity.entity_type == "contract":
                existing.entity_type = "contract"
        for tx in result.transactions:
            existing = next((t for t in draft.transactions if t.id == tx.id or (t.chain, t.tx_hash, t.metadata.get("record_kind")) == (tx.chain, tx.tx_hash, tx.metadata.get("record_kind")) and not tx.id.startswith(("eth-tx-", "sol-tx-"))), None)
            if existing and existing != tx:
                raise ValueError("Conflicting transaction observation")
            if existing is None:
                draft.transactions.append(tx)
        added = []
        for observation in result.observations:
            evidence = normalize(observation, case.investigation.id)
            existing = next((e for e in draft.evidence if e.id == evidence.id or
                (e.evidence_type, e.source_identifier, e.raw_data) == (evidence.evidence_type, evidence.source_identifier, evidence.raw_data)), None)
            if existing:
                if existing.id == evidence.id and existing.model_dump(exclude={"collected_at"}) != evidence.model_dump(exclude={"collected_at"}):
                    raise ValueError("Conflicting evidence observation")
                continue
            draft.evidence.append(evidence)
            added.append(evidence.id)
        draft.collections.update(result.collections)
        Case.model_validate(draft.model_dump(exclude_computed_fields=True))
        case.entities, case.transactions, case.evidence = draft.entities, draft.transactions, draft.evidence
        case.collections = draft.collections
        return added
